# Copyright (C) 2013 Canonical Ltd.
#
# Author: Scott Moser <scott.moser@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import base64
import functools
import logging
import os
import os.path
import re
import socket
import xml.etree.ElementTree as ET  # nosec B405
from enum import Enum
from pathlib import Path
from time import monotonic, sleep, time
from typing import Any, Dict, List, Optional

import requests

from cloudinit import net, sources, ssh_util, subp, util
from cloudinit.event import EventScope, EventType
from cloudinit.net import device_driver
from cloudinit.net.dhcp import (
    NoDHCPLeaseError,
    NoDHCPLeaseInterfaceError,
    NoDHCPLeaseMissingDhclientError,
)
from cloudinit.net.ephemeral import EphemeralDHCPv4, EphemeralIPv4Network
from cloudinit.reporting import events
from cloudinit.sources.azure import errors, identity, imds, kvp
from cloudinit.sources.helpers import netlink
from cloudinit.sources.helpers.azure import (
    DEFAULT_WIRESERVER_ENDPOINT,
    NonAzureDataSource,
    OvfEnvXml,
    azure_ds_reporter,
    azure_ds_telemetry_reporter,
    build_minimal_ovf,
    dhcp_log_cb,
    get_boot_telemetry,
    get_metadata_from_fabric,
    get_system_info,
    report_diagnostic_event,
    report_dmesg_to_kvp,
    report_failure_to_fabric,
)
from cloudinit.url_helper import UrlError

try:
    import crypt  # pylint: disable=W4901

    blowfish_hash: Any = functools.partial(
        crypt.crypt, salt=f"$6${util.rand_str(strlen=16)}"
    )
except (ImportError, AttributeError):
    try:
        import passlib.hash

        blowfish_hash = passlib.hash.sha512_crypt.hash
    except ImportError:

        def blowfish_hash(_):
            """Raise when called so that importing this module doesn't throw
            ImportError when ds_detect() returns false. In this case, crypt
            and passlib are not needed.
            """
            raise ImportError(
                "crypt and passlib not found, missing dependency"
            )


LOG = logging.getLogger(__name__)

DS_NAME = "Azure"
DEFAULT_METADATA = {"instance-id": "iid-AZURE-NODE"}

# azure systems will always have a resource disk, and 66-azure-ephemeral.rules
# ensures that it gets linked to this path.
RESOURCE_DISK_PATH = "/dev/disk/cloud/azure_resource"
DEFAULT_FS = "ext4"
AGENT_SEED_DIR = "/var/lib/waagent"
DEFAULT_PROVISIONING_ISO_DEV = "/dev/sr0"


class PPSType(Enum):
    NONE = "None"
    OS_DISK = "PreprovisionedOSDisk"
    RUNNING = "Running"
    SAVABLE = "Savable"
    UNKNOWN = "Unknown"


PLATFORM_ENTROPY_SOURCE: Optional[str] = "/sys/firmware/acpi/tables/OEM0"

# List of static scripts and network config artifacts created by
# stock ubuntu supported images.
UBUNTU_EXTENDED_NETWORK_SCRIPTS = [
    "/etc/netplan/90-hotplug-azure.yaml",
    "/usr/local/sbin/ephemeral_eth.sh",
    "/etc/udev/rules.d/10-net-device-added.rules",
    "/run/network/interfaces.ephemeral.d",
]


def find_storvscid_from_sysctl_pnpinfo(sysctl_out, deviceid):
    # extract the 'X' from dev.storvsc.X. if deviceid matches
    """
    dev.storvsc.1.%pnpinfo:
        classid=32412632-86cb-44a2-9b5c-50d1417354f5
        deviceid=00000000-0001-8899-0000-000000000000
    """
    for line in sysctl_out.splitlines():
        if re.search(r"pnpinfo", line):
            fields = line.split()
            if len(fields) >= 3:
                columns = fields[2].split("=")
                if (
                    len(columns) >= 2
                    and columns[0] == "deviceid"
                    and columns[1].startswith(deviceid)
                ):
                    comps = fields[0].split(".")
                    return comps[2]
    return None


def find_busdev_from_disk(camcontrol_out, disk_drv):
    # find the scbusX from 'camcontrol devlist -b' output
    # if disk_drv matches the specified disk driver, i.e. blkvsc1
    """
    scbus0 on ata0 bus 0
    scbus1 on ata1 bus 0
    scbus2 on blkvsc0 bus 0
    scbus3 on blkvsc1 bus 0
    scbus4 on storvsc2 bus 0
    scbus5 on storvsc3 bus 0
    scbus-1 on xpt0 bus 0
    """
    for line in camcontrol_out.splitlines():
        if re.search(disk_drv, line):
            items = line.split()
            return items[0]
    return None


def find_dev_from_busdev(camcontrol_out: str, busdev: str) -> Optional[str]:
    # find the daX from 'camcontrol devlist' output
    # if busdev matches the specified value, i.e. 'scbus2'
    """
    <Msft Virtual CD/ROM 1.0>          at scbus1 target 0 lun 0 (cd0,pass0)
    <Msft Virtual Disk 1.0>            at scbus2 target 0 lun 0 (da0,pass1)
    <Msft Virtual Disk 1.0>            at scbus3 target 1 lun 0 (da1,pass2)
    """
    for line in camcontrol_out.splitlines():
        if re.search(busdev, line):
            items = line.split("(")
            if len(items) == 2:
                dev_pass = items[1].split(",")
                return dev_pass[0]
    return None


def normalize_mac_address(mac: str) -> str:
    """Normalize mac address with colons and lower-case."""
    if len(mac) == 12:
        mac = ":".join(
            [mac[0:2], mac[2:4], mac[4:6], mac[6:8], mac[8:10], mac[10:12]]
        )

    return mac.lower()


@azure_ds_telemetry_reporter
def get_hv_netvsc_macs_normalized() -> List[str]:
    """Get Hyper-V NICs as normalized MAC addresses."""
    return [
        normalize_mac_address(n[1])
        for n in net.get_interfaces()
        if n[2] == "hv_netvsc"
    ]


@azure_ds_telemetry_reporter
def determine_device_driver_for_mac(mac: str) -> Optional[str]:
    """Determine the device driver to match on, if any."""
    drivers = [
        i[2]
        for i in net.get_interfaces()
        if mac == normalize_mac_address(i[1])
    ]
    if "hv_netvsc" in drivers:
        return "hv_netvsc"

    if len(drivers) == 1:
        report_diagnostic_event(
            "Assuming driver for interface with mac=%s drivers=%r"
            % (mac, drivers),
            logger_func=LOG.debug,
        )
        return drivers[0]

    report_diagnostic_event(
        "Unable to specify driver for interface with mac=%s drivers=%r"
        % (mac, drivers),
        logger_func=LOG.warning,
    )
    return None


def execute_or_debug(cmd, fail_ret=None) -> str:
    try:
        return subp.subp(cmd).stdout  # pyright: ignore
    except subp.ProcessExecutionError:
        LOG.debug("Failed to execute: %s", " ".join(cmd))
        return fail_ret


def get_dev_storvsc_sysctl():
    return execute_or_debug(["sysctl", "dev.storvsc"], fail_ret="")


def get_camcontrol_dev_bus():
    return execute_or_debug(["camcontrol", "devlist", "-b"])


def get_camcontrol_dev():
    return execute_or_debug(["camcontrol", "devlist"])


def get_resource_disk_on_freebsd(port_id) -> Optional[str]:
    g0 = "00000000"
    if port_id > 1:
        g0 = "00000001"
        port_id = port_id - 2
    g1 = "000" + str(port_id)
    g0g1 = "{0}-{1}".format(g0, g1)

    # search 'X' from
    #  'dev.storvsc.X.%pnpinfo:
    #      classid=32412632-86cb-44a2-9b5c-50d1417354f5
    #      deviceid=00000000-0001-8899-0000-000000000000'
    sysctl_out = get_dev_storvsc_sysctl()

    storvscid = find_storvscid_from_sysctl_pnpinfo(sysctl_out, g0g1)
    if not storvscid:
        LOG.debug("Fail to find storvsc id from sysctl")
        return None

    camcontrol_b_out = get_camcontrol_dev_bus()
    camcontrol_out = get_camcontrol_dev()
    # try to find /dev/XX from 'blkvsc' device
    blkvsc = "blkvsc{0}".format(storvscid)
    scbusx = find_busdev_from_disk(camcontrol_b_out, blkvsc)
    if scbusx:
        devname = find_dev_from_busdev(camcontrol_out, scbusx)
        if devname is None:
            LOG.debug("Fail to find /dev/daX")
            return None
        return devname
    # try to find /dev/XX from 'storvsc' device
    storvsc = "storvsc{0}".format(storvscid)
    scbusx = find_busdev_from_disk(camcontrol_b_out, storvsc)
    if scbusx:
        devname = find_dev_from_busdev(camcontrol_out, scbusx)
        if devname is None:
            LOG.debug("Fail to find /dev/daX")
            return None
        return devname
    return None


