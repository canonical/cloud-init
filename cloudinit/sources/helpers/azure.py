# This file is part of cloud-init. See LICENSE file for license information.
import base64
import json
import logging
import os
import re
import socket
import struct
import time
import textwrap
import zlib
from errno import ENOENT

from cloudinit.settings import CFG_BUILTIN
from cloudinit.net import dhcp
from cloudinit import stages
from cloudinit import temp_utils
from contextlib import contextmanager
from xml.etree import ElementTree
from xml.sax.saxutils import escape

from cloudinit import subp
from cloudinit import url_helper
from cloudinit import util
from cloudinit import version
from cloudinit import distros
from cloudinit.reporting import events
from cloudinit.net.dhcp import EphemeralDHCPv4
from datetime import datetime

LOG = logging.getLogger(__name__)

# This endpoint matches the format as found in dhcp lease files, since this
# value is applied if the endpoint can't be found within a lease file
DEFAULT_WIRESERVER_ENDPOINT = "a8:3f:81:10"

BOOT_EVENT_TYPE = 'boot-telemetry'
SYSTEMINFO_EVENT_TYPE = 'system-info'
DIAGNOSTIC_EVENT_TYPE = 'diagnostic'
COMPRESSED_EVENT_TYPE = 'compressed'
# Maximum number of bytes of the cloud-init.log file that can be dumped to KVP
# at once. This number is based on the analysis done on a large sample of
# cloud-init.log files where the P95 of the file sizes was 537KB and the time
# consumed to dump 500KB file was (P95:76, P99:233, P99.9:1170) in ms
MAX_LOG_TO_KVP_LENGTH = 512000
# File to store the last byte of cloud-init.log that was pushed to KVP. This
# file will be deleted with every VM reboot.
LOG_PUSHED_TO_KVP_INDEX_FILE = '/run/cloud-init/log_pushed_to_kvp_index'
azure_ds_reporter = events.ReportEventStack(
    name="azure-ds",
    description="initialize reporter for azure ds",
    reporting_enabled=True)

DEFAULT_REPORT_FAILURE_USER_VISIBLE_MESSAGE = (
    'The VM encountered an error during deployment. '
    'Please visit https://aka.ms/linuxprovisioningerror '
    'for more information on remediation.')


def azure_ds_telemetry_reporter(func):
    def impl(*args, **kwargs):
        with events.ReportEventStack(
                name=func.__name__,
                description=func.__name__,
                parent=azure_ds_reporter):
            return func(*args, **kwargs)
    return impl


def is_byte_swapped(previous_id, current_id):
    """
    Azure stores the instance ID with an incorrect byte ordering for the
    first parts. This corrects the byte order such that it is consistent with
    that returned by the metadata service.
    """
    if previous_id == current_id:
        return False

    def swap_bytestring(s, width=2):
        dd = [byte for byte in textwrap.wrap(s, 2)]
        dd.reverse()
        return ''.join(dd)

    parts = current_id.split('-')
    swapped_id = '-'.join(
        [
            swap_bytestring(parts[0]),
            swap_bytestring(parts[1]),
            swap_bytestring(parts[2]),
            parts[3],
            parts[4]
        ]
    )

    return previous_id == swapped_id


