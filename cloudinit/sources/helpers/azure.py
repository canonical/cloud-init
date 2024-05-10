# This file is part of cloud-init. See LICENSE file for license information.

# TODO: Importing this file without first importing
# cloudinit.sources.azure.errors will result in a circular import.
import base64
import json
import logging
import os
import re
import textwrap
import zlib
from contextlib import contextmanager
from datetime import datetime
from time import sleep, time
from typing import Callable, List, Optional, TypeVar, Union
from xml.etree import ElementTree  # nosec B405
from xml.sax.saxutils import escape  # nosec B406

from cloudinit import distros, subp, temp_utils, url_helper, util, version
from cloudinit.reporting import events
from cloudinit.sources.azure import errors

LOG = logging.getLogger(__name__)

# Default Wireserver endpoint (if not found in DHCP option 245).
DEFAULT_WIRESERVER_ENDPOINT = "168.63.129.16"

BOOT_EVENT_TYPE = "boot-telemetry"
SYSTEMINFO_EVENT_TYPE = "system-info"
DIAGNOSTIC_EVENT_TYPE = "diagnostic"
COMPRESSED_EVENT_TYPE = "compressed"
azure_ds_reporter = events.ReportEventStack(
    name="azure-ds",
    description="initialize reporter for azure ds",
    reporting_enabled=True,
)

T = TypeVar("T")


def azure_ds_telemetry_reporter(func: Callable[..., T]) -> Callable[..., T]:
    def impl(*args, **kwargs):
        with events.ReportEventStack(
            name=func.__name__,
            description=func.__name__,
            parent=azure_ds_reporter,
        ):
            return func(*args, **kwargs)

    return impl


@azure_ds_telemetry_reporter
def get_boot_telemetry():
    """Report timestamps related to kernel initialization and systemd
    activation of cloud-init"""
    if not distros.uses_systemd():
        raise RuntimeError("distro not using systemd, skipping boot telemetry")

    LOG.debug("Collecting boot telemetry")
    try:
        kernel_start = float(time()) - float(util.uptime())
    except ValueError as e:
        raise RuntimeError("Failed to determine kernel start timestamp") from e

    try:
        out, _ = subp.subp(
            ["systemctl", "show", "-p", "UserspaceTimestampMonotonic"],
            capture=True,
        )
        tsm = None
        if out and "=" in out:
            tsm = out.split("=")[1]

        if not tsm:
            raise RuntimeError(
                "Failed to parse UserspaceTimestampMonotonic from systemd"
            )

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
        out, _ = subp.subp(
            [
                "systemctl",
                "show",
                "cloud-init-local",
                "-p",
                "InactiveExitTimestampMonotonic",
            ],
            capture=True,
        )
        tsm = None
        if out and "=" in out:
            tsm = out.split("=")[1]
        if not tsm:
            raise RuntimeError(
                "Failed to parse InactiveExitTimestampMonotonic from systemd"
            )

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
        BOOT_EVENT_TYPE,
        "boot-telemetry",
        "kernel_start=%s user_start=%s cloudinit_activation=%s"
        % (
            datetime.utcfromtimestamp(kernel_start).isoformat() + "Z",
            datetime.utcfromtimestamp(user_start).isoformat() + "Z",
            datetime.utcfromtimestamp(cloudinit_activation).isoformat() + "Z",
        ),
        events.DEFAULT_EVENT_ORIGIN,
    )
    events.report_event(evt)

    # return the event for unit testing purpose
    return evt


@azure_ds_telemetry_reporter
def get_system_info():
    """Collect and report system information"""
    info = util.system_info()
    evt = events.ReportingEvent(
        SYSTEMINFO_EVENT_TYPE,
        "system information",
        "cloudinit_version=%s, kernel_version=%s, variant=%s, "
        "distro_name=%s, distro_version=%s, flavor=%s, "
        "python_version=%s"
        % (
            version.version_string(),
            info["release"],
            info["variant"],
            info["dist"][0],
            info["dist"][1],
            info["dist"][2],
            info["python"],
        ),
        events.DEFAULT_EVENT_ORIGIN,
    )
    events.report_event(evt)

    # return the event for unit testing purpose
    return evt