# update the FreeBSD specific information
if util.is_FreeBSD():
    DEFAULT_FS = "freebsd-ufs"
    res_disk = get_resource_disk_on_freebsd(1)
    if res_disk is not None:
        LOG.debug("resource disk is not None")
        RESOURCE_DISK_PATH = "/dev/" + res_disk
    else:
        LOG.debug("resource disk is None")
    # TODO Find where platform entropy data is surfaced
    PLATFORM_ENTROPY_SOURCE = None

BUILTIN_DS_CONFIG = {
    "data_dir": AGENT_SEED_DIR,
    "disk_aliases": {"ephemeral0": RESOURCE_DISK_PATH},
    "apply_network_config": True,  # Use IMDS published network configuration
    "apply_network_config_for_secondary_ips": True,  # Configure secondary ips
}

BUILTIN_CLOUD_EPHEMERAL_DISK_CONFIG = {
    "disk_setup": {
        "ephemeral0": {
            "table_type": "gpt",
            "layout": [100],
            "overwrite": True,
        },
    },
    "fs_setup": [{"filesystem": DEFAULT_FS, "device": "ephemeral0.1"}],
}

DS_CFG_PATH = ["datasource", DS_NAME]
DS_CFG_KEY_PRESERVE_NTFS = "never_destroy_ntfs"

# The redacted password fails to meet password complexity requirements
# so we can safely use this to mask/redact the password in the ovf-env.xml
DEF_PASSWD_REDACTION = "REDACTED"