@azure_ds_telemetry_reporter
def get_boot_telemetry():
    """Report timestamps related to kernel initialization and systemd
       activation of cloud-init"""
    if not distros.uses_systemd():
        raise RuntimeError(
            "distro not using systemd, skipping boot telemetry")

    LOG.debug("Collecting boot telemetry")
    try:
        kernel_start = float(time.time()) - float(util.uptime())
    except ValueError as e:
        raise RuntimeError(
            "Failed to determine kernel start timestamp"
        ) from e

    try:
        out, _ = subp.subp(['/bin/systemctl',
                            'show', '-p',
                            'UserspaceTimestampMonotonic'],
                           capture=True)
        tsm = None
        if out and '=' in out:
            tsm = out.split("=")[1]

        if not tsm:
            raise RuntimeError("Failed to parse "
                               "UserspaceTimestampMonotonic from systemd")

        user_start = kernel_start + (float(tsm) / 1000000)
    except subp.ProcessExecutionError as e:
        raise RuntimeError(
            "Failed to get UserspaceTimestampMonotonic: %s" % e
        ) from e
    except ValueError as e:
        raise RuntimeError(
            "Failed to parse UserspaceTimestampMonotonic from systemd: %s" % e
        ) from e

    try:
        out, _ = subp.subp(['/bin/systemctl', 'show',
                            'cloud-init-local', '-p',
                            'InactiveExitTimestampMonotonic'],
                           capture=True)
        tsm = None
        if out and '=' in out:
            tsm = out.split("=")[1]
        if not tsm:
            raise RuntimeError("Failed to parse "
                               "InactiveExitTimestampMonotonic from systemd")

        cloudinit_activation = kernel_start + (float(tsm) / 1000000)
    except subp.ProcessExecutionError as e:
        raise RuntimeError(
            "Failed to get InactiveExitTimestampMonotonic: %s" % e
        ) from e
    except ValueError as e:
        raise RuntimeError(
            "Failed to parse InactiveExitTimestampMonotonic from systemd: %s"
            % e
        ) from e

    evt = events.ReportingEvent(
        BOOT_EVENT_TYPE, 'boot-telemetry',
        "kernel_start=%s user_start=%s cloudinit_activation=%s" %
        (datetime.utcfromtimestamp(kernel_start).isoformat() + 'Z',
         datetime.utcfromtimestamp(user_start).isoformat() + 'Z',
         datetime.utcfromtimestamp(cloudinit_activation).isoformat() + 'Z'),
        events.DEFAULT_EVENT_ORIGIN)
    events.report_event(evt)

    # return the event for unit testing purpose
    return evt


@azure_ds_telemetry_reporter
def get_system_info():
    """Collect and report system information"""
    info = util.system_info()
    evt = events.ReportingEvent(
        SYSTEMINFO_EVENT_TYPE, 'system information',
        "cloudinit_version=%s, kernel_version=%s, variant=%s, "
        "distro_name=%s, distro_version=%s, flavor=%s, "
        "python_version=%s" %
        (version.version_string(), info['release'], info['variant'],
         info['dist'][0], info['dist'][1], info['dist'][2],
         info['python']), events.DEFAULT_EVENT_ORIGIN)
    events.report_event(evt)

    # return the event for unit testing purpose
    return evt


def report_diagnostic_event(
        msg: str, *, logger_func=None) -> events.ReportingEvent:
    """Report a diagnostic event"""
    if callable(logger_func):
        logger_func(msg)
    evt = events.ReportingEvent(
        DIAGNOSTIC_EVENT_TYPE, 'diagnostic message',
        msg, events.DEFAULT_EVENT_ORIGIN)
    events.report_event(evt, excluded_handler_types={"log"})

    # return the event for unit testing purpose
    return evt


def report_compressed_event(event_name, event_content):
    """Report a compressed event"""
    compressed_data = base64.encodebytes(zlib.compress(event_content))
    event_data = {"encoding": "gz+b64",
                  "data": compressed_data.decode('ascii')}
    evt = events.ReportingEvent(
        COMPRESSED_EVENT_TYPE, event_name,
        json.dumps(event_data),
        events.DEFAULT_EVENT_ORIGIN)
    events.report_event(evt,
                        excluded_handler_types={"log", "print", "webhook"})

    # return the event for unit testing purpose
    return evt