def report_diagnostic_event(
    msg: str, *, logger_func=None
) -> events.ReportingEvent:
    """Report a diagnostic event"""
    if callable(logger_func):
        logger_func(msg)
    evt = events.ReportingEvent(
        DIAGNOSTIC_EVENT_TYPE,
        "diagnostic message",
        msg,
        events.DEFAULT_EVENT_ORIGIN,
    )
    events.report_event(evt, excluded_handler_types={"log"})

    # return the event for unit testing purpose
    return evt


def report_compressed_event(event_name, event_content):
    """Report a compressed event"""
    compressed_data = base64.encodebytes(zlib.compress(event_content))
    event_data = {
        "encoding": "gz+b64",
        "data": compressed_data.decode("ascii"),
    }
    evt = events.ReportingEvent(
        COMPRESSED_EVENT_TYPE,
        event_name,
        json.dumps(event_data),
        events.DEFAULT_EVENT_ORIGIN,
    )
    events.report_event(
        evt, excluded_handler_types={"log", "print", "webhook"}
    )

    # return the event for unit testing purpose
    return evt


@azure_ds_telemetry_reporter
def report_dmesg_to_kvp():
    """Report dmesg to KVP."""
    LOG.debug("Dumping dmesg log to KVP")
    try:
        out, _ = subp.subp(["dmesg"], decode=False, capture=True)
        report_compressed_event("dmesg", out)
    except Exception as ex:
        report_diagnostic_event(
            "Exception when dumping dmesg log: %s" % repr(ex),
            logger_func=LOG.warning,
        )


@contextmanager
def cd(newdir):
    prevdir = os.getcwd()
    os.chdir(os.path.expanduser(newdir))
    try:
        yield
    finally:
        os.chdir(prevdir)


@azure_ds_telemetry_reporter
def http_with_retries(
    url: str,
    *,
    headers: dict,
    data: Optional[bytes] = None,
    retry_sleep: int = 5,
    timeout_minutes: int = 20,
) -> url_helper.UrlResponse:
    """Readurl wrapper for querying wireserver.

    :param retry_sleep: Time to sleep before retrying.
    :param timeout_minutes: Retry up to specified number of minutes.
    :raises UrlError: on error fetching data.
    """
    timeout = timeout_minutes * 60 + time()

    attempt = 0
    response = None
    while not response:
        attempt += 1
        try:
            response = url_helper.readurl(
                url, headers=headers, data=data, timeout=(5, 60)
            )
            break
        except url_helper.UrlError as e:
            report_diagnostic_event(
                "Failed HTTP request with Azure endpoint %s during "
                "attempt %d with exception: %s (code=%r headers=%r)"
                % (url, attempt, e, e.code, e.headers),
                logger_func=LOG.debug,
            )
            # Raise exception if we're out of time or network is unreachable.
            # If network is unreachable:
            # - retries will not resolve the situation
            # - for reporting ready for PPS, this generally means VM was put
            #   to sleep or network interface was unplugged before we see
            #   the call complete successfully.
            if (
                time() + retry_sleep >= timeout
                or "Network is unreachable" in str(e)
            ):
                raise

        sleep(retry_sleep)

    report_diagnostic_event(
        "Successful HTTP request with Azure endpoint %s after "
        "%d attempts" % (url, attempt),
        logger_func=LOG.debug,
    )
    return response