class DataSourceAzure(sources.DataSource):
    dsname = "Azure"
    default_update_events = {
        EventScope.NETWORK: {
            EventType.BOOT_NEW_INSTANCE,
            EventType.BOOT,
        }
    }
    _negotiated = False
    _metadata_imds = sources.UNSET
    _ci_pkl_version = 1

    def __init__(self, sys_cfg, distro, paths):
        sources.DataSource.__init__(self, sys_cfg, distro, paths)
        self.seed_dir = os.path.join(paths.seed_dir, "azure")
        self.cfg = {}
        self.seed = None
        self.ds_cfg = util.mergemanydict(
            [util.get_cfg_by_path(sys_cfg, DS_CFG_PATH, {}), BUILTIN_DS_CONFIG]
        )
        self._iso_dev = None
        self._network_config = None
        self._ephemeral_dhcp_ctx: Optional[EphemeralDHCPv4] = None
        self._route_configured_for_imds = False
        self._route_configured_for_wireserver = False
        self._wireserver_endpoint = DEFAULT_WIRESERVER_ENDPOINT
        self._reported_ready_marker_file = os.path.join(
            paths.cloud_dir, "data", "reported_ready"
        )

    def _unpickle(self, ci_pkl_version: int) -> None:
        super()._unpickle(ci_pkl_version)

        self._ephemeral_dhcp_ctx = None
        self._iso_dev = None
        self._route_configured_for_imds = False
        self._route_configured_for_wireserver = False
        self._wireserver_endpoint = DEFAULT_WIRESERVER_ENDPOINT
        self._reported_ready_marker_file = os.path.join(
            self.paths.cloud_dir, "data", "reported_ready"
        )

    def __str__(self):
        root = sources.DataSource.__str__(self)
        return "%s [seed=%s]" % (root, self.seed)

    def _get_subplatform(self):
        """Return the subplatform metadata source details."""
        if self.seed is None:
            subplatform_type = "unknown"
        elif self.seed.startswith("/dev"):
            subplatform_type = "config-disk"
        elif self.seed.lower() == "imds":
            subplatform_type = "imds"
        else:
            subplatform_type = "seed-dir"
        return "%s (%s)" % (subplatform_type, self.seed)

    @azure_ds_telemetry_reporter
    def _check_if_primary(self, ephipv4: EphemeralIPv4Network) -> bool:
        if not ephipv4.static_routes:
            # Primary nics must contain routes.
            return False

        routed_networks = [r[0].split("/")[0] for r in ephipv4.static_routes]

        # Expected to be true for all of Azure public cloud and future Azure
        # Stack versions with IMDS capabilities, but false for existing ones.
        self._route_configured_for_imds = "169.254.169.254" in routed_networks

        # Expected to be true for Azure public cloud and Azure Stack.
        self._route_configured_for_wireserver = (
            self._wireserver_endpoint in routed_networks
        )

        return (
            self._route_configured_for_imds
            or self._route_configured_for_wireserver
        )

    @azure_ds_telemetry_reporter
    def _setup_ephemeral_networking(
        self,
        *,
        iface: Optional[str] = None,
        report_failure_if_not_primary: bool = True,
        retry_sleep: int = 1,
        timeout_minutes: int = 5,
    ) -> bool:
        """Setup ephemeral networking.

        Keep retrying DHCP up to specified number of minutes.  This does
        not kill dhclient, so the timeout in practice may be up to
        timeout_minutes + the system-configured timeout for dhclient.

        :param timeout_minutes: Number of minutes to keep retrying for.

        :raises NoDHCPLeaseError: If unable to obtain DHCP lease.

        :returns: True if NIC is determined to be primary.
        """
        if self._ephemeral_dhcp_ctx is not None:
            raise RuntimeError(
                "Bringing up networking when already configured."
            )

        report_diagnostic_event(
            "Bringing up ephemeral networking with iface=%s: %r"
            % (iface, net.get_interfaces()),
            logger_func=LOG.debug,
        )
        self._ephemeral_dhcp_ctx = EphemeralDHCPv4(
            self.distro,
            iface=iface,
            dhcp_log_func=dhcp_log_cb,
        )

        lease: Optional[Dict[str, Any]] = None
        start_time = monotonic()
        deadline = start_time + timeout_minutes * 60
        with events.ReportEventStack(
            name="obtain-dhcp-lease",
            description="obtain dhcp lease",
            parent=azure_ds_reporter,
        ):
            while lease is None:
                try:
                    lease = self._ephemeral_dhcp_ctx.obtain_lease()
                except NoDHCPLeaseInterfaceError:
                    # Interface not found, continue after sleeping 1 second.
                    report_diagnostic_event(
                        "Interface not found for DHCP", logger_func=LOG.warning
                    )
                    self._report_failure(
                        errors.ReportableErrorDhcpInterfaceNotFound(
                            duration=monotonic() - start_time
                        ),
                        host_only=True,
                    )
                except NoDHCPLeaseMissingDhclientError:
                    # No dhclient, no point in retrying.
                    report_diagnostic_event(
                        "dhclient executable not found", logger_func=LOG.error
                    )
                    self._ephemeral_dhcp_ctx = None
                    raise
                except NoDHCPLeaseError:
                    # Typical DHCP failure, continue after sleeping 1 second.
                    report_diagnostic_event(
                        "Failed to obtain DHCP lease (iface=%s)" % iface,
                        logger_func=LOG.error,
                    )
                    self._report_failure(
                        errors.ReportableErrorDhcpLease(
                            duration=monotonic() - start_time, interface=iface
                        ),
                        host_only=True,
                    )
                except subp.ProcessExecutionError as error:
                    # udevadm settle, ip link set dev eth0 up, etc.
                    report_diagnostic_event(
                        "Command failed: "
                        "cmd=%r stderr=%r stdout=%r exit_code=%s"
                        % (
                            error.cmd,
                            error.stderr,
                            error.stdout,
                            error.exit_code,
                        ),
                        logger_func=LOG.error,
                    )

                # Sleep before retrying, otherwise break if past deadline.
                if lease is None and monotonic() + retry_sleep < deadline:
                    sleep(retry_sleep)
                else:
                    break

            if lease is None:
                self._ephemeral_dhcp_ctx = None
                raise NoDHCPLeaseError()

            # Ensure iface is set.
            iface = lease["interface"]
            self._ephemeral_dhcp_ctx.iface = iface

            # Update wireserver IP from DHCP options.
            if "unknown-245" in lease:
                self._wireserver_endpoint = lease["unknown-245"]

            driver = device_driver(iface)
            ephipv4 = self._ephemeral_dhcp_ctx._ephipv4
            if ephipv4 is None:
                raise RuntimeError("dhcp context missing ephipv4")

            primary = self._check_if_primary(ephipv4)
            report_diagnostic_event(
                "Obtained DHCP lease on interface %r "
                "(primary=%r driver=%r router=%r routes=%r lease=%r "
                "imds_routed=%r wireserver_routed=%r)"
                % (
                    iface,
                    primary,
                    driver,
                    ephipv4.router,
                    ephipv4.static_routes,
                    lease,
                    self._route_configured_for_imds,
                    self._route_configured_for_wireserver,
                ),
                logger_func=LOG.debug,
            )

            if report_failure_if_not_primary and not primary:
                self._report_failure(
                    errors.ReportableErrorDhcpOnNonPrimaryInterface(
                        interface=iface,
                        driver=driver,
                        router=ephipv4.router,
                        static_routes=ephipv4.static_routes,
                        lease=lease,
                    ),
                    host_only=True,
                )
            return primary

    @azure_ds_telemetry_reporter
    def _teardown_ephemeral_networking(self) -> None:
        """Teardown ephemeral networking."""
        self._route_configured_for_imds = False
        self._route_configured_for_wireserver = False
        if self._ephemeral_dhcp_ctx is None:
            return

        self._ephemeral_dhcp_ctx.clean_network()
        self._ephemeral_dhcp_ctx = None

    def _is_ephemeral_networking_up(self) -> bool:
        """Check if networking is configured."""
        return not (
            self._ephemeral_dhcp_ctx is None
            or self._ephemeral_dhcp_ctx.lease is None
        )

    @azure_ds_telemetry_reporter
    def crawl_metadata(self):
        """Walk all instance metadata sources returning a dict on success.

        @return: A dictionary of any metadata content for this instance.
        @raise: InvalidMetaDataException when the expected metadata service is
            unavailable, broken or disabled.
        """
        crawled_data = {}
        # azure removes/ejects the cdrom containing the ovf-env.xml
        # file on reboot.  So, in order to successfully reboot we
        # need to look in the datadir and consider that valid
        ddir = self.ds_cfg["data_dir"]

        # The order in which the candidates are inserted matters here, because
        # it determines the value of ret. More specifically, the first one in
        # the candidate list determines the path to take in order to get the
        # metadata we need.
        ovf_source = None
        md = {"local-hostname": ""}
        cfg = {"system_info": {"default_user": {"name": ""}}}
        userdata_raw = ""
        files = {}

        for src in list_possible_azure_ds(self.seed_dir, ddir):
            try:
                if src.startswith("/dev/"):
                    if util.is_FreeBSD():
                        md, userdata_raw, cfg, files = util.mount_cb(
                            src, load_azure_ds_dir, mtype="udf"
                        )
                    else:
                        md, userdata_raw, cfg, files = util.mount_cb(
                            src, load_azure_ds_dir
                        )
                    # save the device for ejection later
                    self._iso_dev = src
                else:
                    md, userdata_raw, cfg, files = load_azure_ds_dir(src)

                ovf_source = src
                report_diagnostic_event(
                    "Found provisioning metadata in %s" % ovf_source,
                    logger_func=LOG.debug,
                )
                break
            except NonAzureDataSource:
                report_diagnostic_event(
                    "Did not find Azure data source in %s" % src,
                    logger_func=LOG.debug,
                )
                continue
            except util.MountFailedError:
                report_diagnostic_event(
                    "%s was not mountable" % src, logger_func=LOG.debug
                )
                continue
        else:
            msg = (
                "Unable to find provisioning media, falling back to IMDS "
                "metadata. Be aware that IMDS metadata does not support "
                "admin passwords or custom-data (user-data only)."
            )
            report_diagnostic_event(msg, logger_func=LOG.warning)

        # If we read OVF from attached media, we are provisioning.  If OVF
        # is not found, we are probably provisioning on a system which does
        # not have UDF support.  In either case, require IMDS metadata.
        # If we require IMDS metadata, try harder to obtain networking, waiting
        # for at least 20 minutes.  Otherwise only wait 5 minutes.
        requires_imds_metadata = bool(self._iso_dev) or ovf_source is None
        timeout_minutes = 20 if requires_imds_metadata else 5
        try:
            self._setup_ephemeral_networking(timeout_minutes=timeout_minutes)
        except NoDHCPLeaseError:
            pass

        imds_md = {}
        if self._is_ephemeral_networking_up():
            imds_md = self.get_metadata_from_imds(report_failure=True)

        if not imds_md and ovf_source is None:
            msg = "No OVF or IMDS available"
            report_diagnostic_event(msg)
            raise sources.InvalidMetaDataException(msg)

        # Refresh PPS type using metadata.
        pps_type = self._determine_pps_type(cfg, imds_md)
        if pps_type != PPSType.NONE:
            if util.is_FreeBSD():
                msg = "Free BSD is not supported for PPS VMs"
                report_diagnostic_event(msg, logger_func=LOG.error)
                raise sources.InvalidMetaDataException(msg)

            # Networking is a hard requirement for source PPS, fail without it.
            if not self._is_ephemeral_networking_up():
                msg = "DHCP failed while in source PPS"
                report_diagnostic_event(msg, logger_func=LOG.error)
                raise sources.InvalidMetaDataException(msg)

            if pps_type == PPSType.RUNNING:
                self._wait_for_pps_running_reuse()
            elif pps_type == PPSType.SAVABLE:
                self._wait_for_pps_savable_reuse()
            elif pps_type == PPSType.OS_DISK:
                self._wait_for_pps_os_disk_shutdown()
            else:
                self._wait_for_pps_unknown_reuse()

            md, userdata_raw, cfg, files = self._reprovision()
            # fetch metadata again as it has changed after reprovisioning
            imds_md = self.get_metadata_from_imds(report_failure=True)

            # validate imds pps metadata
            imds_ppstype = self._ppstype_from_imds(imds_md)
            if imds_ppstype not in (None, PPSType.NONE.value):
                self._report_failure(
                    errors.ReportableErrorImdsInvalidMetadata(
                        key="extended.compute.ppsType", value=imds_ppstype
                    )
                )

        # Report errors if IMDS network configuration is missing data.
        self.validate_imds_network_metadata(imds_md=imds_md)

        self.seed = ovf_source or "IMDS"
        crawled_data.update(
            {
                "cfg": cfg,
                "files": files,
                "metadata": util.mergemanydict([md, {"imds": imds_md}]),
                "userdata_raw": userdata_raw,
            }
        )
        imds_username = _username_from_imds(imds_md)
        imds_hostname = _hostname_from_imds(imds_md)
        imds_disable_password = _disable_password_from_imds(imds_md)
        if imds_username:
            LOG.debug("Username retrieved from IMDS: %s", imds_username)
            cfg["system_info"]["default_user"]["name"] = imds_username
        if imds_hostname:
            LOG.debug("Hostname retrieved from IMDS: %s", imds_hostname)
            crawled_data["metadata"]["local-hostname"] = imds_hostname
        if imds_disable_password:
            LOG.debug(
                "Disable password retrieved from IMDS: %s",
                imds_disable_password,
            )
            crawled_data["metadata"][
                "disable_password"
            ] = imds_disable_password

        if self.seed == "IMDS" and not crawled_data["files"]:
            try:
                contents = build_minimal_ovf(
                    username=imds_username,  # pyright: ignore
                    hostname=imds_hostname,  # pyright: ignore
                    disableSshPwd=imds_disable_password,  # pyright: ignore
                )
                crawled_data["files"] = {"ovf-env.xml": contents}
            except Exception as e:
                report_diagnostic_event(
                    "Failed to construct OVF from IMDS data %s" % e,
                    logger_func=LOG.debug,
                )

        # only use userdata from imds if OVF did not provide custom data
        # userdata provided by IMDS is always base64 encoded
        if not userdata_raw:
            imds_userdata = _userdata_from_imds(imds_md)
            if imds_userdata:
                LOG.debug("Retrieved userdata from IMDS")
                try:
                    crawled_data["userdata_raw"] = base64.b64decode(
                        "".join(imds_userdata.split())
                    )
                except Exception:
                    report_diagnostic_event(
                        "Bad userdata in IMDS", logger_func=LOG.warning
                    )

        if ovf_source == ddir:
            report_diagnostic_event(
                "using files cached in %s" % ddir, logger_func=LOG.debug
            )

        seed = _get_random_seed()
        if seed:
            crawled_data["metadata"]["random_seed"] = seed
        crawled_data["metadata"]["instance-id"] = self._iid()

        if self._negotiated is False and self._is_ephemeral_networking_up():
            # Report ready and fetch public-keys from Wireserver, if required.
            pubkey_info = self._determine_wireserver_pubkey_info(
                cfg=cfg, imds_md=imds_md
            )
            try:
                ssh_keys = self._report_ready(pubkey_info=pubkey_info)
            except Exception:
                # Failed to report ready, but continue with best effort.
                pass
            else:
                LOG.debug("negotiating returned %s", ssh_keys)
                if ssh_keys:
                    crawled_data["metadata"]["public-keys"] = ssh_keys

                self._cleanup_markers()

        return crawled_data

    @azure_ds_telemetry_reporter
    def get_metadata_from_imds(self, report_failure: bool) -> Dict:
        start_time = monotonic()
        retry_deadline = start_time + 300

        # As a temporary workaround to support Azure Stack implementations
        # which may not enable IMDS, limit connection errors to 11.
        if not self._route_configured_for_imds:
            max_connection_errors = 11
        else:
            max_connection_errors = None

        error_string: Optional[str] = None
        error_report: Optional[errors.ReportableError] = None
        try:
            return imds.fetch_metadata_with_api_fallback(
                max_connection_errors=max_connection_errors,
                retry_deadline=retry_deadline,
            )
        except UrlError as error:
            error_string = str(error)
            duration = monotonic() - start_time
            error_report = errors.ReportableErrorImdsUrlError(
                exception=error, duration=duration
            )

            # As a temporary workaround to support Azure Stack implementations
            # which may not enable IMDS, don't report connection errors to
            # wireserver if route is not configured.
            if not self._route_configured_for_imds and isinstance(
                error.cause, requests.ConnectionError
            ):
                report_failure = False
        except ValueError as error:
            error_string = str(error)
            error_report = errors.ReportableErrorImdsMetadataParsingException(
                exception=error
            )

        self._report_failure(error_report, host_only=not report_failure)
        report_diagnostic_event(
            "Ignoring IMDS metadata due to: %s" % error_string,
            logger_func=LOG.warning,
        )
        return {}

    def clear_cached_attrs(self, attr_defaults=()):
        """Reset any cached class attributes to defaults."""
        super(DataSourceAzure, self).clear_cached_attrs(attr_defaults)
        self._metadata_imds = sources.UNSET

    @azure_ds_telemetry_reporter
    def ds_detect(self):
        """Check platform environment to report if this datasource may
        run.
        """
        chassis_tag = identity.ChassisAssetTag.query_system()
        if chassis_tag is not None:
            return True

        # If no valid chassis tag, check for seeded ovf-env.xml.
        if self.seed_dir is None:
            return False

        return Path(self.seed_dir, "ovf-env.xml").exists()

    @azure_ds_telemetry_reporter
    def _get_data(self):
        """Crawl and process datasource metadata caching metadata as attrs.

        @return: True on success, False on error, invalid or disabled
            datasource.
        """
        try:
            get_boot_telemetry()
        except Exception as e:
            LOG.warning("Failed to get boot telemetry: %s", e)

        try:
            get_system_info()
        except Exception as e:
            LOG.warning("Failed to get system information: %s", e)

        try:
            crawled_data = util.log_time(
                logfunc=LOG.debug,
                msg="Crawl of metadata service",
                func=self.crawl_metadata,
            )
        except errors.ReportableError as error:
            self._report_failure(error)
            return False
        except Exception as error:
            reportable_error = errors.ReportableErrorUnhandledException(error)
            self._report_failure(reportable_error)
            return False
        finally:
            self._teardown_ephemeral_networking()

        if (
            self.distro
            and self.distro.name == "ubuntu"
            and self.ds_cfg.get("apply_network_config")
        ):
            maybe_remove_ubuntu_network_config_scripts()

        # Process crawled data and augment with various config defaults

        # Only merge in default cloud config related to the ephemeral disk
        # if the ephemeral disk exists
        devpath = RESOURCE_DISK_PATH
        if os.path.exists(devpath):
            report_diagnostic_event(
                "Ephemeral resource disk '%s' exists. "
                "Merging default Azure cloud ephemeral disk configs."
                % devpath,
                logger_func=LOG.debug,
            )
            self.cfg = util.mergemanydict(
                [crawled_data["cfg"], BUILTIN_CLOUD_EPHEMERAL_DISK_CONFIG]
            )
        else:
            report_diagnostic_event(
                "Ephemeral resource disk '%s' does not exist. "
                "Not merging default Azure cloud ephemeral disk configs."
                % devpath,
                logger_func=LOG.debug,
            )
            self.cfg = crawled_data["cfg"]

        self._metadata_imds = crawled_data["metadata"]["imds"]
        self.metadata = util.mergemanydict(
            [crawled_data["metadata"], DEFAULT_METADATA]
        )
        self.userdata_raw = crawled_data["userdata_raw"]

        # walinux agent writes files world readable, but expects
        # the directory to be protected.
        write_files(
            self.ds_cfg["data_dir"], crawled_data["files"], dirmode=0o700
        )
        return True

    def get_instance_id(self):
        if not self.metadata or "instance-id" not in self.metadata:
            return self._iid()
        return str(self.metadata["instance-id"])

    def device_name_to_device(self, name):
        return self.ds_cfg["disk_aliases"].get(name)

    @azure_ds_telemetry_reporter
    def get_public_ssh_keys(self) -> List[str]:
        """
        Retrieve public SSH keys.
        """
        try:
            return self._get_public_keys_from_imds(self.metadata["imds"])
        except (KeyError, ValueError):
            pass

        return self._get_public_keys_from_ovf()

    def _get_public_keys_from_imds(self, imds_md: dict) -> List[str]:
        """Get SSH keys from IMDS metadata.

        :raises KeyError: if IMDS metadata is malformed/missing.
        :raises ValueError: if key format is not supported.

        :returns: List of keys.
        """
        try:
            ssh_keys = [
                public_key["keyData"]
                for public_key in imds_md["compute"]["publicKeys"]
            ]
        except KeyError:
            log_msg = "No SSH keys found in IMDS metadata"
            report_diagnostic_event(log_msg, logger_func=LOG.debug)
            raise

        if any(not _key_is_openssh_formatted(key=key) for key in ssh_keys):
            log_msg = "Key(s) not in OpenSSH format"
            report_diagnostic_event(log_msg, logger_func=LOG.debug)
            raise ValueError(log_msg)

        log_msg = "Retrieved {} keys from IMDS".format(len(ssh_keys))
        report_diagnostic_event(log_msg, logger_func=LOG.debug)
        return ssh_keys

    def _get_public_keys_from_ovf(self) -> List[str]:
        """Get SSH keys that were fetched from wireserver.

        :returns: List of keys.
        """
        ssh_keys = []
        try:
            ssh_keys = self.metadata["public-keys"]
            log_msg = "Retrieved {} keys from OVF".format(len(ssh_keys))
            report_diagnostic_event(log_msg, logger_func=LOG.debug)
        except KeyError:
            log_msg = "No keys available from OVF"
            report_diagnostic_event(log_msg, logger_func=LOG.debug)

        return ssh_keys

    def get_config_obj(self):
        return self.cfg

    def check_instance_id(self, sys_cfg):
        # quickly (local check only) if self.instance_id is still valid
        return sources.instance_id_matches_system_uuid(self.get_instance_id())

    def _iid(self, previous=None):
        prev_iid_path = os.path.join(
            self.paths.get_cpath("data"), "instance-id"
        )
        system_uuid = identity.query_system_uuid()
        if os.path.exists(prev_iid_path):
            previous = util.load_text_file(prev_iid_path).strip()
            swapped_id = identity.byte_swap_system_uuid(system_uuid)

            # Older kernels than 4.15 will have UPPERCASE product_uuid.
            # We don't want Azure to react to an UPPER/lower difference as
            # a new instance id as it rewrites SSH host keys.
            # LP: #1835584
            if previous.lower() in [system_uuid, swapped_id]:
                return previous
        return system_uuid

    @azure_ds_telemetry_reporter
    def _wait_for_nic_detach(self, nl_sock):
        """Use the netlink socket provided to wait for nic detach event.
        NOTE: The function doesn't close the socket. The caller owns closing
        the socket and disposing it safely.
        """
        try:
            ifname = None

            # Preprovisioned VM will only have one NIC, and it gets
            # detached immediately after deployment.
            with events.ReportEventStack(
                name="wait-for-nic-detach",
                description="wait for nic detach",
                parent=azure_ds_reporter,
            ):
                ifname = netlink.wait_for_nic_detach_event(nl_sock)
            if ifname is None:
                msg = (
                    "Preprovisioned nic not detached as expected. "
                    "Proceeding without failing."
                )
                report_diagnostic_event(msg, logger_func=LOG.warning)
            else:
                report_diagnostic_event(
                    "The preprovisioned nic %s is detached" % ifname,
                    logger_func=LOG.debug,
                )
        except AssertionError as error:
            report_diagnostic_event(str(error), logger_func=LOG.error)
            raise

    @azure_ds_telemetry_reporter
    def wait_for_link_up(
        self, ifname: str, retries: int = 100, retry_sleep: float = 0.1
    ):
        for i in range(retries):
            if self.distro.networking.try_set_link_up(ifname):
                report_diagnostic_event(
                    "The link %s is up." % ifname, logger_func=LOG.info
                )
                break

            if (i + 1) < retries:
                sleep(retry_sleep)
        else:
            report_diagnostic_event(
                "The link %s is not up after %f seconds, continuing anyways."
                % (ifname, retries * retry_sleep),
                logger_func=LOG.info,
            )

    @azure_ds_telemetry_reporter
    def _create_report_ready_marker(self):
        path = self._reported_ready_marker_file
        LOG.info("Creating a marker file to report ready: %s", path)
        util.write_file(
            path, "{pid}: {time}\n".format(pid=os.getpid(), time=time())
        )
        report_diagnostic_event(
            "Successfully created reported ready marker file "
            "while in the preprovisioning pool.",
            logger_func=LOG.debug,
        )

    @azure_ds_telemetry_reporter
    def _report_ready_for_pps(
        self,
        *,
        create_marker: bool = True,
        expect_url_error: bool = False,
    ) -> None:
        """Report ready for PPS, creating the marker file upon completion.

        :raises sources.InvalidMetaDataException: On error reporting ready.
        """
        try:
            self._report_ready()
        except Exception as error:
            # Ignore HTTP failures for Savable PPS as the call may appear to
            # fail if the network interface is unplugged or the VM is
            # suspended before we process the response. Worst case scenario
            # is that we failed to report ready for source PPS and this VM
            # will be discarded shortly, no harm done.
            if expect_url_error and isinstance(error, UrlError):
                report_diagnostic_event(
                    "Ignoring http call failure, it was expected.",
                    logger_func=LOG.debug,
                )
                # The iso was ejected prior to reporting ready.
                self._iso_dev = None
            else:
                msg = (
                    "Failed reporting ready while in the preprovisioning pool."
                )
                report_diagnostic_event(msg, logger_func=LOG.error)
                raise sources.InvalidMetaDataException(msg) from error

        # Reset flag as we will need to report ready again for re-use.
        self._negotiated = False

        if create_marker:
            self._create_report_ready_marker()

    @azure_ds_telemetry_reporter
    def _wait_for_hot_attached_primary_nic(self, nl_sock):
        """Wait until the primary nic for the vm is hot-attached."""
        LOG.info("Waiting for primary nic to be hot-attached")
        try:
            nics_found = []
            primary_nic_found = False

            # Wait for netlink nic attach events. After the first nic is
            # attached, we are already in the customer vm deployment path and
            # so everything from then on should happen fast and avoid
            # unnecessary delays wherever possible.
            while True:
                ifname = None
                with events.ReportEventStack(
                    name="wait-for-nic-attach",
                    description=(
                        "wait for nic attach after %d nics have been attached"
                        % len(nics_found)
                    ),
                    parent=azure_ds_reporter,
                ):
                    ifname = netlink.wait_for_nic_attach_event(
                        nl_sock, nics_found
                    )

                # wait_for_nic_attach_event guarantees that ifname it not None
                nics_found.append(ifname)
                report_diagnostic_event(
                    "Detected nic %s attached." % ifname, logger_func=LOG.info
                )

                # Attempt to bring the interface's operating state to
                # UP in case it is not already.
                self.wait_for_link_up(ifname)

                # If primary nic is not found, check if this is it. The
                # platform will attach the primary nic first so we
                # won't be in primary_nic_found = false state for long.
                if not primary_nic_found:
                    LOG.info("Checking if %s is the primary nic", ifname)
                    primary_nic_found = self._setup_ephemeral_networking(
                        iface=ifname,
                        timeout_minutes=20,
                        report_failure_if_not_primary=False,
                    )

                # Exit criteria: check if we've discovered primary nic
                if primary_nic_found:
                    LOG.info("Found primary nic for this VM.")
                    break
                else:
                    self._teardown_ephemeral_networking()

        except AssertionError as error:
            report_diagnostic_event(str(error), logger_func=LOG.error)

    @azure_ds_telemetry_reporter
    def _create_bound_netlink_socket(self) -> socket.socket:
        try:
            return netlink.create_bound_netlink_socket()
        except netlink.NetlinkCreateSocketError as error:
            report_diagnostic_event(
                f"Failed to create netlink socket: {error}",
                logger_func=LOG.error,
            )
            raise

    @azure_ds_telemetry_reporter
    def _wait_for_pps_os_disk_shutdown(self):
        """Report ready and wait for host to initiate shutdown."""
        self._report_ready_for_pps(create_marker=False)

        report_diagnostic_event(
            "Waiting for host to shutdown VM...",
            logger_func=LOG.info,
        )
        sleep(31536000)
        raise errors.ReportableErrorOsDiskPpsFailure()

    @azure_ds_telemetry_reporter
    def _wait_for_pps_running_reuse(self) -> None:
        """Report ready and wait for nic link to switch upon re-use."""
        nl_sock = self._create_bound_netlink_socket()

        try:
            if (
                self._ephemeral_dhcp_ctx is None
                or self._ephemeral_dhcp_ctx.iface is None
            ):
                raise RuntimeError("missing ephemeral context")

            iface = self._ephemeral_dhcp_ctx.iface
            self._report_ready_for_pps()

            LOG.debug(
                "Wait for vnetswitch to happen on %s",
                iface,
            )
            with events.ReportEventStack(
                name="wait-for-media-disconnect-connect",
                description="wait for vnet switch",
                parent=azure_ds_reporter,
            ):
                try:
                    netlink.wait_for_media_disconnect_connect(nl_sock, iface)
                except AssertionError as e:
                    report_diagnostic_event(
                        "Error while waiting for vnet switch: %s" % e,
                        logger_func=LOG.error,
                    )
        finally:
            nl_sock.close()

        # Teardown source PPS network configuration.
        self._teardown_ephemeral_networking()

    @azure_ds_telemetry_reporter
    def _wait_for_pps_savable_reuse(self):
        """Report ready and wait for nic(s) to be hot-attached upon re-use."""
        nl_sock = self._create_bound_netlink_socket()

        try:
            self._report_ready_for_pps(expect_url_error=True)
            try:
                self._teardown_ephemeral_networking()
            except subp.ProcessExecutionError as e:
                report_diagnostic_event(
                    "Ignoring failure while tearing down networking, "
                    "NIC was likely unplugged: %r" % e,
                    logger_func=LOG.info,
                )
                self._ephemeral_dhcp_ctx = None

            self._wait_for_nic_detach(nl_sock)
            self._wait_for_hot_attached_primary_nic(nl_sock)
        finally:
            nl_sock.close()

    @azure_ds_telemetry_reporter
    def _wait_for_pps_unknown_reuse(self):
        """Report ready if needed for unknown/recovery PPS."""
        if os.path.isfile(self._reported_ready_marker_file):
            # Already reported ready, nothing to do.
            return

        self._report_ready_for_pps()

        # Teardown source PPS network configuration.
        self._teardown_ephemeral_networking()

    @azure_ds_telemetry_reporter
    def _poll_imds(self) -> bytes:
        """Poll IMDs for reprovisiondata XML document data."""
        dhcp_attempts = 0
        reprovision_data: Optional[bytes] = None
        while not reprovision_data:
            if not self._is_ephemeral_networking_up():
                dhcp_attempts += 1
                try:
                    self._setup_ephemeral_networking(timeout_minutes=5)
                except NoDHCPLeaseError:
                    continue

            with events.ReportEventStack(
                name="get-reprovision-data-from-imds",
                description="get reprovision data from imds",
                parent=azure_ds_reporter,
            ):
                try:
                    reprovision_data = imds.fetch_reprovision_data()
                except UrlError:
                    self._teardown_ephemeral_networking()
                    continue

        report_diagnostic_event(
            "attempted dhcp %d times after reuse" % dhcp_attempts,
            logger_func=LOG.debug,
        )
        return reprovision_data

    @azure_ds_telemetry_reporter
    def _report_failure(
        self, error: errors.ReportableError, host_only: bool = False
    ) -> bool:
        """Report failure to Azure host and fabric.

        For errors that may be recoverable (e.g. DHCP), host_only provides a
        mechanism to report the failure that can be updated later with success.
        DHCP will not be attempted if host_only=True and networking is down.

        @param error: Error to report.
        @param host_only: Only report to host (error may be recoverable).
        @return: The success status of sending the failure signal.
        """
        report_diagnostic_event(
            f"Azure datasource failure occurred: {error.as_encoded_report()}",
            logger_func=LOG.error,
        )
        report_dmesg_to_kvp()
        reported = kvp.report_failure_to_host(error)
        if host_only:
            return reported

        if self._is_ephemeral_networking_up():
            try:
                report_diagnostic_event(
                    "Using cached ephemeral dhcp context "
                    "to report failure to Azure",
                    logger_func=LOG.debug,
                )
                report_failure_to_fabric(
                    endpoint=self._wireserver_endpoint, error=error
                )
                self._negotiated = True
                return True
            except Exception as e:
                report_diagnostic_event(
                    "Failed to report failure using "
                    "cached ephemeral dhcp context: %s" % e,
                    logger_func=LOG.error,
                )

        try:
            report_diagnostic_event(
                "Using new ephemeral dhcp to report failure to Azure",
                logger_func=LOG.debug,
            )
            self._teardown_ephemeral_networking()
            try:
                self._setup_ephemeral_networking(timeout_minutes=20)
            except NoDHCPLeaseError:
                # Reporting failure will fail, but it will emit telemetry.
                pass
            report_failure_to_fabric(
                endpoint=self._wireserver_endpoint, error=error
            )
            self._negotiated = True
            return True
        except Exception as e:
            report_diagnostic_event(
                "Failed to report failure using new ephemeral dhcp: %s" % e,
                logger_func=LOG.debug,
            )

        return False

    @azure_ds_telemetry_reporter
    def _report_ready(
        self, *, pubkey_info: Optional[List[str]] = None
    ) -> Optional[List[str]]:
        """Tells the fabric provisioning has completed.

        :param pubkey_info: Fingerprints of keys to request from Wireserver.

        :raises Exception: if failed to report.

        :returns: List of SSH keys, if requested.
        """
        report_dmesg_to_kvp()
        kvp.report_success_to_host()

        try:
            data = get_metadata_from_fabric(
                endpoint=self._wireserver_endpoint,
                distro=self.distro,
                iso_dev=self._iso_dev,
                pubkey_info=pubkey_info,
            )
        except Exception as e:
            report_diagnostic_event(
                "Error communicating with Azure fabric; You may experience "
                "connectivity issues: %s" % e,
                logger_func=LOG.warning,
            )
            raise

        # Reporting ready ejected OVF media, no need to do so again.
        self._iso_dev = None
        self._negotiated = True
        return data

    def _ppstype_from_imds(self, imds_md: dict) -> Optional[str]:
        try:
            return imds_md["extended"]["compute"]["ppsType"]
        except Exception as e:
            report_diagnostic_event(
                "Could not retrieve pps configuration from IMDS: %s" % e,
                logger_func=LOG.debug,
            )
            return None

    def _determine_pps_type(self, ovf_cfg: dict, imds_md: dict) -> PPSType:
        """Determine PPS type using OVF, IMDS data, and reprovision marker."""
        if os.path.isfile(self._reported_ready_marker_file):
            pps_type = PPSType.UNKNOWN
        elif (
            ovf_cfg.get("PreprovisionedVMType", None) == PPSType.SAVABLE.value
            or self._ppstype_from_imds(imds_md) == PPSType.SAVABLE.value
        ):
            pps_type = PPSType.SAVABLE
        elif (
            ovf_cfg.get("PreprovisionedVMType", None) == PPSType.OS_DISK.value
            or self._ppstype_from_imds(imds_md) == PPSType.OS_DISK.value
        ):
            pps_type = PPSType.OS_DISK
        elif (
            ovf_cfg.get("PreprovisionedVm") is True
            or ovf_cfg.get("PreprovisionedVMType", None)
            == PPSType.RUNNING.value
            or self._ppstype_from_imds(imds_md) == PPSType.RUNNING.value
        ):
            pps_type = PPSType.RUNNING
        else:
            pps_type = PPSType.NONE

        report_diagnostic_event(
            "PPS type: %s" % pps_type.value, logger_func=LOG.info
        )
        return pps_type

    @azure_ds_telemetry_reporter
    def _reprovision(self):
        """Initiate the reprovisioning workflow.

        Ephemeral networking is up upon successful reprovisioning.
        """
        contents = self._poll_imds()
        with events.ReportEventStack(
            name="reprovisioning-read-azure-ovf",
            description="read azure ovf during reprovisioning",
            parent=azure_ds_reporter,
        ):
            md, ud, cfg = read_azure_ovf(contents)
            return (md, ud, cfg, {"ovf-env.xml": contents})

    @azure_ds_telemetry_reporter
    def _determine_wireserver_pubkey_info(
        self, *, cfg: dict, imds_md: dict
    ) -> Optional[List[str]]:
        """Determine the fingerprints we need to retrieve from Wireserver.

        :return: List of keys to request from Wireserver, if any, else None.
        """
        pubkey_info: Optional[List[str]] = None
        try:
            self._get_public_keys_from_imds(imds_md)
        except (KeyError, ValueError):
            pubkey_info = cfg.get("_pubkeys", None)
            log_msg = "Retrieved {} fingerprints from OVF".format(
                len(pubkey_info) if pubkey_info is not None else 0
            )
            report_diagnostic_event(log_msg, logger_func=LOG.debug)
        return pubkey_info

    def _cleanup_markers(self):
        """Cleanup any marker files."""
        util.del_file(self._reported_ready_marker_file)

    @azure_ds_telemetry_reporter
    def activate(self, cfg, is_new_instance):
        instance_dir = self.paths.get_ipath_cur()
        try:
            address_ephemeral_resize(
                instance_dir,
                is_new_instance=is_new_instance,
                preserve_ntfs=self.ds_cfg.get(DS_CFG_KEY_PRESERVE_NTFS, False),
            )
        finally:
            report_dmesg_to_kvp()
        return

    @property
    def availability_zone(self):
        return (
            self.metadata.get("imds", {})
            .get("compute", {})
            .get("platformFaultDomain")
        )

    @azure_ds_telemetry_reporter
    def _generate_network_config(self):
        """Generate network configuration according to configuration."""
        # Use IMDS network metadata, if configured.
        if (
            self._metadata_imds
            and self._metadata_imds != sources.UNSET
            and self.ds_cfg.get("apply_network_config")
        ):
            try:
                return generate_network_config_from_instance_network_metadata(
                    self._metadata_imds["network"],
                    apply_network_config_for_secondary_ips=self.ds_cfg.get(
                        "apply_network_config_for_secondary_ips"
                    ),
                )
            except Exception as e:
                LOG.error(
                    "Failed generating network config "
                    "from IMDS network metadata: %s",
                    str(e),
                )

        # Generate fallback configuration.
        try:
            return _generate_network_config_from_fallback_config()
        except Exception as e:
            LOG.error("Failed generating fallback network config: %s", str(e))

        return {}

    @property
    def network_config(self):
        """Provide network configuration v2 dictionary."""
        # Use cached config, if present.
        if self._network_config and self._network_config != sources.UNSET:
            return self._network_config

        self._network_config = self._generate_network_config()
        return self._network_config

    @property
    def region(self):
        return self.metadata.get("imds", {}).get("compute", {}).get("location")

    @azure_ds_telemetry_reporter
    def validate_imds_network_metadata(self, imds_md: dict) -> bool:
        """Validate IMDS network config and report telemetry for errors."""
        local_macs = get_hv_netvsc_macs_normalized()

        try:
            network_config = imds_md["network"]
            imds_macs = [
                normalize_mac_address(i["macAddress"])
                for i in network_config["interface"]
            ]
        except KeyError:
            report_diagnostic_event(
                "IMDS network metadata has incomplete configuration: %r"
                % imds_md.get("network"),
                logger_func=LOG.warning,
            )
            return False

        missing_macs = [m for m in local_macs if m not in imds_macs]
        if not missing_macs:
            return True

        report_diagnostic_event(
            "IMDS network metadata is missing configuration for NICs %r: %r"
            % (missing_macs, network_config),
            logger_func=LOG.warning,
        )

        if not self._ephemeral_dhcp_ctx or not self._ephemeral_dhcp_ctx.iface:
            # No primary interface to check against.
            return False

        primary_mac = net.get_interface_mac(self._ephemeral_dhcp_ctx.iface)
        if not primary_mac or not isinstance(primary_mac, str):
            # Unexpected data for primary interface.
            return False

        primary_mac = normalize_mac_address(primary_mac)
        if primary_mac in missing_macs:
            report_diagnostic_event(
                "IMDS network metadata is missing primary NIC %r: %r"
                % (primary_mac, network_config),
                logger_func=LOG.warning,
            )

        return False