@azure_ds_telemetry_reporter
def push_log_to_kvp(file_name=CFG_BUILTIN['def_log_file']):
    """Push a portion of cloud-init.log file or the whole file to KVP
    based on the file size.
    The first time this function is called after VM boot, It will push the last
    n bytes of the log file such that n < MAX_LOG_TO_KVP_LENGTH
    If called again on the same boot, it continues from where it left off.
    In addition to cloud-init.log, dmesg log will also be collected."""

    start_index = get_last_log_byte_pushed_to_kvp_index()

    LOG.debug("Dumping cloud-init.log file to KVP")
    try:
        with open(file_name, "rb") as f:
            f.seek(0, os.SEEK_END)
            seek_index = max(f.tell() - MAX_LOG_TO_KVP_LENGTH, start_index)
            report_diagnostic_event(
                "Dumping last {0} bytes of cloud-init.log file to KVP starting"
                " from index: {1}".format(f.tell() - seek_index, seek_index),
                logger_func=LOG.debug)
            f.seek(seek_index, os.SEEK_SET)
            report_compressed_event("cloud-init.log", f.read())
            util.write_file(LOG_PUSHED_TO_KVP_INDEX_FILE, str(f.tell()))
    except Exception as ex:
        report_diagnostic_event(
            "Exception when dumping log file: %s" % repr(ex),
            logger_func=LOG.warning)

    LOG.debug("Dumping dmesg log to KVP")
    try:
        out, _ = subp.subp(['dmesg'], decode=False, capture=True)
        report_compressed_event("dmesg", out)
    except Exception as ex:
        report_diagnostic_event(
            "Exception when dumping dmesg log: %s" % repr(ex),
            logger_func=LOG.warning)


@azure_ds_telemetry_reporter
def get_last_log_byte_pushed_to_kvp_index():
    try:
        with open(LOG_PUSHED_TO_KVP_INDEX_FILE, "r") as f:
            return int(f.read())
    except IOError as e:
        if e.errno != ENOENT:
            report_diagnostic_event("Reading LOG_PUSHED_TO_KVP_INDEX_FILE"
                                    " failed: %s." % repr(e),
                                    logger_func=LOG.warning)
    except ValueError as e:
        report_diagnostic_event("Invalid value in LOG_PUSHED_TO_KVP_INDEX_FILE"
                                ": %s." % repr(e),
                                logger_func=LOG.warning)
    except Exception as e:
        report_diagnostic_event("Failed to get the last log byte pushed to KVP"
                                ": %s." % repr(e), logger_func=LOG.warning)
    return 0


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


@azure_ds_telemetry_reporter
def http_with_retries(url, **kwargs) -> str:
    """Wrapper around url_helper.readurl() with custom telemetry logging
    that url_helper.readurl() does not provide.
    """
    exc = None

    max_readurl_attempts = 240
    default_readurl_timeout = 5
    periodic_logging_attempts = 12

    if 'timeout' not in kwargs:
        kwargs['timeout'] = default_readurl_timeout

    # remove kwargs that cause url_helper.readurl to retry,
    # since we are already implementing our own retry logic.
    if kwargs.pop('retries', None):
        LOG.warning(
            'Ignoring retries kwarg passed in for '
            'communication with Azure endpoint.')
    if kwargs.pop('infinite', None):
        LOG.warning(
            'Ignoring infinite kwarg passed in for communication '
            'with Azure endpoint.')

    for attempt in range(1, max_readurl_attempts + 1):
        try:
            ret = url_helper.readurl(url, **kwargs)

            report_diagnostic_event(
                'Successful HTTP request with Azure endpoint %s after '
                '%d attempts' % (url, attempt),
                logger_func=LOG.debug)

            return ret

        except Exception as e:
            exc = e
            if attempt % periodic_logging_attempts == 0:
                report_diagnostic_event(
                    'Failed HTTP request with Azure endpoint %s during '
                    'attempt %d with exception: %s' %
                    (url, attempt, e),
                    logger_func=LOG.debug)

    raise exc


class AzureEndpointHttpClient:

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
        return http_with_retries(url, headers=headers)

    def post(self, url, data=None, extra_headers=None):
        headers = self.headers
        if extra_headers is not None:
            headers = self.headers.copy()
            headers.update(extra_headers)
        return http_with_retries(
            url, data=data, headers=headers)


class InvalidGoalStateXMLException(Exception):
    """Raised when GoalState XML is invalid or has missing data."""


