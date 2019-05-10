# This file is part of cloud-init. See LICENSE file for license information.

import json
import logging
import os
import re
import socket
import struct
import time

from cloudinit.net import dhcp
from cloudinit import stages
from cloudinit import temp_utils
from contextlib import contextmanager
from xml.etree import ElementTree

from cloudinit import url_helper
from cloudinit import util
from cloudinit.reporting import events

LOG = logging.getLogger(__name__)

# This endpoint matches the format as found in dhcp lease files, since this
# value is applied if the endpoint can't be found within a lease file
DEFAULT_WIRESERVER_ENDPOINT = "a8:3f:81:10"

azure_ds_reporter = events.ReportEventStack(
    name="azure-ds",
    description="initialize reporter for azure ds",
    reporting_enabled=True)


def azure_ds_telemetry_reporter(func):
    def impl(*args, **kwargs):
        with events.ReportEventStack(
                name=func.__name__,
                description=func.__name__,
                parent=azure_ds_reporter):
            return func(*args, **kwargs)
    return impl


@contextmanager
def cd(newdir):
    prevdir = os.getcwd()
    os.chdir(os.path.expanduser(newdir))
    try:
        yield
    finally:
        os.chdir(prevdir)


def _get_dhcp_endpoint_option_name():
    if util.is_FreeBSD():
        azure_endpoint = "option-245"
    else:
        azure_endpoint = "unknown-245"
    return azure_endpoint


class AzureEndpointHttpClient(object):

    headers = {
        'x-ms-agent-name': 'WALinuxAgent',
        'x-ms-version': '2012-11-30',
    }

    def __init__(self, certificate):
        self.extra_secure_headers = {
            "x-ms-cipher-name": "DES_EDE3_CBC",
            "x-ms-guest-agent-public-x509-cert": certificate,
        }

    def get(self, url, secure=False):
        headers = self.headers
        if secure:
            headers = self.headers.copy()
            headers.update(self.extra_secure_headers)
        return url_helper.read_file_or_url(url, headers=headers)

    def post(self, url, data=None, extra_headers=None):
        headers = self.headers
        if extra_headers is not None:
            headers = self.headers.copy()
            headers.update(extra_headers)
        return url_helper.read_file_or_url(url, data=data, headers=headers)


class GoalState(object):

    def __init__(self, xml, http_client):
        self.http_client = http_client
        self.root = ElementTree.fromstring(xml)
        self._certificates_xml = None

    def _text_from_xpath(self, xpath):
        element = self.root.find(xpath)
        if element is not None:
            return element.text
        return None

    @property
    def container_id(self):
        return self._text_from_xpath('./Container/ContainerId')

    @property
    def incarnation(self):
        return self._text_from_xpath('./Incarnation')

    @property
    def instance_id(self):
        return self._text_from_xpath(
            './Container/RoleInstanceList/RoleInstance/InstanceId')

    @property
    def certificates_xml(self):
        if self._certificates_xml is None:
            url = self._text_from_xpath(
                './Container/RoleInstanceList/RoleInstance'
                '/Configuration/Certificates')
            if url is not None:
                self._certificates_xml = self.http_client.get(
                    url, secure=True).contents
        return self._certificates_xml