def _username_from_imds(imds_data):
    try:
        return imds_data["compute"]["osProfile"]["adminUsername"]
    except KeyError:
        return None


def _userdata_from_imds(imds_data):
    try:
        return imds_data["compute"]["userData"]
    except KeyError:
        return None


def _hostname_from_imds(imds_data):
    try:
        return imds_data["compute"]["osProfile"]["computerName"]
    except KeyError:
        return None


def _disable_password_from_imds(imds_data):
    try:
        return (
            imds_data["compute"]["osProfile"]["disablePasswordAuthentication"]
            == "true"
        )
    except KeyError:
        return None


def _key_is_openssh_formatted(key):
    """
    Validate whether or not the key is OpenSSH-formatted.
    """
    # See https://bugs.launchpad.net/cloud-init/+bug/1910835
    if "\r\n" in key.strip():
        return False

    parser = ssh_util.AuthKeyLineParser()
    try:
        akl = parser.parse(key)
    except TypeError:
        return False

    return akl.keytype is not None


def _partitions_on_device(devpath, maxnum=16):
    # return a list of tuples (ptnum, path) for each part on devpath
    for suff in ("-part", "p", ""):
        found = []
        for pnum in range(1, maxnum):
            ppath = devpath + suff + str(pnum)
            if os.path.exists(ppath):
                found.append((pnum, os.path.realpath(ppath)))
        if found:
            return found
    return []