def build_minimal_ovf(
    username: str, hostname: str, disableSshPwd: str
) -> bytes:
    OVF_ENV_TEMPLATE = textwrap.dedent(
        """\
        <ns0:Environment xmlns:ns0="http://schemas.dmtf.org/ovf/environment/1"
         xmlns:ns1="http://schemas.microsoft.com/windowsazure"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
          <ns1:ProvisioningSection>
            <ns1:Version>1.0</ns1:Version>
            <ns1:LinuxProvisioningConfigurationSet>
              <ns1:ConfigurationSetType>LinuxProvisioningConfiguration
              </ns1:ConfigurationSetType>
              <ns1:UserName>{username}</ns1:UserName>
              <ns1:DisableSshPasswordAuthentication>{disableSshPwd}
              </ns1:DisableSshPasswordAuthentication>
              <ns1:HostName>{hostname}</ns1:HostName>
            </ns1:LinuxProvisioningConfigurationSet>
          </ns1:ProvisioningSection>
          <ns1:PlatformSettingsSection>
            <ns1:Version>1.0</ns1:Version>
            <ns1:PlatformSettings>
              <ns1:ProvisionGuestAgent>true</ns1:ProvisionGuestAgent>
            </ns1:PlatformSettings>
          </ns1:PlatformSettingsSection>
        </ns0:Environment>
        """
    )
    ret = OVF_ENV_TEMPLATE.format(
        username=username, hostname=hostname, disableSshPwd=disableSshPwd
    )
    return ret.encode("utf-8")


class AzureEndpointHttpClient:
    headers = {
        "x-ms-agent-name": "WALinuxAgent",
        "x-ms-version": "2012-11-30",
    }

    def __init__(self, certificate):
        self.extra_secure_headers = {
            "x-ms-cipher-name": "DES_EDE3_CBC",
            "x-ms-guest-agent-public-x509-cert": certificate,
        }

    def get(self, url, secure=False) -> url_helper.UrlResponse:
        headers = self.headers
        if secure:
            headers = self.headers.copy()
            headers.update(self.extra_secure_headers)
        return http_with_retries(url, headers=headers)

    def post(
        self, url, data: Optional[bytes] = None, extra_headers=None
    ) -> url_helper.UrlResponse:
        headers = self.headers
        if extra_headers is not None:
            headers = self.headers.copy()
            headers.update(extra_headers)
        return http_with_retries(url, data=data, headers=headers)


class InvalidGoalStateXMLException(Exception):
    """Raised when GoalState XML is invalid or has missing data."""


class GoalState:
    def __init__(
        self,
        unparsed_xml: Union[str, bytes],
        azure_endpoint_client: AzureEndpointHttpClient,
        need_certificate: bool = True,
    ) -> None:
        """Parses a GoalState XML string and returns a GoalState object.

        @param unparsed_xml: string representing a GoalState XML.
        @param azure_endpoint_client: instance of AzureEndpointHttpClient.
        @param need_certificate: switch to know if certificates is needed.
        @return: GoalState object representing the GoalState XML string.
        """
        self.azure_endpoint_client = azure_endpoint_client

        try:
            self.root = ElementTree.fromstring(unparsed_xml)  # nosec B314
        except ElementTree.ParseError as e:
            report_diagnostic_event(
                "Failed to parse GoalState XML: %s" % e,
                logger_func=LOG.warning,
            )
            raise

        self.container_id = self._text_from_xpath("./Container/ContainerId")
        self.instance_id = self._text_from_xpath(
            "./Container/RoleInstanceList/RoleInstance/InstanceId"
        )
        self.incarnation = self._text_from_xpath("./Incarnation")

        for attr in ("container_id", "instance_id", "incarnation"):
            if getattr(self, attr) is None:
                msg = "Missing %s in GoalState XML" % attr
                report_diagnostic_event(msg, logger_func=LOG.warning)
                raise InvalidGoalStateXMLException(msg)

        self.certificates_xml = None
        url = self._text_from_xpath(
            "./Container/RoleInstanceList/RoleInstance"
            "/Configuration/Certificates"
        )
        if url is not None and need_certificate:
            with events.ReportEventStack(
                name="get-certificates-xml",
                description="get certificates xml",
                parent=azure_ds_reporter,
            ):
                self.certificates_xml = self.azure_endpoint_client.get(
                    url, secure=True
                ).contents
                if self.certificates_xml is None:
                    raise InvalidGoalStateXMLException(
                        "Azure endpoint returned empty certificates xml."
                    )

    def _text_from_xpath(self, xpath):
        element = self.root.find(xpath)
        if element is not None:
            return element.text
        return None