class GoalState:

    def __init__(
            self,
            unparsed_xml: str,
            azure_endpoint_client: AzureEndpointHttpClient,
            need_certificate: bool = True) -> None:
        """Parses a GoalState XML string and returns a GoalState object.

        @param unparsed_xml: string representing a GoalState XML.
        @param azure_endpoint_client: instance of AzureEndpointHttpClient.
        @param need_certificate: switch to know if certificates is needed.
        @return: GoalState object representing the GoalState XML string.
        """
        self.azure_endpoint_client = azure_endpoint_client

        try:
            self.root = ElementTree.fromstring(unparsed_xml)
        except ElementTree.ParseError as e:
            report_diagnostic_event(
                'Failed to parse GoalState XML: %s' % e,
                logger_func=LOG.warning)
            raise

        self.container_id = self._text_from_xpath('./Container/ContainerId')
        self.instance_id = self._text_from_xpath(
            './Container/RoleInstanceList/RoleInstance/InstanceId')
        self.incarnation = self._text_from_xpath('./Incarnation')

        for attr in ("container_id", "instance_id", "incarnation"):
            if getattr(self, attr) is None:
                msg = 'Missing %s in GoalState XML' % attr
                report_diagnostic_event(msg, logger_func=LOG.warning)
                raise InvalidGoalStateXMLException(msg)

        self.certificates_xml = None
        url = self._text_from_xpath(
            './Container/RoleInstanceList/RoleInstance'
            '/Configuration/Certificates')
        if url is not None and need_certificate:
            with events.ReportEventStack(
                    name="get-certificates-xml",
                    description="get certificates xml",
                    parent=azure_ds_reporter):
                self.certificates_xml = \
                    self.azure_endpoint_client.get(
                        url, secure=True).contents
                if self.certificates_xml is None:
                    raise InvalidGoalStateXMLException(
                        'Azure endpoint returned empty certificates xml.')

    def _text_from_xpath(self, xpath):
        element = self.root.find(xpath)
        if element is not None:
            return element.text
        return None