@azure_ds_telemetry_reporter
def _has_ntfs_filesystem(devpath):
    ntfs_devices = util.find_devs_with("TYPE=ntfs", no_cache=True)
    LOG.debug("ntfs_devices found = %s", ntfs_devices)
    return os.path.realpath(devpath) in ntfs_devices


@azure_ds_telemetry_reporter
def can_dev_be_reformatted(devpath, preserve_ntfs):
    """Determine if the ephemeral drive at devpath should be reformatted.

    A fresh ephemeral disk is formatted by Azure and will:
      a.) have a partition table (dos or gpt)
      b.) have 1 partition that is ntfs formatted, or
          have 2 partitions with the second partition ntfs formatted.
          (larger instances with >2TB ephemeral disk have gpt, and will
           have a microsoft reserved partition as part 1.  LP: #1686514)
      c.) the ntfs partition will have no files other than possibly
          'dataloss_warning_readme.txt'

    User can indicate that NTFS should never be destroyed by setting
    DS_CFG_KEY_PRESERVE_NTFS in dscfg.
    If data is found on NTFS, user is warned to set DS_CFG_KEY_PRESERVE_NTFS
    to make sure cloud-init does not accidentally wipe their data.
    If cloud-init cannot mount the disk to check for data, destruction
    will be allowed, unless the dscfg key is set."""
    if preserve_ntfs:
        msg = "config says to never destroy NTFS (%s.%s), skipping checks" % (
            ".".join(DS_CFG_PATH),
            DS_CFG_KEY_PRESERVE_NTFS,
        )
        return False, msg

    if not os.path.exists(devpath):
        return False, "device %s does not exist" % devpath

    LOG.debug(
        "Resolving realpath of %s -> %s", devpath, os.path.realpath(devpath)
    )

    # devpath of /dev/sd[a-z] or /dev/disk/cloud/azure_resource
    # where partitions are "<devpath>1" or "<devpath>-part1" or "<devpath>p1"
    partitions = _partitions_on_device(devpath)
    if len(partitions) == 0:
        return False, "device %s was not partitioned" % devpath
    elif len(partitions) > 2:
        msg = "device %s had 3 or more partitions: %s" % (
            devpath,
            " ".join([p[1] for p in partitions]),
        )
        return False, msg
    elif len(partitions) == 2:
        cand_part, cand_path = partitions[1]
    else:
        cand_part, cand_path = partitions[0]

    if not _has_ntfs_filesystem(cand_path):
        msg = "partition %s (%s) on device %s was not ntfs formatted" % (
            cand_part,
            cand_path,
            devpath,
        )
        return False, msg

    @azure_ds_telemetry_reporter
    def count_files(mp):
        ignored = set(
            ["dataloss_warning_readme.txt", "system volume information"]
        )
        return len([f for f in os.listdir(mp) if f.lower() not in ignored])

    bmsg = "partition %s (%s) on device %s was ntfs formatted" % (
        cand_part,
        cand_path,
        devpath,
    )

    with events.ReportEventStack(
        name="mount-ntfs-and-count",
        description="mount-ntfs-and-count",
        parent=azure_ds_reporter,
    ) as evt:
        try:
            file_count = util.mount_cb(
                cand_path,
                count_files,
                mtype="ntfs",
                update_env_for_mount={"LANG": "C"},
                log_error=False,
            )
        except util.MountFailedError as e:
            evt.description = "cannot mount ntfs"
            if "unknown filesystem type 'ntfs'" in str(e):
                return (
                    True,
                    (
                        bmsg + " but this system cannot mount NTFS,"
                        " assuming there are no important files."
                        " Formatting allowed."
                    ),
                )
            return False, bmsg + " but mount of %s failed: %s" % (cand_part, e)

        if file_count != 0:
            evt.description = "mounted and counted %d files" % file_count
            LOG.warning(
                "it looks like you're using NTFS on the ephemeral"
                " disk, to ensure that filesystem does not get wiped,"
                " set %s.%s in config",
                ".".join(DS_CFG_PATH),
                DS_CFG_KEY_PRESERVE_NTFS,
            )
            return False, bmsg + " but had %d files on it." % file_count

    return True, bmsg + " and had no important files. Safe for reformatting."