class OpenSSLManager:
    certificate_names = {
        "private_key": "TransportPrivate.pem",
        "certificate": "TransportCert.pem",
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
        LOG.debug("Generating certificate for communication with fabric...")
        if self.certificate is not None:
            LOG.debug("Certificate already generated.")
            return
        with cd(self.tmpdir):
            subp.subp(
                [
                    "openssl",
                    "req",
                    "-x509",
                    "-nodes",
                    "-subj",
                    "/CN=LinuxTransport",
                    "-days",
                    "32768",
                    "-newkey",
                    "rsa:2048",
                    "-keyout",
                    self.certificate_names["private_key"],
                    "-out",
                    self.certificate_names["certificate"],
                ]
            )
            certificate = ""
            for line in open(self.certificate_names["certificate"]):
                if "CERTIFICATE" not in line:
                    certificate += line.rstrip()
            self.certificate = certificate
        LOG.debug("New certificate generated.")

    @staticmethod
    @azure_ds_telemetry_reporter
    def _run_x509_action(action, cert):
        cmd = ["openssl", "x509", "-noout", action]
        result, _ = subp.subp(cmd, data=cert)
        return result

    @azure_ds_telemetry_reporter
    def _get_ssh_key_from_cert(self, certificate):
        pub_key = self._run_x509_action("-pubkey", certificate)
        keygen_cmd = ["ssh-keygen", "-i", "-m", "PKCS8", "-f", "/dev/stdin"]
        ssh_key, _ = subp.subp(keygen_cmd, data=pub_key)
        return ssh_key

    @azure_ds_telemetry_reporter
    def _get_fingerprint_from_cert(self, certificate):
        r"""openssl x509 formats fingerprints as so:
        'SHA1 Fingerprint=07:3E:19:D1:4D:1C:79:92:24:C6:A0:FD:8D:DA:\
        B6:A8:BF:27:D4:73\n'

        Azure control plane passes that fingerprint as so:
        '073E19D14D1C799224C6A0FD8DDAB6A8BF27D473'
        """
        raw_fp = self._run_x509_action("-fingerprint", certificate)
        eq = raw_fp.find("=")
        octets = raw_fp[eq + 1 : -1].split(":")
        return "".join(octets)

    @azure_ds_telemetry_reporter
    def _decrypt_certs_from_xml(self, certificates_xml):
        """Decrypt the certificates XML document using the our private key;
        return the list of certs and private keys contained in the doc.
        """
        tag = ElementTree.fromstring(certificates_xml).find(  # nosec B314
            ".//Data"
        )
        certificates_content = tag.text
        lines = [
            b"MIME-Version: 1.0",
            b'Content-Disposition: attachment; filename="Certificates.p7m"',
            b'Content-Type: application/x-pkcs7-mime; name="Certificates.p7m"',
            b"Content-Transfer-Encoding: base64",
            b"",
            certificates_content.encode("utf-8"),
        ]
        with cd(self.tmpdir):
            out, _ = subp.subp(
                "openssl cms -decrypt -in /dev/stdin -inkey"
                " {private_key} -recip {certificate} | openssl pkcs12 -nodes"
                " -password pass:".format(**self.certificate_names),
                shell=True,
                data=b"\n".join(lines),
            )
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
            if re.match(r"[-]+END .*?KEY[-]+$", line):
                # ignore private_keys
                current = []
            elif re.match(r"[-]+END .*?CERTIFICATE[-]+$", line):
                certificate = "\n".join(current)
                ssh_key = self._get_ssh_key_from_cert(certificate)
                fingerprint = self._get_fingerprint_from_cert(certificate)
                keys[fingerprint] = ssh_key
                current = []
        return keys


class GoalStateHealthReporter:
    HEALTH_REPORT_XML_TEMPLATE = textwrap.dedent(
        """\
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
        """
    )

    HEALTH_DETAIL_SUBSECTION_XML_TEMPLATE = textwrap.dedent(
        """\
        <Details>
          <SubStatus>{health_substatus}</SubStatus>
          <Description>{health_description}</Description>
        </Details>
        """
    )

    PROVISIONING_SUCCESS_STATUS = "Ready"
    PROVISIONING_NOT_READY_STATUS = "NotReady"
    PROVISIONING_FAILURE_SUBSTATUS = "ProvisioningFailed"

    HEALTH_REPORT_DESCRIPTION_TRIM_LEN = 512

    def __init__(
        self,
        goal_state: GoalState,
        azure_endpoint_client: AzureEndpointHttpClient,
        endpoint: str,
    ) -> None:
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
            status=self.PROVISIONING_SUCCESS_STATUS,
        )
        LOG.debug("Reporting ready to Azure fabric.")
        try:
            self._post_health_report(document=document)
        except Exception as e:
            report_diagnostic_event(
                "exception while reporting ready: %s" % e,
                logger_func=LOG.error,
            )
            raise

        LOG.info("Reported ready to Azure fabric.")

    @azure_ds_telemetry_reporter
    def send_failure_signal(self, description: str) -> None:
        document = self.build_report(
            incarnation=self._goal_state.incarnation,
            container_id=self._goal_state.container_id,
            instance_id=self._goal_state.instance_id,
            status=self.PROVISIONING_NOT_READY_STATUS,
            substatus=self.PROVISIONING_FAILURE_SUBSTATUS,
            description=description,
        )
        try:
            self._post_health_report(document=document)
        except Exception as e:
            msg = "exception while reporting failure: %s" % e
            report_diagnostic_event(msg, logger_func=LOG.error)
            raise

        LOG.warning("Reported failure to Azure fabric.")

    def build_report(
        self,
        incarnation: str,
        container_id: str,
        instance_id: str,
        status: str,
        substatus=None,
        description=None,
    ) -> bytes:
        health_detail = ""
        if substatus is not None:
            health_detail = self.HEALTH_DETAIL_SUBSECTION_XML_TEMPLATE.format(
                health_substatus=escape(substatus),
                health_description=escape(
                    description[: self.HEALTH_REPORT_DESCRIPTION_TRIM_LEN]
                ),
            )

        health_report = self.HEALTH_REPORT_XML_TEMPLATE.format(
            incarnation=escape(str(incarnation)),
            container_id=escape(container_id),
            instance_id=escape(instance_id),
            health_status=escape(status),
            health_detail_subsection=health_detail,
        )

        return health_report.encode("utf-8")

    @azure_ds_telemetry_reporter
    def _post_health_report(self, document: bytes) -> None:
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
        # sleep(0) is a low-cost and proven method to yield the scheduler
        # and ensure that events are flushed.
        # See HyperVKvpReportingHandler class, which is a multi-threaded
        # reporting handler that writes to the special KVP files.
        sleep(0)

        LOG.debug("Sending health report to Azure fabric.")
        url = "http://{}/machine?comp=health".format(self._endpoint)
        self._azure_endpoint_client.post(
            url,
            data=document,
            extra_headers={"Content-Type": "text/xml; charset=utf-8"},
        )
        LOG.debug("Successfully sent health report to Azure fabric")