class OpenSSLManager(object):

    certificate_names = {
        'private_key': 'TransportPrivate.pem',
        'certificate': 'TransportCert.pem',
    }

    def __init__(self):
        self.tmpdir = temp_utils.mkdtemp()
        self.certificate = None
        self.generate_certificate()

    def clean_up(self):
        util.del_dir(self.tmpdir)

    @azure_ds_telemetry_reporter
    def generate_certificate(self):
        LOG.debug('Generating certificate for communication with fabric...')
        if self.certificate is not None:
            LOG.debug('Certificate already generated.')
            return
        with cd(self.tmpdir):
            util.subp([
                'openssl', 'req', '-x509', '-nodes', '-subj',
                '/CN=LinuxTransport', '-days', '32768', '-newkey', 'rsa:2048',
                '-keyout', self.certificate_names['private_key'],
                '-out', self.certificate_names['certificate'],
            ])
            certificate = ''
            for line in open(self.certificate_names['certificate']):
                if "CERTIFICATE" not in line:
                    certificate += line.rstrip()
            self.certificate = certificate
        LOG.debug('New certificate generated.')

    @staticmethod
    @azure_ds_telemetry_reporter
    def _run_x509_action(action, cert):
        cmd = ['openssl', 'x509', '-noout', action]
        result, _ = util.subp(cmd, data=cert)
        return result

    @azure_ds_telemetry_reporter
    def _get_ssh_key_from_cert(self, certificate):
        pub_key = self._run_x509_action('-pubkey', certificate)
        keygen_cmd = ['ssh-keygen', '-i', '-m', 'PKCS8', '-f', '/dev/stdin']
        ssh_key, _ = util.subp(keygen_cmd, data=pub_key)
        return ssh_key

    @azure_ds_telemetry_reporter
    def _get_fingerprint_from_cert(self, certificate):
        """openssl x509 formats fingerprints as so:
        'SHA1 Fingerprint=07:3E:19:D1:4D:1C:79:92:24:C6:A0:FD:8D:DA:\
        B6:A8:BF:27:D4:73\n'

        Azure control plane passes that fingerprint as so:
        '073E19D14D1C799224C6A0FD8DDAB6A8BF27D473'
        """
        raw_fp = self._run_x509_action('-fingerprint', certificate)
        eq = raw_fp.find('=')
        octets = raw_fp[eq+1:-1].split(':')
        return ''.join(octets)

    @azure_ds_telemetry_reporter
    def _decrypt_certs_from_xml(self, certificates_xml):
        """Decrypt the certificates XML document using the our private key;
           return the list of certs and private keys contained in the doc.
        """
        tag = ElementTree.fromstring(certificates_xml).find('.//Data')
        certificates_content = tag.text
        lines = [
            b'MIME-Version: 1.0',
            b'Content-Disposition: attachment; filename="Certificates.p7m"',
            b'Content-Type: application/x-pkcs7-mime; name="Certificates.p7m"',
            b'Content-Transfer-Encoding: base64',
            b'',
            certificates_content.encode('utf-8'),
        ]
        with cd(self.tmpdir):
            out, _ = util.subp(
                'openssl cms -decrypt -in /dev/stdin -inkey'
                ' {private_key} -recip {certificate} | openssl pkcs12 -nodes'
                ' -password pass:'.format(**self.certificate_names),
                shell=True, data=b'\n'.join(lines))
        return out

    @azure_ds_telemetry_reporter
    def parse_certificates(self, certificates_xml):
        """Given the Certificates XML document, return a dictionary of
           fingerprints and associated SSH keys derived from the certs."""
        out = self._decrypt_certs_from_xml(certificates_xml)
        current = []
        keys = {}
        for line in out.splitlines():
            current.append(line)
            if re.match(r'[-]+END .*?KEY[-]+$', line):
                # ignore private_keys
                current = []
            elif re.match(r'[-]+END .*?CERTIFICATE[-]+$', line):
                certificate = '\n'.join(current)
                ssh_key = self._get_ssh_key_from_cert(certificate)
                fingerprint = self._get_fingerprint_from_cert(certificate)
                keys[fingerprint] = ssh_key
                current = []
        return keys