@azure_ds_telemetry_reporter
def address_ephemeral_resize(
    instance_dir: str,
    devpath: str = RESOURCE_DISK_PATH,
    is_new_instance: bool = False,
    preserve_ntfs: bool = False,
):
    if not os.path.exists(devpath):
        report_diagnostic_event(
            "Ephemeral resource disk '%s' does not exist." % devpath,
            logger_func=LOG.debug,
        )
        return
    else:
        report_diagnostic_event(
            "Ephemeral resource disk '%s' exists." % devpath,
            logger_func=LOG.debug,
        )

    result = False
    msg = None
    if is_new_instance:
        result, msg = (True, "First instance boot.")
    else:
        result, msg = can_dev_be_reformatted(devpath, preserve_ntfs)

    LOG.debug("reformattable=%s: %s", result, msg)
    if not result:
        return

    for mod in ["disk_setup", "mounts"]:
        sempath = os.path.join(instance_dir, "sem", "config_" + mod)
        bmsg = 'Marker "%s" for module "%s"' % (sempath, mod)
        if os.path.exists(sempath):
            try:
                os.unlink(sempath)
                LOG.debug("%s removed.", bmsg)
            except FileNotFoundError as e:
                LOG.warning("%s: remove failed! (%s)", bmsg, e)
        else:
            LOG.debug("%s did not exist.", bmsg)
    return