class WALinuxAgentShim:
    def __init__(self, endpoint: str):
        self.endpoint = endpoint
        self.openssl_manager: Optional[OpenSSLManager] = None
        self.azure_endpoint_client: Optional[AzureEndpointHttpClient] = None

    def clean_up(self):
        if self.openssl_manager is not None:
            self.openssl_manager.clean_up()

    @azure_ds_telemetry_reporter
    def eject_iso(self, iso_dev, distro: distros.Distro) -> None:
        LOG.debug("Ejecting the provisioning iso")
        try:
            distro.eject_media(iso_dev)
        except Exception as e:
            report_diagnostic_event(
                "Failed ejecting the provisioning iso: %s" % e,
                logger_func=LOG.error,
            )

    @azure_ds_telemetry_reporter
    def register_with_azure_and_fetch_data(
        self, distro: distros.Distro, pubkey_info=None, iso_dev=None
    ) -> Optional[List[str]]:
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
                http_client_certificate
            )
        goal_state = self._fetch_goal_state_from_azure(
            need_certificate=http_client_certificate is not None
        )
        ssh_keys = None
        if pubkey_info is not None:
            ssh_keys = self._get_user_pubkeys(goal_state, pubkey_info)
        health_reporter = GoalStateHealthReporter(
            goal_state, self.azure_endpoint_client, self.endpoint
        )

        if iso_dev is not None:
            self.eject_iso(iso_dev, distro=distro)

        health_reporter.send_ready_signal()
        return ssh_keys

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
            goal_state, self.azure_endpoint_client, self.endpoint
        )
        health_reporter.send_failure_signal(description=description)

    @azure_ds_telemetry_reporter
    def _fetch_goal_state_from_azure(
        self, need_certificate: bool
    ) -> GoalState:
        """Fetches the GoalState XML from the Azure endpoint, parses the XML,
        and returns a GoalState object.

        @param need_certificate: switch to know if certificates is needed.
        @return: GoalState object representing the GoalState XML
        """
        unparsed_goal_state_xml = self._get_raw_goal_state_xml_from_azure()
        return self._parse_raw_goal_state_xml(
            unparsed_goal_state_xml, need_certificate
        )

    @azure_ds_telemetry_reporter
    def _get_raw_goal_state_xml_from_azure(self) -> bytes:
        """Fetches the GoalState XML from the Azure endpoint and returns
        the XML as a string.

        @return: GoalState XML string
        """

        LOG.info("Registering with Azure...")
        url = "http://{}/machine/?comp=goalstate".format(self.endpoint)
        try:
            with events.ReportEventStack(
                name="goalstate-retrieval",
                description="retrieve goalstate",
                parent=azure_ds_reporter,
            ):
                response = self.azure_endpoint_client.get(url)  # type: ignore
        except Exception as e:
            report_diagnostic_event(
                "failed to register with Azure and fetch GoalState XML: %s"
                % e,
                logger_func=LOG.warning,
            )
            raise
        LOG.debug("Successfully fetched GoalState XML.")
        return response.contents

    @azure_ds_telemetry_reporter
    def _parse_raw_goal_state_xml(
        self,
        unparsed_goal_state_xml: Union[str, bytes],
        need_certificate: bool,
    ) -> GoalState:
        """Parses a GoalState XML string and returns a GoalState object.

        @param unparsed_goal_state_xml: GoalState XML string
        @param need_certificate: switch to know if certificates is needed.
        @return: GoalState object representing the GoalState XML
        """
        try:
            goal_state = GoalState(
                unparsed_goal_state_xml,
                self.azure_endpoint_client,  # type: ignore
                need_certificate,
            )
        except Exception as e:
            report_diagnostic_event(
                "Error processing GoalState XML: %s" % e,
                logger_func=LOG.warning,
            )
            raise
        msg = ", ".join(
            [
                "GoalState XML container id: %s" % goal_state.container_id,
                "GoalState XML instance id: %s" % goal_state.instance_id,
                "GoalState XML incarnation: %s" % goal_state.incarnation,
            ]
        )
        report_diagnostic_event(msg, logger_func=LOG.debug)
        return goal_state

    @azure_ds_telemetry_reporter
    def _get_user_pubkeys(
        self, goal_state: GoalState, pubkey_info: list
    ) -> list:
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
        if (
            goal_state.certificates_xml is not None
            and pubkey_info is not None
            and self.openssl_manager is not None
        ):
            LOG.debug("Certificate XML found; parsing out public keys.")
            keys_by_fingerprint = self.openssl_manager.parse_certificates(
                goal_state.certificates_xml
            )
            ssh_keys = self._filter_pubkeys(keys_by_fingerprint, pubkey_info)
        return ssh_keys

    @staticmethod
    def _filter_pubkeys(keys_by_fingerprint: dict, pubkey_info: list) -> list:
        """Filter and return only the user's actual pubkeys.

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
            if "value" in pubkey and pubkey["value"]:
                keys.append(pubkey["value"])
            elif "fingerprint" in pubkey and pubkey["fingerprint"]:
                fingerprint = pubkey["fingerprint"]
                if fingerprint in keys_by_fingerprint:
                    keys.append(keys_by_fingerprint[fingerprint])
                else:
                    LOG.warning(
                        "ovf-env.xml specified PublicKey fingerprint "
                        "%s not found in goalstate XML",
                        fingerprint,
                    )
            else:
                LOG.warning(
                    "ovf-env.xml specified PublicKey with neither "
                    "value nor fingerprint: %s",
                    pubkey,
                )

        return keys


@azure_ds_telemetry_reporter
def get_metadata_from_fabric(
    endpoint: str,
    distro: distros.Distro,
    pubkey_info: Optional[List[str]] = None,
    iso_dev: Optional[str] = None,
):
    shim = WALinuxAgentShim(endpoint=endpoint)
    try:
        return shim.register_with_azure_and_fetch_data(
            distro=distro, pubkey_info=pubkey_info, iso_dev=iso_dev
        )
    finally:
        shim.clean_up()


@azure_ds_telemetry_reporter
def report_failure_to_fabric(endpoint: str, error: "errors.ReportableError"):
    shim = WALinuxAgentShim(endpoint=endpoint)
    description = error.as_encoded_report()
    try:
        shim.register_with_azure_and_report_failure(description=description)
    finally:
        shim.clean_up()


def dhcp_log_cb(out, err):
    report_diagnostic_event(
        "dhclient output stream: %s" % out, logger_func=LOG.debug
    )
    report_diagnostic_event(
        "dhclient error stream: %s" % err, logger_func=LOG.debug
    )


class NonAzureDataSource(Exception):
    pass


class OvfEnvXml:
    NAMESPACES = {
        "ovf": "http://schemas.dmtf.org/ovf/environment/1",
        "wa": "http://schemas.microsoft.com/windowsazure",
    }

    def __init__(
        self,
        *,
        username: Optional[str] = None,
        password: Optional[str] = None,
        hostname: Optional[str] = None,
        custom_data: Optional[bytes] = None,
        disable_ssh_password_auth: Optional[bool] = None,
        public_keys: Optional[List[dict]] = None,
        preprovisioned_vm: bool = False,
        preprovisioned_vm_type: Optional[str] = None,
        provision_guest_proxy_agent: bool = False,
    ) -> None:
        self.username = username
        self.password = password
        self.hostname = hostname
        self.custom_data = custom_data
        self.disable_ssh_password_auth = disable_ssh_password_auth
        self.public_keys: List[dict] = public_keys or []
        self.preprovisioned_vm = preprovisioned_vm
        self.preprovisioned_vm_type = preprovisioned_vm_type
        self.provision_guest_proxy_agent = provision_guest_proxy_agent

    def __eq__(self, other) -> bool:
        return self.__dict__ == other.__dict__

    @classmethod
    def parse_text(cls, ovf_env_xml: str) -> "OvfEnvXml":
        """Parser for ovf-env.xml data.

        :raises NonAzureDataSource: if XML is not in Azure's format.
        :raises errors.ReportableErrorOvfParsingException: if XML is
                unparsable or invalid.
        """
        try:
            root = ElementTree.fromstring(ovf_env_xml)  # nosec B314
        except ElementTree.ParseError as e:
            raise errors.ReportableErrorOvfParsingException(exception=e) from e

        # If there's no provisioning section, it's not Azure ovf-env.xml.
        if not root.find("./wa:ProvisioningSection", cls.NAMESPACES):
            raise NonAzureDataSource(
                "Ignoring non-Azure ovf-env.xml: ProvisioningSection not found"
            )

        instance = OvfEnvXml()
        instance._parse_linux_configuration_set_section(root)
        instance._parse_platform_settings_section(root)

        return instance

    def _find(
        self,
        node,
        name: str,
        required: bool,
        namespace: str = "wa",
    ):
        matches = node.findall(
            "./%s:%s" % (namespace, name), OvfEnvXml.NAMESPACES
        )
        if len(matches) == 0:
            msg = "missing configuration for %r" % name
            LOG.debug(msg)
            if required:
                raise errors.ReportableErrorOvfInvalidMetadata(msg)
            return None
        elif len(matches) > 1:
            raise errors.ReportableErrorOvfInvalidMetadata(
                "multiple configuration matches for %r (%d)"
                % (name, len(matches))
            )

        return matches[0]

    def _parse_property(
        self,
        node,
        name: str,
        required: bool,
        decode_base64: bool = False,
        parse_bool: bool = False,
        default=None,
    ):
        matches = node.findall("./wa:" + name, OvfEnvXml.NAMESPACES)
        if len(matches) == 0:
            msg = "missing configuration for %r" % name
            LOG.debug(msg)
            if required:
                raise errors.ReportableErrorOvfInvalidMetadata(msg)
            return default
        elif len(matches) > 1:
            raise errors.ReportableErrorOvfInvalidMetadata(
                "multiple configuration matches for %r (%d)"
                % (name, len(matches))
            )

        value = matches[0].text

        # Empty string may be None.
        if value is None:
            value = default

        if decode_base64 and value is not None:
            value = base64.b64decode("".join(value.split()))

        if parse_bool:
            value = util.translate_bool(value)

        return value

    def _parse_linux_configuration_set_section(self, root):
        provisioning_section = self._find(
            root, "ProvisioningSection", required=True
        )
        config_set = self._find(
            provisioning_section,
            "LinuxProvisioningConfigurationSet",
            required=True,
        )

        self.custom_data = self._parse_property(
            config_set,
            "CustomData",
            decode_base64=True,
            required=False,
        )
        self.username = self._parse_property(
            config_set, "UserName", required=True
        )
        self.password = self._parse_property(
            config_set, "UserPassword", required=False
        )
        self.hostname = self._parse_property(
            config_set, "HostName", required=True
        )
        self.disable_ssh_password_auth = self._parse_property(
            config_set,
            "DisableSshPasswordAuthentication",
            parse_bool=True,
            required=False,
        )

        self._parse_ssh_section(config_set)

    def _parse_platform_settings_section(self, root):
        platform_settings_section = self._find(
            root, "PlatformSettingsSection", required=True
        )
        platform_settings = self._find(
            platform_settings_section, "PlatformSettings", required=True
        )

        self.preprovisioned_vm = self._parse_property(
            platform_settings,
            "PreprovisionedVm",
            parse_bool=True,
            default=False,
            required=False,
        )
        self.preprovisioned_vm_type = self._parse_property(
            platform_settings,
            "PreprovisionedVMType",
            required=False,
        )
        self.provision_guest_proxy_agent = self._parse_property(
            platform_settings,
            "ProvisionGuestProxyAgent",
            parse_bool=True,
            default=False,
            required=False,
        )

    def _parse_ssh_section(self, config_set):
        self.public_keys = []

        ssh_section = self._find(config_set, "SSH", required=False)
        if ssh_section is None:
            return

        public_keys_section = self._find(
            ssh_section, "PublicKeys", required=False
        )
        if public_keys_section is None:
            return

        for public_key in public_keys_section.findall(
            "./wa:PublicKey", OvfEnvXml.NAMESPACES
        ):
            fingerprint = self._parse_property(
                public_key, "Fingerprint", required=False
            )
            path = self._parse_property(public_key, "Path", required=False)
            value = self._parse_property(
                public_key, "Value", default="", required=False
            )
            ssh_key = {
                "fingerprint": fingerprint,
                "path": path,
                "value": value,
            }
            self.public_keys.append(ssh_key)