class WALinuxAgentShim(object):

    REPORT_READY_XML_TEMPLATE = '\n'.join([
        '<?xml version="1.0" encoding="utf-8"?>',
        '<Health xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
        ' xmlns:xsd="http://www.w3.org/2001/XMLSchema">',
        '  <GoalStateIncarnation>{incarnation}</GoalStateIncarnation>',
        '  <Container>',
        '    <ContainerId>{container_id}</ContainerId>',
        '    <RoleInstanceList>',
        '      <Role>',
        '        <InstanceId>{instance_id}</InstanceId>',
        '        <Health>',
        '          <State>Ready</State>',
        '        </Health>',
        '      </Role>',
        '    </RoleInstanceList>',
        '  </Container>',
        '</Health>'])

    def __init__(self, fallback_lease_file=None, dhcp_options=None):
        LOG.debug('WALinuxAgentShim instantiated, fallback_lease_file=%s',
                  fallback_lease_file)
        self.dhcpoptions = dhcp_options
        self._endpoint = None
        self.openssl_manager = None
        self.lease_file = fallback_lease_file

    def clean_up(self):
        if self.openssl_manager is not None:
            self.openssl_manager.clean_up()

    @staticmethod
    def _get_hooks_dir():
        _paths = stages.Init()
        return os.path.join(_paths.paths.get_runpath(), "dhclient.hooks")

    @property
    def endpoint(self):
        if self._endpoint is None:
            self._endpoint = self.find_endpoint(self.lease_file,
                                                self.dhcpoptions)
        return self._endpoint

    @staticmethod
    def get_ip_from_lease_value(fallback_lease_value):
        unescaped_value = fallback_lease_value.replace('\\', '')
        if len(unescaped_value) > 4:
            hex_string = ''
            for hex_pair in unescaped_value.split(':'):
                if len(hex_pair) == 1:
                    hex_pair = '0' + hex_pair
                hex_string += hex_pair
            packed_bytes = struct.pack(
                '>L', int(hex_string.replace(':', ''), 16))
        else:
            packed_bytes = unescaped_value.encode('utf-8')
        return socket.inet_ntoa(packed_bytes)

    @staticmethod
    @azure_ds_telemetry_reporter
    def _networkd_get_value_from_leases(leases_d=None):
        return dhcp.networkd_get_option_from_leases(
            'OPTION_245', leases_d=leases_d)

    @staticmethod
    @azure_ds_telemetry_reporter
    def _get_value_from_leases_file(fallback_lease_file):
        leases = []
        try:
            content = util.load_file(fallback_lease_file)
        except IOError as ex:
            LOG.error("Failed to read %s: %s", fallback_lease_file, ex)
            return None

        LOG.debug("content is %s", content)
        option_name = _get_dhcp_endpoint_option_name()
        for line in content.splitlines():
            if option_name in line:
                # Example line from Ubuntu
                # option unknown-245 a8:3f:81:10;
                leases.append(line.strip(' ').split(' ', 2)[-1].strip(';\n"'))
        # Return the "most recent" one in the list
        if len(leases) < 1:
            return None
        else:
            return leases[-1]

    @staticmethod
    @azure_ds_telemetry_reporter
    def _load_dhclient_json():
        dhcp_options = {}
        hooks_dir = WALinuxAgentShim._get_hooks_dir()
        if not os.path.exists(hooks_dir):
            LOG.debug("%s not found.", hooks_dir)
            return None
        hook_files = [os.path.join(hooks_dir, x)
                      for x in os.listdir(hooks_dir)]
        for hook_file in hook_files:
            try:
                name = os.path.basename(hook_file).replace('.json', '')
                dhcp_options[name] = json.loads(util.load_file((hook_file)))
            except ValueError:
                raise ValueError(
                    '{_file} is not valid JSON data'.format(_file=hook_file))
        return dhcp_options

    @staticmethod
    @azure_ds_telemetry_reporter
    def _get_value_from_dhcpoptions(dhcp_options):
        if dhcp_options is None:
            return None
        # the MS endpoint server is given to us as DHPC option 245
        _value = None
        for interface in dhcp_options:
            _value = dhcp_options[interface].get('unknown_245', None)
            if _value is not None:
                LOG.debug("Endpoint server found in dhclient options")
                break
        return _value

    @staticmethod
    @azure_ds_telemetry_reporter
    def find_endpoint(fallback_lease_file=None, dhcp245=None):
        value = None
        if dhcp245 is not None:
            value = dhcp245
            LOG.debug("Using Azure Endpoint from dhcp options")
        if value is None:
            LOG.debug('Finding Azure endpoint from networkd...')
            value = WALinuxAgentShim._networkd_get_value_from_leases()
        if value is None:
            # Option-245 stored in /run/cloud-init/dhclient.hooks/<ifc>.json
            # a dhclient exit hook that calls cloud-init-dhclient-hook
            LOG.debug('Finding Azure endpoint from hook json...')
            dhcp_options = WALinuxAgentShim._load_dhclient_json()
            value = WALinuxAgentShim._get_value_from_dhcpoptions(dhcp_options)
        if value is None:
            # Fallback and check the leases file if unsuccessful
            LOG.debug("Unable to find endpoint in dhclient logs. "
                      " Falling back to check lease files")
            if fallback_lease_file is None:
                LOG.warning("No fallback lease file was specified.")
                value = None
            else:
                LOG.debug("Looking for endpoint in lease file %s",
                          fallback_lease_file)
                value = WALinuxAgentShim._get_value_from_leases_file(
                    fallback_lease_file)
        if value is None:
            LOG.warning("No lease found; using default endpoint")
            value = DEFAULT_WIRESERVER_ENDPOINT

        endpoint_ip_address = WALinuxAgentShim.get_ip_from_lease_value(value)
        LOG.debug('Azure endpoint found at %s', endpoint_ip_address)
        return endpoint_ip_address

    @azure_ds_telemetry_reporter
    def register_with_azure_and_fetch_data(self, pubkey_info=None):
        if self.openssl_manager is None:
            self.openssl_manager = OpenSSLManager()
        http_client = AzureEndpointHttpClient(self.openssl_manager.certificate)
        LOG.info('Registering with Azure...')
        attempts = 0
        while True:
            try:
                response = http_client.get(
                    'http://{0}/machine/?comp=goalstate'.format(self.endpoint))
            except Exception:
                if attempts < 10:
                    time.sleep(attempts + 1)
                else:
                    raise
            else:
                break
            attempts += 1
        LOG.debug('Successfully fetched GoalState XML.')
        goal_state = GoalState(response.contents, http_client)
        ssh_keys = []
        if goal_state.certificates_xml is not None and pubkey_info is not None:
            LOG.debug('Certificate XML found; parsing out public keys.')
            keys_by_fingerprint = self.openssl_manager.parse_certificates(
                goal_state.certificates_xml)
            ssh_keys = self._filter_pubkeys(keys_by_fingerprint, pubkey_info)
        self._report_ready(goal_state, http_client)
        return {'public-keys': ssh_keys}

    def _filter_pubkeys(self, keys_by_fingerprint, pubkey_info):
        """cloud-init expects a straightforward array of keys to be dropped
           into the user's authorized_keys file. Azure control plane exposes
           multiple public keys to the VM via wireserver. Select just the
           user's key(s) and return them, ignoring any other certs.
        """
        keys = []
        for pubkey in pubkey_info:
            if 'value' in pubkey and pubkey['value']:
                keys.append(pubkey['value'])
            elif 'fingerprint' in pubkey and pubkey['fingerprint']:
                fingerprint = pubkey['fingerprint']
                if fingerprint in keys_by_fingerprint:
                    keys.append(keys_by_fingerprint[fingerprint])
                else:
                    LOG.warning("ovf-env.xml specified PublicKey fingerprint "
                                "%s not found in goalstate XML", fingerprint)
            else:
                LOG.warning("ovf-env.xml specified PublicKey with neither "
                            "value nor fingerprint: %s", pubkey)

        return keys

    @azure_ds_telemetry_reporter
    def _report_ready(self, goal_state, http_client):
        LOG.debug('Reporting ready to Azure fabric.')
        document = self.REPORT_READY_XML_TEMPLATE.format(
            incarnation=goal_state.incarnation,
            container_id=goal_state.container_id,
            instance_id=goal_state.instance_id,
        )
        http_client.post(
            "http://{0}/machine?comp=health".format(self.endpoint),
            data=document,
            extra_headers={'Content-Type': 'text/xml; charset=utf-8'},
        )
        LOG.info('Reported ready to Azure fabric.')


@azure_ds_telemetry_reporter
def get_metadata_from_fabric(fallback_lease_file=None, dhcp_opts=None,
                             pubkey_info=None):
    shim = WALinuxAgentShim(fallback_lease_file=fallback_lease_file,
                            dhcp_options=dhcp_opts)
    try:
        return shim.register_with_azure_and_fetch_data(pubkey_info=pubkey_info)
    finally:
        shim.clean_up()

# vi: ts=4 expandtab