@azure_ds_telemetry_reporter
def write_files(datadir, files, dirmode=None):
    def _redact_password(cnt, fname):
        """Azure provides the UserPassword in plain text. So we redact it"""
        try:
            root = ET.fromstring(cnt)  # nosec B314
            for elem in root.iter():
                if (
                    "UserPassword" in elem.tag
                    and elem.text != DEF_PASSWD_REDACTION
                ):
                    elem.text = DEF_PASSWD_REDACTION
            return ET.tostring(root)
        except Exception:
            LOG.critical("failed to redact userpassword in %s", fname)
            return cnt

    if not datadir:
        return
    if not files:
        files = {}
    util.ensure_dir(datadir, dirmode)
    for name, content in files.items():
        fname = os.path.join(datadir, name)
        if "ovf-env.xml" in name:
            content = _redact_password(content, fname)
        util.write_file(filename=fname, content=content, mode=0o600)


@azure_ds_telemetry_reporter
def read_azure_ovf(contents):
    """Parse OVF XML contents.

    :return: Tuple of metadata, configuration, userdata dicts.

    :raises NonAzureDataSource: if XML is not in Azure's format.
    :raises errors.ReportableError: if XML is unparsable or invalid.
    """
    ovf_env = OvfEnvXml.parse_text(contents)
    md: Dict[str, Any] = {}
    cfg = {}
    ud = ovf_env.custom_data or ""

    if ovf_env.hostname:
        md["local-hostname"] = ovf_env.hostname

    if ovf_env.public_keys:
        cfg["_pubkeys"] = ovf_env.public_keys

    if ovf_env.disable_ssh_password_auth is not None:
        cfg["ssh_pwauth"] = not ovf_env.disable_ssh_password_auth
    elif ovf_env.password:
        cfg["ssh_pwauth"] = True

    defuser = {}
    if ovf_env.username:
        defuser["name"] = ovf_env.username
    if ovf_env.password:
        defuser["lock_passwd"] = False
        if DEF_PASSWD_REDACTION != ovf_env.password:
            defuser["hashed_passwd"] = encrypt_pass(ovf_env.password)

    if defuser:
        cfg["system_info"] = {"default_user": defuser}

    cfg["PreprovisionedVm"] = ovf_env.preprovisioned_vm
    report_diagnostic_event(
        "PreprovisionedVm: %s" % ovf_env.preprovisioned_vm,
        logger_func=LOG.info,
    )

    cfg["PreprovisionedVMType"] = ovf_env.preprovisioned_vm_type
    report_diagnostic_event(
        "PreprovisionedVMType: %s" % ovf_env.preprovisioned_vm_type,
        logger_func=LOG.info,
    )

    cfg["ProvisionGuestProxyAgent"] = ovf_env.provision_guest_proxy_agent
    report_diagnostic_event(
        "ProvisionGuestProxyAgent: %s" % ovf_env.provision_guest_proxy_agent,
        logger_func=LOG.info,
    )
    return (md, ud, cfg)