class OpenSSLManager:

    certificate_names = {
        'private_key': 'TransportPrivate.pem',
        'certificate': 'TransportCert.pem',
    }

    def __init__(self):
        self.tmpdir = temp_utils.mkdtemp()
        self._certificate = None
        self.generate_certificate()

    def clean_up(self):
        util.del_dir(self.tmpdir)

    @property
    def certificate(self):
        return self._certificate

    @certificate.setter
    def certificate(self, value):
        self._certificate = value

    @azure_ds_telemetry_reporter
    def generate_certificate(self):
        LOG.debug('Generating certificate for communication with fabric...')
        if self.certificate is not None:
            LOG.debug('Certificate already generated.')
            return
        with cd(self.tmpdir):
            subp.subp([
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
        result, _ = subp.subp(cmd, data=cert)
        return result

    @azure_ds_telemetry_reporter
    def _get_ssh_key_from_cert(self, certificate):
        pub_key = self._run_x509_action('-pubkey', certificate)
        keygen_cmd = ['ssh-keygen', '-i', '-m', 'PKCS8', '-f', '/dev/stdin']
        ssh_key, _ = subp.subp(keygen_cmd, data=pub_key)
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
            out, _ = subp.subp(
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


class GoalStateHealthReporter:

    HEALTH_REPORT_XML_TEMPLATE = textwrap.dedent('''\
        <?xml version="1.0" encoding="utf-8"?>
        <Health xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xmlns:xsd="http://www.w3.org/2001/XMLSchema">
          <GoalStateIncarnation>{incarnation}</GoalStateIncarnation>
          <Container>
            <ContainerId>{container_id}</ContainerId>
            <RoleInstanceList>
              <Role>
                <InstanceId>{instance_id}</InstanceId>
                <Health>
                  <State>{health_status}</State>
                  {health_detail_subsection}
                </Health>
              </Role>
            </RoleInstanceList>
          </Container>
        </Health>
        ''')

    HEALTH_DETAIL_SUBSECTION_XML_TEMPLATE = textwrap.dedent('''\
        <Details>
          <SubStatus>{health_substatus}</SubStatus>
          <Description>{health_description}</Description>
        </Details>
        ''')

    PROVISIONING_SUCCESS_STATUS = 'Ready'
    PROVISIONING_NOT_READY_STATUS = 'NotReady'
    PROVISIONING_FAILURE_SUBSTATUS = 'ProvisioningFailed'

    HEALTH_REPORT_DESCRIPTION_TRIM_LEN = 512

    def __init__(
            self, goal_state: GoalState,
            azure_endpoint_client: AzureEndpointHttpClient,
            endpoint: str) -> None:
        """Creates instance that will report provisioning status to an endpoint

        @param goal_state: An instance of class GoalState that contains
            goal state info such as incarnation, container id, and instance id.
            These 3 values are needed when reporting the provisioning status
            to Azure
        @param azure_endpoint_client: Instance of class AzureEndpointHttpClient
        @param endpoint: Endpoint (string) where the provisioning status report
            will be sent to
        @return: Instance of class GoalStateHealthReporter
        """
        self._goal_state = goal_state
        self._azure_endpoint_client = azure_endpoint_client
        self._endpoint = endpoint

    @azure_ds_telemetry_reporter
    def send_ready_signal(self) -> None:
        document = self.build_report(
            incarnation=self._goal_state.incarnation,
            container_id=self._goal_state.container_id,
            instance_id=self._goal_state.instance_id,
            status=self.PROVISIONING_SUCCESS_STATUS)
        LOG.debug('Reporting ready to Azure fabric.')
        try:
            self._post_health_report(document=document)
        except Exception as e:
            report_diagnostic_event(
                "exception while reporting ready: %s" % e,
                logger_func=LOG.error)
            raise

        LOG.info('Reported ready to Azure fabric.')

    @azure_ds_telemetry_reporter
    def send_failure_signal(self, description: str) -> None:
        document = self.build_report(
            incarnation=self._goal_state.incarnation,
            container_id=self._goal_state.container_id,
            instance_id=self._goal_state.instance_id,
            status=self.PROVISIONING_NOT_READY_STATUS,
            substatus=self.PROVISIONING_FAILURE_SUBSTATUS,
            description=description)
        try:
            self._post_health_report(document=document)
        except Exception as e:
            msg = "exception while reporting failure: %s" % e
            report_diagnostic_event(msg, logger_func=LOG.error)
            raise

        LOG.warning('Reported failure to Azure fabric.')

    def build_report(
            self, incarnation: str, container_id: str, instance_id: str,
            status: str, substatus=None, description=None) -> str:
        health_detail = ''
        if substatus is not None:
            health_detail = self.HEALTH_DETAIL_SUBSECTION_XML_TEMPLATE.format(
                health_substatus=escape(substatus),
                health_description=escape(
                    description[:self.HEALTH_REPORT_DESCRIPTION_TRIM_LEN]))

        health_report = self.HEALTH_REPORT_XML_TEMPLATE.format(
            incarnation=escape(str(incarnation)),
            container_id=escape(container_id),
            instance_id=escape(instance_id),
            health_status=escape(status),
            health_detail_subsection=health_detail)

        return health_report

    @azure_ds_telemetry_reporter
    def _post_health_report(self, document: str) -> None:
        push_log_to_kvp()

        # Whenever report_diagnostic_event(diagnostic_msg) is invoked in code,
        # the diagnostic messages are written to special files
        # (/var/opt/hyperv/.kvp_pool_*) as Hyper-V KVP messages.
        # Hyper-V KVP message communication is done through these files,
        # and KVP functionality is used to communicate and share diagnostic
        # info with the Azure Host.
        # The Azure Host will collect the VM's Hyper-V KVP diagnostic messages
        # when cloud-init reports to fabric.
        # When the Azure Host receives the health report signal, it will only
        # collect and process whatever KVP diagnostic messages have been
        # written to the KVP files.
        # KVP messages that are published after the Azure Host receives the
        # signal are ignored and unprocessed, so yield this thread to the
        # Hyper-V KVP Reporting thread so that they are written.
        # time.sleep(0) is a low-cost and proven method to yield the scheduler
        # and ensure that events are flushed.
        # See HyperVKvpReportingHandler class, which is a multi-threaded
        # reporting handler that writes to the special KVP files.
        time.sleep(0)

        LOG.debug('Sending health report to Azure fabric.')
        url = "http://{}/machine?comp=health".format(self._endpoint)
        self._azure_endpoint_client.post(
            url,
            data=document,
            extra_headers={'Content-Type': 'text/xml; charset=utf-8'})
        LOG.debug('Successfully sent health report to Azure fabric')


class WALinuxAgentShim:

    def __init__(self, fallback_lease_file=None, dhcp_options=None):
        LOG.debug('WALinuxAgentShim instantiated, fallback_lease_file=%s',
                  fallback_lease_file)
        self.dhcpoptions = dhcp_options
        self._endpoint = None
        self.openssl_manager = None
        self.azure_endpoint_client = None
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
            except ValueError as e:
                raise ValueError(
                    '{_file} is not valid JSON data'.format(_file=hook_file)
                ) from e
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
        """Finds and returns the Azure endpoint using various methods.

        The Azure endpoint is searched in the following order:
        1. Endpoint from dhcp options (dhcp option 245).
        2. Endpoint from networkd.
        3. Endpoint from dhclient hook json.
        4. Endpoint from fallback lease file.
        5. The default Azure endpoint.

        @param fallback_lease_file: Fallback lease file that will be used
            during endpoint search.
        @param dhcp245: dhcp options that will be used during endpoint search.
        @return: Azure endpoint IP address.
        """
        value = None

        if dhcp245 is not None:
            value = dhcp245
            LOG.debug("Using Azure Endpoint from dhcp options")
        if value is None:
            report_diagnostic_event(
                'No Azure endpoint from dhcp options. '
                'Finding Azure endpoint from networkd...',
                logger_func=LOG.debug)
            value = WALinuxAgentShim._networkd_get_value_from_leases()
        if value is None:
            # Option-245 stored in /run/cloud-init/dhclient.hooks/<ifc>.json
            # a dhclient exit hook that calls cloud-init-dhclient-hook
            report_diagnostic_event(
                'No Azure endpoint from networkd. '
                'Finding Azure endpoint from hook json...',
                logger_func=LOG.debug)
            dhcp_options = WALinuxAgentShim._load_dhclient_json()
            value = WALinuxAgentShim._get_value_from_dhcpoptions(dhcp_options)
        if value is None:
            # Fallback and check the leases file if unsuccessful
            report_diagnostic_event(
                'No Azure endpoint from dhclient logs. '
                'Unable to find endpoint in dhclient logs. '
                'Falling back to check lease files',
                logger_func=LOG.debug)
            if fallback_lease_file is None:
                report_diagnostic_event(
                    'No fallback lease file was specified.',
                    logger_func=LOG.warning)
                value = None
            else:
                report_diagnostic_event(
                    'Looking for endpoint in lease file %s'
                    % fallback_lease_file, logger_func=LOG.debug)
                value = WALinuxAgentShim._get_value_from_leases_file(
                    fallback_lease_file)
        if value is None:
            value = DEFAULT_WIRESERVER_ENDPOINT
            report_diagnostic_event(
                'No lease found; using default endpoint: %s' % value,
                logger_func=LOG.warning)

        endpoint_ip_address = WALinuxAgentShim.get_ip_from_lease_value(value)
        report_diagnostic_event(
            'Azure endpoint found at %s' % endpoint_ip_address,
            logger_func=LOG.debug)
        return endpoint_ip_address

    @azure_ds_telemetry_reporter
    def register_with_azure_and_fetch_data(self, pubkey_info=None) -> dict:
        """Gets the VM's GoalState from Azure, uses the GoalState information
        to report ready/send the ready signal/provisioning complete signal to
        Azure, and then uses pubkey_info to filter and obtain the user's
        pubkeys from the GoalState.

        @param pubkey_info: List of pubkey values and fingerprints which are
            used to filter and obtain the user's pubkey values from the
            GoalState.
        @return: The list of user's authorized pubkey values.
        """
        http_client_certificate = None
        if self.openssl_manager is None and pubkey_info is not None:
            self.openssl_manager = OpenSSLManager()
            http_client_certificate = self.openssl_manager.certificate
        if self.azure_endpoint_client is None:
            self.azure_endpoint_client = AzureEndpointHttpClient(
                http_client_certificate)
        goal_state = self._fetch_goal_state_from_azure(
            need_certificate=http_client_certificate is not None
        )
        ssh_keys = None
        if pubkey_info is not None:
            ssh_keys = self._get_user_pubkeys(goal_state, pubkey_info)
        health_reporter = GoalStateHealthReporter(
            goal_state, self.azure_endpoint_client, self.endpoint)
        health_reporter.send_ready_signal()
        return {'public-keys': ssh_keys}

    @azure_ds_telemetry_reporter
    def register_with_azure_and_report_failure(self, description: str) -> None:
        """Gets the VM's GoalState from Azure, uses the GoalState information
        to report failure/send provisioning failure signal to Azure.

        @param: user visible error description of provisioning failure.
        """
        if self.azure_endpoint_client is None:
            self.azure_endpoint_client = AzureEndpointHttpClient(None)
        goal_state = self._fetch_goal_state_from_azure(need_certificate=False)
        health_reporter = GoalStateHealthReporter(
            goal_state, self.azure_endpoint_client, self.endpoint)
        health_reporter.send_failure_signal(description=description)

    @azure_ds_telemetry_reporter
    def _fetch_goal_state_from_azure(
            self,
            need_certificate: bool) -> GoalState:
        """Fetches the GoalState XML from the Azure endpoint, parses the XML,
        and returns a GoalState object.

        @param need_certificate: switch to know if certificates is needed.
        @return: GoalState object representing the GoalState XML
        """
        unparsed_goal_state_xml = self._get_raw_goal_state_xml_from_azure()
        return self._parse_raw_goal_state_xml(
            unparsed_goal_state_xml,
            need_certificate
        )

    @azure_ds_telemetry_reporter
    def _get_raw_goal_state_xml_from_azure(self) -> str:
        """Fetches the GoalState XML from the Azure endpoint and returns
        the XML as a string.

        @return: GoalState XML string
        """

        LOG.info('Registering with Azure...')
        url = 'http://{}/machine/?comp=goalstate'.format(self.endpoint)
        try:
            with events.ReportEventStack(
                    name="goalstate-retrieval",
                    description="retrieve goalstate",
                    parent=azure_ds_reporter):
                response = self.azure_endpoint_client.get(url)
        except Exception as e:
            report_diagnostic_event(
                'failed to register with Azure and fetch GoalState XML: %s'
                % e, logger_func=LOG.warning)
            raise
        LOG.debug('Successfully fetched GoalState XML.')
        return response.contents

    @azure_ds_telemetry_reporter
    def _parse_raw_goal_state_xml(
            self,
            unparsed_goal_state_xml: str,
            need_certificate: bool) -> GoalState:
        """Parses a GoalState XML string and returns a GoalState object.

        @param unparsed_goal_state_xml: GoalState XML string
        @param need_certificate: switch to know if certificates is needed.
        @return: GoalState object representing the GoalState XML
        """
        try:
            goal_state = GoalState(
                unparsed_goal_state_xml,
                self.azure_endpoint_client,
                need_certificate
            )
        except Exception as e:
            report_diagnostic_event(
                'Error processing GoalState XML: %s' % e,
                logger_func=LOG.warning)
            raise
        msg = ', '.join([
            'GoalState XML container id: %s' % goal_state.container_id,
            'GoalState XML instance id: %s' % goal_state.instance_id,
            'GoalState XML incarnation: %s' % goal_state.incarnation])
        report_diagnostic_event(msg, logger_func=LOG.debug)
        return goal_state

    @azure_ds_telemetry_reporter
    def _get_user_pubkeys(
            self, goal_state: GoalState, pubkey_info: list) -> list:
        """Gets and filters the VM admin user's authorized pubkeys.

        The admin user in this case is the username specified as "admin"
        when deploying VMs on Azure.
        See https://docs.microsoft.com/en-us/cli/azure/vm#az-vm-create.
        cloud-init expects a straightforward array of keys to be dropped
        into the admin user's authorized_keys file. Azure control plane exposes
        multiple public keys to the VM via wireserver. Select just the
        admin user's key(s) and return them, ignoring any other certs.

        @param goal_state: GoalState object. The GoalState object contains
            a certificate XML, which contains both the VM user's authorized
            pubkeys and other non-user pubkeys, which are used for
            MSI and protected extension handling.
        @param pubkey_info: List of VM user pubkey dicts that were previously
            obtained from provisioning data.
            Each pubkey dict in this list can either have the format
            pubkey['value'] or pubkey['fingerprint'].
            Each pubkey['fingerprint'] in the list is used to filter
            and obtain the actual pubkey value from the GoalState
            certificates XML.
            Each pubkey['value'] requires no further processing and is
            immediately added to the return list.
        @return: A list of the VM user's authorized pubkey values.
        """
        ssh_keys = []
        if goal_state.certificates_xml is not None and pubkey_info is not None:
            LOG.debug('Certificate XML found; parsing out public keys.')
            keys_by_fingerprint = self.openssl_manager.parse_certificates(
                goal_state.certificates_xml)
            ssh_keys = self._filter_pubkeys(keys_by_fingerprint, pubkey_info)
        return ssh_keys

    @staticmethod
    def _filter_pubkeys(keys_by_fingerprint: dict, pubkey_info: list) -> list:
        """ Filter and return only the user's actual pubkeys.

        @param keys_by_fingerprint: pubkey fingerprint -> pubkey value dict
            that was obtained from GoalState Certificates XML. May contain
            non-user pubkeys.
        @param pubkey_info: List of VM user pubkeys. Pubkey values are added
            to the return list without further processing. Pubkey fingerprints
            are used to filter and obtain the actual pubkey values from
            keys_by_fingerprint.
        @return: A list of the VM user's authorized pubkey values.
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
def get_metadata_from_fabric(fallback_lease_file=None, dhcp_opts=None,
                             pubkey_info=None):
    shim = WALinuxAgentShim(fallback_lease_file=fallback_lease_file,
                            dhcp_options=dhcp_opts)
    try:
        return shim.register_with_azure_and_fetch_data(pubkey_info=pubkey_info)
    finally:
        shim.clean_up()


@azure_ds_telemetry_reporter
def report_failure_to_fabric(fallback_lease_file=None, dhcp_opts=None,
                             description=None):
    shim = WALinuxAgentShim(fallback_lease_file=fallback_lease_file,
                            dhcp_options=dhcp_opts)
    if not description:
        description = DEFAULT_REPORT_FAILURE_USER_VISIBLE_MESSAGE
    try:
        shim.register_with_azure_and_report_failure(
            description=description)
    finally:
        shim.clean_up()


def dhcp_log_cb(out, err):
    report_diagnostic_event(
        "dhclient output stream: %s" % out, logger_func=LOG.debug)
    report_diagnostic_event(
        "dhclient error stream: %s" % err, logger_func=LOG.debug)


class EphemeralDHCPv4WithReporting:
    def __init__(self, reporter, nic=None):
        self.reporter = reporter
        self.ephemeralDHCPv4 = EphemeralDHCPv4(
            iface=nic, dhcp_log_func=dhcp_log_cb)

    def __enter__(self):
        with events.ReportEventStack(
                name="obtain-dhcp-lease",
                description="obtain dhcp lease",
                parent=self.reporter):
            return self.ephemeralDHCPv4.__enter__()

    def __exit__(self, excp_type, excp_value, excp_traceback):
        self.ephemeralDHCPv4.__exit__(
            excp_type, excp_value, excp_traceback)


# vi: ts=4 expandtab
