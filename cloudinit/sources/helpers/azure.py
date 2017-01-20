# This file is part of cloud-init. See LICENSE file for license information.

import json
import logging
import os
import re
import socket
import struct
import tempfile
import time

from cloudinit import stages
from contextlib import contextmanager
from xml.etree import ElementTree

from cloudinit import util


LOG = logging.getLogger(__name__)


@contextmanager
def cd(newdir):
    prevdir = os.getcwd()
    os.chdir(os.path.expanduser(newdir))
    try:
        yield
    finally:
        os.chdir(prevdir)


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
        return util.read_file_or_url(url, headers=headers)

    def post(self, url, data=None, extra_headers=None):
        headers = self.headers
        if extra_headers is not None:
            headers = self.headers.copy()
            headers.update(extra_headers)
        return util.read_file_or_url(url, data=data, headers=headers)


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
        self.tmpdir = tempfile.mkdtemp()
        self.certificate = None
        self.generate_certificate()

    def clean_up(self):
        util.del_dir(self.tmpdir)

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

    def parse_certificates(self, certificates_xml):
        tag = ElementTree.fromstring(certificates_xml).find(
            './/Data')
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
            with open('Certificates.p7m', 'wb') as f:
                f.write(b'\n'.join(lines))
            out, _ = util.subp(
                'openssl cms -decrypt -in Certificates.p7m -inkey'
                ' {private_key} -recip {certificate} | openssl pkcs12 -nodes'
                ' -password pass:'.format(**self.certificate_names),
                shell=True)
        private_keys, certificates = [], []
        current = []
        for line in out.splitlines():
            current.append(line)
            if re.match(r'[-]+END .*?KEY[-]+$', line):
                private_keys.append('\n'.join(current))
                current = []
            elif re.match(r'[-]+END .*?CERTIFICATE[-]+$', line):
                certificates.append('\n'.join(current))
                current = []
        keys = []
        for certificate in certificates:
            with cd(self.tmpdir):
                public_key, _ = util.subp(
                    'openssl x509 -noout -pubkey |'
                    'ssh-keygen -i -m PKCS8 -f /dev/stdin',
                    data=certificate,
                    shell=True)
            keys.append(public_key)
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

    def __init__(self, fallback_lease_file=None):
        LOG.debug('WALinuxAgentShim instantiated, fallback_lease_file=%s',
                  fallback_lease_file)
        self.dhcpoptions = None
        self._endpoint = None
        self.openssl_manager = None
        self.values = {}
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
            self._endpoint = self.find_endpoint(self.lease_file)
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
    def _get_value_from_leases_file(fallback_lease_file):
        leases = []
        content = util.load_file(fallback_lease_file)
        LOG.debug("content is %s", content)
        for line in content.splitlines():
            if 'unknown-245' in line:
                # Example line from Ubuntu
                # option unknown-245 a8:3f:81:10;
                leases.append(line.strip(' ').split(' ', 2)[-1].strip(';\n"'))
        # Return the "most recent" one in the list
        if len(leases) < 1:
            return None
        else:
            return leases[-1]

    @staticmethod
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
                raise ValueError("%s is not valid JSON data", hook_file)
        return dhcp_options

    @staticmethod
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
    def find_endpoint(fallback_lease_file=None):
        LOG.debug('Finding Azure endpoint...')
        value = None
        # Option-245 stored in /run/cloud-init/dhclient.hooks/<ifc>.json
        # a dhclient exit hook that calls cloud-init-dhclient-hook
        dhcp_options = WALinuxAgentShim._load_dhclient_json()
        value = WALinuxAgentShim._get_value_from_dhcpoptions(dhcp_options)
        if value is None:
            # Fallback and check the leases file if unsuccessful
            LOG.debug("Unable to find endpoint in dhclient logs. "
                      " Falling back to check lease files")
            if fallback_lease_file is None:
                LOG.warn("No fallback lease file was specified.")
                value = None
            else:
                LOG.debug("Looking for endpoint in lease file %s",
                          fallback_lease_file)
                value = WALinuxAgentShim._get_value_from_leases_file(
                    fallback_lease_file)

        if value is None:
            raise ValueError('No endpoint found.')

        endpoint_ip_address = WALinuxAgentShim.get_ip_from_lease_value(value)
        LOG.debug('Azure endpoint found at %s', endpoint_ip_address)
        return endpoint_ip_address

    def register_with_azure_and_fetch_data(self):
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
        public_keys = []
        if goal_state.certificates_xml is not None:
            LOG.debug('Certificate XML found; parsing out public keys.')
            public_keys = self.openssl_manager.parse_certificates(
                goal_state.certificates_xml)
        data = {
            'public-keys': public_keys,
        }
        self._report_ready(goal_state, http_client)
        return data

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


def get_metadata_from_fabric(fallback_lease_file=None):
    shim = WALinuxAgentShim(fallback_lease_file=fallback_lease_file)
    try:
        return shim.register_with_azure_and_fetch_data()
    finally:
        shim.clean_up()

# vi: ts=4 expandtab