def encrypt_pass(password):
    return blowfish_hash(password)


@azure_ds_telemetry_reporter
def _check_freebsd_cdrom(cdrom_dev):
    """Return boolean indicating path to cdrom device has content."""
    try:
        with open(cdrom_dev) as fp:
            fp.read(1024)
            return True
    except IOError:
        LOG.debug("cdrom (%s) is not configured", cdrom_dev)
    return False


@azure_ds_telemetry_reporter
def _get_random_seed(source=PLATFORM_ENTROPY_SOURCE):
    """Return content random seed file if available, otherwise,
    return None."""
    # azure / hyper-v provides random data here
    # now update ds_cfg to reflect contents pass in config
    if source is None:
        return None
    seed = util.load_binary_file(source, quiet=True)

    # The seed generally contains non-Unicode characters. load_binary_file puts
    # them into bytes (in python 3).
    # bytes is a non-serializable type, and the handler
    # used applies b64 encoding *again* to handle it. The simplest solution
    # is to just b64encode the data and then decode it to a serializable
    # string. Same number of bits of entropy, just with 25% more zeroes.
    # There's no need to undo this base64-encoding when the random seed is
    # actually used in cc_seed_random.py.
    return base64.b64encode(seed).decode()  # pyright: ignore


@azure_ds_telemetry_reporter
def list_possible_azure_ds(seed, cache_dir):
    yield seed
    yield DEFAULT_PROVISIONING_ISO_DEV
    if util.is_FreeBSD():
        cdrom_dev = "/dev/cd0"
        if _check_freebsd_cdrom(cdrom_dev):
            yield cdrom_dev
    else:
        for fstype in ("iso9660", "udf"):
            yield from util.find_devs_with("TYPE=%s" % fstype)
    if cache_dir:
        yield cache_dir


@azure_ds_telemetry_reporter
def load_azure_ds_dir(source_dir):
    ovf_file = os.path.join(source_dir, "ovf-env.xml")

    if not os.path.isfile(ovf_file):
        raise NonAzureDataSource("No ovf-env file found")

    with open(ovf_file, "rb") as fp:
        contents = fp.read()

    md, ud, cfg = read_azure_ovf(contents)
    return (md, ud, cfg, {"ovf-env.xml": contents})


@azure_ds_telemetry_reporter
def generate_network_config_from_instance_network_metadata(
    network_metadata: dict,
    *,
    apply_network_config_for_secondary_ips: bool,
) -> dict:
    """Convert imds network metadata dictionary to network v2 configuration.

    :param: network_metadata: Dict of "network" key from instance metadata.

    :return: Dictionary containing network version 2 standard configuration.
    """
    netconfig: Dict[str, Any] = {"version": 2, "ethernets": {}}
    for idx, intf in enumerate(network_metadata["interface"]):
        has_ip_address = False
        # First IPv4 and/or IPv6 address will be obtained via DHCP.
        # Any additional IPs of each type will be set as static
        # addresses.
        nicname = "eth{idx}".format(idx=idx)
        dhcp_override = {"route-metric": (idx + 1) * 100}
        # DNS resolution through secondary NICs is not supported, disable it.
        if idx > 0:
            dhcp_override["use-dns"] = False
        dev_config: Dict[str, Any] = {
            "dhcp4": True,
            "dhcp4-overrides": dhcp_override,
            "dhcp6": False,
        }
        for addr_type in ("ipv4", "ipv6"):
            addresses = intf.get(addr_type, {}).get("ipAddress", [])
            # If there are no available IP addresses, then we don't
            # want to add this interface to the generated config.
            if not addresses:
                LOG.debug("No %s addresses found for: %r", addr_type, intf)
                continue
            has_ip_address = True
            if addr_type == "ipv4":
                default_prefix = "24"
            else:
                default_prefix = "128"
                if addresses:
                    dev_config["dhcp6"] = True
                    # non-primary interfaces should have a higher
                    # route-metric (cost) so default routes prefer
                    # primary nic due to lower route-metric value
                    dev_config["dhcp6-overrides"] = dhcp_override

            if not apply_network_config_for_secondary_ips:
                continue

            for addr in addresses[1:]:
                # Append static address config for ip > 1
                netPrefix = intf[addr_type]["subnet"][0].get(
                    "prefix", default_prefix
                )
                privateIp = addr["privateIpAddress"]
                if not dev_config.get("addresses"):
                    dev_config["addresses"] = []
                dev_config["addresses"].append(
                    "{ip}/{prefix}".format(ip=privateIp, prefix=netPrefix)
                )
        if dev_config and has_ip_address:
            mac = normalize_mac_address(intf["macAddress"])
            dev_config.update(
                {"match": {"macaddress": mac.lower()}, "set-name": nicname}
            )
            driver = determine_device_driver_for_mac(mac)
            if driver:
                dev_config["match"]["driver"] = driver
            netconfig["ethernets"][nicname] = dev_config
            continue

        LOG.debug(
            "No configuration for: %s (dev_config=%r) (has_ip_address=%r)",
            nicname,
            dev_config,
            has_ip_address,
        )
    return netconfig


@azure_ds_telemetry_reporter
def _generate_network_config_from_fallback_config() -> dict:
    """Generate fallback network config.

    @return: Dictionary containing network version 2 standard configuration.
    """
    cfg = net.generate_fallback_config(config_driver=True)
    if cfg is None:
        return {}
    return cfg


@azure_ds_telemetry_reporter
def maybe_remove_ubuntu_network_config_scripts(paths=None):
    """Remove Azure-specific ubuntu network config for non-primary nics.

    @param paths: List of networking scripts or directories to remove when
        present.

    In certain supported ubuntu images, static udev rules or netplan yaml
    config is delivered in the base ubuntu image to support dhcp on any
    additional interfaces which get attached by a customer at some point
    after initial boot. Since the Azure datasource can now regenerate
    network configuration as metadata reports these new devices, we no longer
    want the udev rules or netplan's 90-hotplug-azure.yaml to configure
    networking on eth1 or greater as it might collide with cloud-init's
    configuration.

    Remove the any existing extended network scripts if the datasource is
    enabled to write network per-boot.
    """
    if not paths:
        paths = UBUNTU_EXTENDED_NETWORK_SCRIPTS
    logged = False
    for path in paths:
        if os.path.exists(path):
            if not logged:
                LOG.info(
                    "Removing Ubuntu extended network scripts because"
                    " cloud-init updates Azure network configuration on the"
                    " following events: %s.",
                    [EventType.BOOT.value, EventType.BOOT_LEGACY.value],
                )
                logged = True
            if os.path.isdir(path):
                util.del_dir(path)
            else:
                util.del_file(path)


# Legacy: Must be present in case we load an old pkl object
DataSourceAzureNet = DataSourceAzure

# Used to match classes to dependencies
datasources = [
    (DataSourceAzure, (sources.DEP_FILESYSTEM,)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
