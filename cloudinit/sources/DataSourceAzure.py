# Copyright (C) 2013 Canonical Ltd.
#
# Author: Scott Moser <scott.moser@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import base64
import crypt
import datetime
import os
import os.path
import re
import xml.etree.ElementTree as ET
from enum import Enum
from time import sleep, time
from typing import Any, Dict, List, Optional
from xml.dom import minidom

import requests

from cloudinit import dmi
from cloudinit import log as logging
from cloudinit import net, sources, ssh_util, subp, util
from cloudinit.event import EventScope, EventType
from cloudinit.net import device_driver
from cloudinit.net.dhcp import EphemeralDHCPv4, NoDHCPLeaseError
from cloudinit.reporting import events
from cloudinit.sources.helpers import netlink
from cloudinit.sources.helpers.azure import (
    DEFAULT_REPORT_FAILURE_USER_VISIBLE_MESSAGE,
    DEFAULT_WIRESERVER_ENDPOINT,
    azure_ds_reporter,
    azure_ds_telemetry_reporter,
    build_minimal_ovf,
    dhcp_log_cb,
    get_boot_telemetry,
    get_metadata_from_fabric,
    get_system_info,
    is_byte_swapped,
    push_log_to_kvp,
    report_diagnostic_event,
    report_failure_to_fabric,
)
from cloudinit.url_helper import UrlError, readurl, retry_on_url_exc

LOG = logging.getLogger(__name__)

DS_NAME = "Azure"
DEFAULT_METADATA = {"instance-id": "iid-AZURE-NODE"}

# azure systems will always have a resource disk, and 66-azure-ephemeral.rules
# ensures that it gets linked to this path.
RESOURCE_DISK_PATH = "/dev/disk/cloud/azure_resource"
LEASE_FILE = "/var/lib/dhcp/dhclient.eth0.leases"
DEFAULT_FS = "ext4"
# DMI chassis-asset-tag is set static for all azure instances
AZURE_CHASSIS_ASSET_TAG = "7783-7084-3265-9085-8269-3286-77"
REPROVISION_MARKER_FILE = "/var/lib/cloud/data/poll_imds"
REPROVISION_NIC_DETACHED_MARKER_FILE = "/var/lib/cloud/data/nic_detached"
REPORTED_READY_MARKER_FILE = "/var/lib/cloud/data/reported_ready"
AGENT_SEED_DIR = "/var/lib/waagent"
DEFAULT_PROVISIONING_ISO_DEV = "/dev/sr0"

# In the event where the IMDS primary server is not
# available, it takes 1s to fallback to the secondary one
IMDS_TIMEOUT_IN_SECONDS = 2
IMDS_URL = "http://169.254.169.254/metadata"
IMDS_VER_MIN = "2019-06-01"
IMDS_VER_WANT = "2021-08-01"
IMDS_EXTENDED_VER_MIN = "2021-03-01"


class MetadataType(Enum):
    ALL = "{}/instance".format(IMDS_URL)
    NETWORK = "{}/instance/network".format(IMDS_URL)
    REPROVISION_DATA = "{}/reprovisiondata".format(IMDS_URL)


class PPSType(Enum):
    NONE = "None"
    RUNNING = "Running"
    SAVABLE = "Savable"
    UNKNOWN = "Unknown"


PLATFORM_ENTROPY_SOURCE: Optional[str] = "/sys/firmware/acpi/tables/OEM0"

# List of static scripts and network config artifacts created by
# stock ubuntu suported images.
UBUNTU_EXTENDED_NETWORK_SCRIPTS = [
    "/etc/netplan/90-hotplug-azure.yaml",
    "/usr/local/sbin/ephemeral_eth.sh",
    "/etc/udev/rules.d/10-net-device-added.rules",
    "/run/network/interfaces.ephemeral.d",
]

# This list is used to blacklist devices that will be considered
# for renaming or fallback interfaces.
#
# On Azure network devices using these drivers are automatically
# configured by the platform and should not be configured by
# cloud-init's network configuration.
#
# Note:
# Azure Dv4 and Ev4 series VMs always have mlx5 hardware.
# https://docs.microsoft.com/en-us/azure/virtual-machines/dv4-dsv4-series
# https://docs.microsoft.com/en-us/azure/virtual-machines/ev4-esv4-series
# Earlier D and E series VMs (such as Dv2, Dv3, and Ev3 series VMs)
# can have either mlx4 or mlx5 hardware, with the older series VMs
# having a higher chance of coming with mlx4 hardware.
# https://docs.microsoft.com/en-us/azure/virtual-machines/dv2-dsv2-series
# https://docs.microsoft.com/en-us/azure/virtual-machines/dv3-dsv3-series
# https://docs.microsoft.com/en-us/azure/virtual-machines/ev3-esv3-series
BLACKLIST_DRIVERS = ["mlx4_core", "mlx5_core"]


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


def execute_or_debug(cmd, fail_ret=None) -> str:
    try:
        return subp.subp(cmd)[0]  # type: ignore
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
    LEASE_FILE = "/var/db/dhclient.leases.hn0"
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
    "dhclient_lease_file": LEASE_FILE,
    "apply_network_config": True,  # Use IMDS published network configuration
}
# RELEASE_BLOCKER: Xenial and earlier apply_network_config default is False

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
DEF_EPHEMERAL_LABEL = "Temporary Storage"

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
        self.dhclient_lease_file = self.ds_cfg.get("dhclient_lease_file")
        self._iso_dev = None
        self._network_config = None
        self._ephemeral_dhcp_ctx = None
        self._wireserver_endpoint = DEFAULT_WIRESERVER_ENDPOINT

    def _unpickle(self, ci_pkl_version: int) -> None:
        super()._unpickle(ci_pkl_version)

        self._ephemeral_dhcp_ctx = None
        self._iso_dev = None
        self._wireserver_endpoint = DEFAULT_WIRESERVER_ENDPOINT

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
    def _setup_ephemeral_networking(
        self, *, iface: Optional[str] = None, timeout_minutes: int = 5
    ) -> None:
        """Setup ephemeral networking.

        Keep retrying DHCP up to specified number of minutes.  This does
        not kill dhclient, so the timeout in practice may be up to
        timeout_minutes + the system-configured timeout for dhclient.

        :param timeout_minutes: Number of minutes to keep retrying for.

        :raises NoDHCPLeaseError: If unable to obtain DHCP lease.
        """
        if self._ephemeral_dhcp_ctx is not None:
            raise RuntimeError(
                "Bringing up networking when already configured."
            )

        LOG.debug("Requested ephemeral networking (iface=%s)", iface)

        start = datetime.datetime.utcnow()
        timeout = start + datetime.timedelta(minutes=timeout_minutes)

        self._ephemeral_dhcp_ctx = EphemeralDHCPv4(
            iface=iface, dhcp_log_func=dhcp_log_cb
        )

        lease = None
        with events.ReportEventStack(
            name="obtain-dhcp-lease",
            description="obtain dhcp lease",
            parent=azure_ds_reporter,
        ):
            while datetime.datetime.utcnow() < timeout:
                try:
                    lease = self._ephemeral_dhcp_ctx.obtain_lease()
                    break
                except NoDHCPLeaseError:
                    continue

            if lease is None:
                msg = "Failed to obtain DHCP lease (iface=%s)" % iface
                report_diagnostic_event(msg, logger_func=LOG.error)
                self._ephemeral_dhcp_ctx = None
                raise NoDHCPLeaseError()
            else:
                # Ensure iface is set.
                self._ephemeral_dhcp_ctx.iface = lease["interface"]

                # Update wireserver IP from DHCP options.
                if "unknown-245" in lease:
                    self._wireserver_endpoint = lease["unknown-245"]

    @azure_ds_telemetry_reporter
    def _teardown_ephemeral_networking(self) -> None:
        """Teardown ephemeral networking."""
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
        ovf_is_accessible = False
        metadata_source = None
        md = {}
        userdata_raw = ""
        cfg = {}
        files = {}

        if os.path.isfile(REPROVISION_MARKER_FILE):
            metadata_source = "IMDS"
            report_diagnostic_event(
                "Reprovision marker file already present "
                "before crawling Azure metadata: %s" % REPROVISION_MARKER_FILE,
                logger_func=LOG.debug,
            )
        else:
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
                    ovf_is_accessible = True
                    metadata_source = src
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
                    md = {"local-hostname": ""}
                    cfg = {"system_info": {"default_user": {"name": ""}}}
                    metadata_source = "IMDS"
                    continue
                except BrokenAzureDataSource as exc:
                    msg = "BrokenAzureDataSource: %s" % exc
                    report_diagnostic_event(msg, logger_func=LOG.error)
                    raise sources.InvalidMetaDataException(msg)

        report_diagnostic_event(
            "Found provisioning metadata in %s" % metadata_source,
            logger_func=LOG.debug,
        )

        # If we read OVF from attached media, we are provisioning.  If OVF
        # is not found, we are probably provisioning on a system which does
        # not have UDF support.  In either case, require IMDS metadata.
        # If we require IMDS metadata, try harder to obtain networking, waiting
        # for at least 20 minutes.  Otherwise only wait 5 minutes.
        requires_imds_metadata = bool(self._iso_dev) or not ovf_is_accessible
        timeout_minutes = 5 if requires_imds_metadata else 20
        try:
            self._setup_ephemeral_networking(timeout_minutes=timeout_minutes)
        except NoDHCPLeaseError:
            pass

        if self._is_ephemeral_networking_up():
            imds_md = self.get_imds_data_with_api_fallback(retries=10)
        else:
            imds_md = {}

        if not imds_md and not ovf_is_accessible:
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

            self._write_reprovision_marker()

            if pps_type == PPSType.SAVABLE:
                self._wait_for_all_nics_ready()

            md, userdata_raw, cfg, files = self._reprovision()
            # fetch metadata again as it has changed after reprovisioning
            imds_md = self.get_imds_data_with_api_fallback(retries=10)

        # Report errors if IMDS network configuration is missing data.
        self.validate_imds_network_metadata(imds_md=imds_md)

        self.seed = metadata_source
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

        if metadata_source == "IMDS" and not crawled_data["files"]:
            try:
                contents = build_minimal_ovf(
                    username=imds_username,  # type: ignore
                    hostname=imds_hostname,  # type: ignore
                    disableSshPwd=imds_disable_password,  # type: ignore
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

        if not metadata_source:
            msg = "No Azure metadata found"
            report_diagnostic_event(msg, logger_func=LOG.error)
            raise sources.InvalidMetaDataException(msg)
        else:
            report_diagnostic_event(
                "found datasource in %s" % metadata_source,
                logger_func=LOG.debug,
            )

        if metadata_source == ddir:
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
                self._negotiated = True

        return crawled_data

    def _is_platform_viable(self):
        """Check platform environment to report if this datasource may run."""
        return _is_platform_viable(self.seed_dir)

    def clear_cached_attrs(self, attr_defaults=()):
        """Reset any cached class attributes to defaults."""
        super(DataSourceAzure, self).clear_cached_attrs(attr_defaults)
        self._metadata_imds = sources.UNSET

    @azure_ds_telemetry_reporter
    def _get_data(self):
        """Crawl and process datasource metadata caching metadata as attrs.

        @return: True on success, False on error, invalid or disabled
            datasource.
        """
        if not self._is_platform_viable():
            return False
        try:
            get_boot_telemetry()
        except Exception as e:
            LOG.warning("Failed to get boot telemetry: %s", e)

        try:
            get_system_info()
        except Exception as e:
            LOG.warning("Failed to get system information: %s", e)

        self.distro.networking.blacklist_drivers = BLACKLIST_DRIVERS

        try:
            crawled_data = util.log_time(
                logfunc=LOG.debug,
                msg="Crawl of metadata service",
                func=self.crawl_metadata,
            )
        except Exception as e:
            report_diagnostic_event(
                "Could not crawl Azure metadata: %s" % e, logger_func=LOG.error
            )
            self._report_failure(
                description=DEFAULT_REPORT_FAILURE_USER_VISIBLE_MESSAGE
            )
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

        user_ds_cfg = util.get_cfg_by_path(self.cfg, DS_CFG_PATH, {})
        self.ds_cfg = util.mergemanydict([user_ds_cfg, self.ds_cfg])

        # walinux agent writes files world readable, but expects
        # the directory to be protected.
        write_files(
            self.ds_cfg["data_dir"], crawled_data["files"], dirmode=0o700
        )
        return True

    @azure_ds_telemetry_reporter
    def get_imds_data_with_api_fallback(
        self,
        *,
        retries,
        md_type=MetadataType.ALL,
        exc_cb=retry_on_url_exc,
        infinite=False,
    ):
        """
        Wrapper for get_metadata_from_imds so that we can have flexibility
        in which IMDS api-version we use. If a particular instance of IMDS
        does not have the api version that is desired, we want to make
        this fault tolerant and fall back to a good known minimum api
        version.
        """
        for _ in range(retries):
            try:
                LOG.info("Attempting IMDS api-version: %s", IMDS_VER_WANT)
                return get_metadata_from_imds(
                    retries=0,
                    md_type=md_type,
                    api_version=IMDS_VER_WANT,
                    exc_cb=exc_cb,
                )
            except UrlError as err:
                LOG.info("UrlError with IMDS api-version: %s", IMDS_VER_WANT)
                if err.code == 400:
                    log_msg = "Fall back to IMDS api-version: {}".format(
                        IMDS_VER_MIN
                    )
                    report_diagnostic_event(log_msg, logger_func=LOG.info)
                    break

        LOG.info("Using IMDS api-version: %s", IMDS_VER_MIN)
        return get_metadata_from_imds(
            retries=retries,
            md_type=md_type,
            api_version=IMDS_VER_MIN,
            exc_cb=exc_cb,
            infinite=infinite,
        )

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
        # Older kernels than 4.15 will have UPPERCASE product_uuid.
        # We don't want Azure to react to an UPPER/lower difference as a new
        # instance id as it rewrites SSH host keys.
        # LP: #1835584
        system_uuid = dmi.read_dmi_data("system-uuid")
        if system_uuid is None:
            raise RuntimeError("failed to read system-uuid")

        iid = system_uuid.lower()
        if os.path.exists(prev_iid_path):
            previous = util.load_file(prev_iid_path).strip()
            if previous.lower() == iid:
                # If uppercase/lowercase equivalent, return the previous value
                # to avoid new instance id.
                return previous
            if is_byte_swapped(previous.lower(), iid):
                return previous
        return iid

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
                    logger_func=LOG.warning,
                )
            path = REPROVISION_NIC_DETACHED_MARKER_FILE
            LOG.info("Creating a marker file for nic detached: %s", path)
            util.write_file(
                path, "{pid}: {time}\n".format(pid=os.getpid(), time=time())
            )
        except AssertionError as error:
            report_diagnostic_event(str(error), logger_func=LOG.error)
            raise

    @azure_ds_telemetry_reporter
    def wait_for_link_up(self, ifname):
        """In cases where the link state is still showing down after a nic is
        hot-attached, we can attempt to bring it up by forcing the hv_netvsc
        drivers to query the link state by unbinding and then binding the
        device. This function attempts infinitely until the link is up,
        because we cannot proceed further until we have a stable link."""

        if self.distro.networking.try_set_link_up(ifname):
            report_diagnostic_event(
                "The link %s is already up." % ifname, logger_func=LOG.info
            )
            return

        LOG.debug("Attempting to bring %s up", ifname)

        attempts = 0
        LOG.info("Unbinding and binding the interface %s", ifname)
        while True:
            device_id = net.read_sys_net(ifname, "device/device_id")
            if device_id is False or not isinstance(device_id, str):
                raise RuntimeError("Unable to read device ID: %s" % device_id)
            devicename = device_id.strip("{}")
            util.write_file(
                "/sys/bus/vmbus/drivers/hv_netvsc/unbind", devicename
            )
            util.write_file(
                "/sys/bus/vmbus/drivers/hv_netvsc/bind", devicename
            )

            attempts = attempts + 1
            if self.distro.networking.try_set_link_up(ifname):
                msg = "The link %s is up after %s attempts" % (
                    ifname,
                    attempts,
                )
                report_diagnostic_event(msg, logger_func=LOG.info)
                return

            if attempts % 10 == 0:
                msg = "Link is not up after %d attempts to rebind" % attempts
                report_diagnostic_event(msg, logger_func=LOG.info)
                LOG.info(msg)

            # It could take some time after rebind for the interface to be up.
            # So poll for the status for some time before attempting to rebind
            # again.
            sleep_duration = 0.5
            max_status_polls = 20
            LOG.debug(
                "Polling %d seconds for primary NIC link up after rebind.",
                sleep_duration * max_status_polls,
            )

            for i in range(0, max_status_polls):
                if self.distro.networking.is_up(ifname):
                    msg = (
                        "After %d attempts to rebind, link is up after "
                        "polling the link status %d times" % (attempts, i)
                    )
                    report_diagnostic_event(msg, logger_func=LOG.info)
                    LOG.debug(msg)
                    return
                else:
                    sleep(sleep_duration)

    @azure_ds_telemetry_reporter
    def _create_report_ready_marker(self):
        path = REPORTED_READY_MARKER_FILE
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
    def _report_ready_for_pps(self) -> None:
        """Report ready for PPS, creating the marker file upon completion.

        :raises sources.InvalidMetaDataException: On error reporting ready.
        """
        try:
            self._report_ready()
        except Exception as error:
            msg = "Failed reporting ready while in the preprovisioning pool."
            report_diagnostic_event(msg, logger_func=LOG.error)
            raise sources.InvalidMetaDataException(msg) from error

        self._create_report_ready_marker()

    @azure_ds_telemetry_reporter
    def _check_if_nic_is_primary(self, ifname):
        """Check if a given interface is the primary nic or not. If it is the
        primary nic, then we also get the expected total nic count from IMDS.
        IMDS will process the request and send a response only for primary NIC.
        """
        is_primary = False
        expected_nic_count = -1
        imds_md = None
        metadata_poll_count = 0
        metadata_logging_threshold = 1
        expected_errors_count = 0

        # For now, only a VM's primary NIC can contact IMDS and WireServer. If
        # DHCP fails for a NIC, we have no mechanism to determine if the NIC is
        # primary or secondary. In this case, retry DHCP until successful.
        self._setup_ephemeral_networking(iface=ifname, timeout_minutes=20)

        # Retry polling network metadata for a limited duration only when the
        # calls fail due to network unreachable error or timeout.
        # This is because the platform drops packets going towards IMDS
        # when it is not a primary nic. If the calls fail due to other issues
        # like 410, 503 etc, then it means we are primary but IMDS service
        # is unavailable at the moment. Retry indefinitely in those cases
        # since we cannot move on without the network metadata. In the future,
        # all this will not be necessary, as a new dhcp option would tell
        # whether the nic is primary or not.
        def network_metadata_exc_cb(msg, exc):
            nonlocal expected_errors_count, metadata_poll_count
            nonlocal metadata_logging_threshold

            metadata_poll_count = metadata_poll_count + 1

            # Log when needed but back off exponentially to avoid exploding
            # the log file.
            if metadata_poll_count >= metadata_logging_threshold:
                metadata_logging_threshold *= 2
                report_diagnostic_event(
                    "Ran into exception when attempting to reach %s "
                    "after %d polls." % (msg, metadata_poll_count),
                    logger_func=LOG.error,
                )

                if isinstance(exc, UrlError):
                    report_diagnostic_event(
                        "poll IMDS with %s failed. Exception: %s and code: %s"
                        % (msg, exc.cause, exc.code),
                        logger_func=LOG.error,
                    )

            # Retry up to a certain limit for both timeout and network
            # unreachable errors.
            if exc.cause and isinstance(
                exc.cause, (requests.Timeout, requests.ConnectionError)
            ):
                expected_errors_count = expected_errors_count + 1
                return expected_errors_count <= 10
            return True

        # Primary nic detection will be optimized in the future. The fact that
        # primary nic is being attached first helps here. Otherwise each nic
        # could add several seconds of delay.
        try:
            imds_md = self.get_imds_data_with_api_fallback(
                retries=0,
                md_type=MetadataType.NETWORK,
                exc_cb=network_metadata_exc_cb,
                infinite=True,
            )
        except Exception as e:
            LOG.warning(
                "Failed to get network metadata using nic %s. Attempt to "
                "contact IMDS failed with error %s. Assuming this is not the "
                "primary nic.",
                ifname,
                e,
            )

        if imds_md:
            # Only primary NIC will get a response from IMDS.
            LOG.info("%s is the primary nic", ifname)
            is_primary = True

            # Set the expected nic count based on the response received.
            expected_nic_count = len(imds_md["interface"])
            report_diagnostic_event(
                "Expected nic count: %d" % expected_nic_count,
                logger_func=LOG.info,
            )
        else:
            # If we are not the primary nic, then clean the dhcp context.
            self._teardown_ephemeral_networking()

        return is_primary, expected_nic_count

    @azure_ds_telemetry_reporter
    def _wait_for_hot_attached_nics(self, nl_sock):
        """Wait until all the expected nics for the vm are hot-attached.
        The expected nic count is obtained by requesting the network metadata
        from IMDS.
        """
        LOG.info("Waiting for nics to be hot-attached")
        try:
            # Wait for nics to be attached one at a time, until we know for
            # sure that all nics have been attached.
            nics_found = []
            primary_nic_found = False
            expected_nic_count = -1

            # Wait for netlink nic attach events. After the first nic is
            # attached, we are already in the customer vm deployment path and
            # so eerything from then on should happen fast and avoid
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
                    (
                        primary_nic_found,
                        expected_nic_count,
                    ) = self._check_if_nic_is_primary(ifname)

                # Exit criteria: check if we've discovered all nics
                if (
                    expected_nic_count != -1
                    and len(nics_found) >= expected_nic_count
                ):
                    LOG.info("Found all the nics for this VM.")
                    break

        except AssertionError as error:
            report_diagnostic_event(str(error), logger_func=LOG.error)

    @azure_ds_telemetry_reporter
    def _wait_for_all_nics_ready(self):
        """Wait for nic(s) to be hot-attached. There may be multiple nics
        depending on the customer request.
        But only primary nic would be able to communicate with wireserver
        and IMDS. So we detect and save the primary nic to be used later.
        """

        nl_sock = None
        try:
            nl_sock = netlink.create_bound_netlink_socket()

            report_ready_marker_present = bool(
                os.path.isfile(REPORTED_READY_MARKER_FILE)
            )

            # Report ready if the marker file is not already present.
            # The nic of the preprovisioned vm gets hot-detached as soon as
            # we report ready. So no need to save the dhcp context.
            if not os.path.isfile(REPORTED_READY_MARKER_FILE):
                self._report_ready_for_pps()

            has_nic_been_detached = bool(
                os.path.isfile(REPROVISION_NIC_DETACHED_MARKER_FILE)
            )

            if not has_nic_been_detached:
                LOG.info("NIC has not been detached yet.")
                self._teardown_ephemeral_networking()
                self._wait_for_nic_detach(nl_sock)

            # If we know that the preprovisioned nic has been detached, and we
            # still have a fallback nic, then it means the VM must have
            # rebooted as part of customer assignment, and all the nics have
            # already been attached by the Azure platform. So there is no need
            # to wait for nics to be hot-attached.
            if not self.fallback_interface:
                self._wait_for_hot_attached_nics(nl_sock)
            else:
                report_diagnostic_event(
                    "Skipping waiting for nic attach "
                    "because we already have a fallback "
                    "interface. Report Ready marker "
                    "present before detaching nics: %s"
                    % report_ready_marker_present,
                    logger_func=LOG.info,
                )
        except netlink.NetlinkCreateSocketError as e:
            report_diagnostic_event(str(e), logger_func=LOG.warning)
            raise
        finally:
            if nl_sock:
                nl_sock.close()

    @azure_ds_telemetry_reporter
    def _poll_imds(self):
        """Poll IMDS for the new provisioning data until we get a valid
        response. Then return the returned JSON object."""
        url = "{}?api-version={}".format(
            MetadataType.REPROVISION_DATA.value, IMDS_VER_MIN
        )
        headers = {"Metadata": "true"}
        nl_sock = None
        report_ready = bool(not os.path.isfile(REPORTED_READY_MARKER_FILE))
        self.imds_logging_threshold = 1
        self.imds_poll_counter = 1
        dhcp_attempts = 0
        reprovision_data = None

        def exc_cb(msg, exception):
            if isinstance(exception, UrlError):
                if exception.code in (404, 410):
                    if self.imds_poll_counter == self.imds_logging_threshold:
                        # Reducing the logging frequency as we are polling IMDS
                        self.imds_logging_threshold *= 2
                        LOG.debug(
                            "Backing off logging threshold for the same "
                            "exception to %d",
                            self.imds_logging_threshold,
                        )
                        report_diagnostic_event(
                            "poll IMDS with %s failed. "
                            "Exception: %s and code: %s"
                            % (msg, exception.cause, exception.code),
                            logger_func=LOG.debug,
                        )
                    self.imds_poll_counter += 1
                    return True
                else:
                    # If we get an exception while trying to call IMDS, we call
                    # DHCP and setup the ephemeral network to acquire a new IP.
                    report_diagnostic_event(
                        "poll IMDS with %s failed. Exception: %s and code: %s"
                        % (msg, exception.cause, exception.code),
                        logger_func=LOG.warning,
                    )
                    return False

            report_diagnostic_event(
                "poll IMDS failed with an unexpected exception: %s"
                % exception,
                logger_func=LOG.warning,
            )
            return False

        if report_ready:
            # Networking must be up for netlink to detect
            # media disconnect/connect.  It may be down to due
            # initial DHCP failure, if so check for it and retry,
            # ensuring we flag it as required.
            if not self._is_ephemeral_networking_up():
                self._setup_ephemeral_networking(timeout_minutes=20)

            try:
                if (
                    self._ephemeral_dhcp_ctx is None
                    or self._ephemeral_dhcp_ctx.iface is None
                ):
                    raise RuntimeError("Missing ephemeral context")
                iface = self._ephemeral_dhcp_ctx.iface

                nl_sock = netlink.create_bound_netlink_socket()
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
                        netlink.wait_for_media_disconnect_connect(
                            nl_sock, iface
                        )
                    except AssertionError as e:
                        report_diagnostic_event(
                            "Error while waiting for vnet switch: %s" % e,
                            logger_func=LOG.error,
                        )
            except netlink.NetlinkCreateSocketError as e:
                report_diagnostic_event(
                    "Failed to create bound netlink socket: %s" % e,
                    logger_func=LOG.warning,
                )
                raise sources.InvalidMetaDataException(
                    "Failed to report ready while in provisioning pool."
                ) from e
            except NoDHCPLeaseError as e:
                report_diagnostic_event(
                    "DHCP failed while in provisioning pool",
                    logger_func=LOG.warning,
                )
                raise sources.InvalidMetaDataException(
                    "Failed to report ready while in provisioning pool."
                ) from e
            finally:
                if nl_sock:
                    nl_sock.close()

            # Teardown old network configuration.
            self._teardown_ephemeral_networking()

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
                    reprovision_data = readurl(
                        url,
                        timeout=IMDS_TIMEOUT_IN_SECONDS,
                        headers=headers,
                        exception_cb=exc_cb,
                        infinite=True,
                        log_req_resp=False,
                    ).contents
                except UrlError:
                    self._teardown_ephemeral_networking()
                    continue

        report_diagnostic_event(
            "attempted dhcp %d times after reuse" % dhcp_attempts,
            logger_func=LOG.debug,
        )
        report_diagnostic_event(
            "polled imds %d times after reuse" % self.imds_poll_counter,
            logger_func=LOG.debug,
        )

        return reprovision_data

    @azure_ds_telemetry_reporter
    def _report_failure(self, description: Optional[str] = None) -> bool:
        """Tells the Azure fabric that provisioning has failed.

        @param description: A description of the error encountered.
        @return: The success status of sending the failure signal.
        """
        if self._is_ephemeral_networking_up():
            try:
                report_diagnostic_event(
                    "Using cached ephemeral dhcp context "
                    "to report failure to Azure",
                    logger_func=LOG.debug,
                )
                report_failure_to_fabric(
                    dhcp_opts=self._wireserver_endpoint,
                    description=description,
                )
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
                dhcp_opts=self._wireserver_endpoint, description=description
            )
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
        try:
            data = get_metadata_from_fabric(
                fallback_lease_file=None,
                dhcp_opts=self._wireserver_endpoint,
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
        if os.path.isfile(REPROVISION_MARKER_FILE):
            pps_type = PPSType.UNKNOWN
        elif (
            ovf_cfg.get("PreprovisionedVMType", None) == PPSType.SAVABLE.value
            or self._ppstype_from_imds(imds_md) == PPSType.SAVABLE.value
        ):
            pps_type = PPSType.SAVABLE
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

    def _write_reprovision_marker(self):
        """Write reprovision marker file in case system is rebooted."""
        LOG.info(
            "Creating a marker file to poll imds: %s", REPROVISION_MARKER_FILE
        )
        util.write_file(
            REPROVISION_MARKER_FILE,
            "{pid}: {time}\n".format(pid=os.getpid(), time=time()),
        )

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
        util.del_file(REPORTED_READY_MARKER_FILE)
        util.del_file(REPROVISION_MARKER_FILE)
        util.del_file(REPROVISION_NIC_DETACHED_MARKER_FILE)

    @azure_ds_telemetry_reporter
    def activate(self, cfg, is_new_instance):
        try:
            address_ephemeral_resize(
                is_new_instance=is_new_instance,
                preserve_ntfs=self.ds_cfg.get(DS_CFG_KEY_PRESERVE_NTFS, False),
            )
        finally:
            push_log_to_kvp(self.sys_cfg["def_log_file"])
        return

    @property
    def availability_zone(self):
        return (
            self.metadata.get("imds", {})
            .get("compute", {})
            .get("platformFaultDomain")
        )

    @property
    def network_config(self):
        """Generate a network config like net.generate_fallback_network() with
        the following exceptions.

        1. Probe the drivers of the net-devices present and inject them in
           the network configuration under params: driver: <driver> value
        2. Generate a fallback network config that does not include any of
           the blacklisted devices.
        """
        if not self._network_config or self._network_config == sources.UNSET:
            if self.ds_cfg.get("apply_network_config"):
                nc_src = self._metadata_imds
            else:
                nc_src = None
            self._network_config = parse_network_config(nc_src)
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
        ignored = set(["dataloss_warning_readme.txt"])
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
    devpath=RESOURCE_DISK_PATH, is_new_instance=False, preserve_ntfs=False
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
        sempath = "/var/lib/cloud/instance/sem/config_" + mod
        bmsg = 'Marker "%s" for module "%s"' % (sempath, mod)
        if os.path.exists(sempath):
            try:
                os.unlink(sempath)
                LOG.debug("%s removed.", bmsg)
            except Exception as e:
                # python3 throws FileNotFoundError, python2 throws OSError
                LOG.warning("%s: remove failed! (%s)", bmsg, e)
        else:
            LOG.debug("%s did not exist.", bmsg)
    return


@azure_ds_telemetry_reporter
def write_files(datadir, files, dirmode=None):
    def _redact_password(cnt, fname):
        """Azure provides the UserPassword in plain text. So we redact it"""
        try:
            root = ET.fromstring(cnt)
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
    for (name, content) in files.items():
        fname = os.path.join(datadir, name)
        if "ovf-env.xml" in name:
            content = _redact_password(content, fname)
        util.write_file(filename=fname, content=content, mode=0o600)


def find_child(node, filter_func):
    ret = []
    if not node.hasChildNodes():
        return ret
    for child in node.childNodes:
        if filter_func(child):
            ret.append(child)
    return ret


@azure_ds_telemetry_reporter
def load_azure_ovf_pubkeys(sshnode):
    # This parses a 'SSH' node formatted like below, and returns
    # an array of dicts.
    #  [{'fingerprint': '6BE7A7C3C8A8F4B123CCA5D0C2F1BE4CA7B63ED7',
    #    'path': '/where/to/go'}]
    #
    # <SSH><PublicKeys>
    #   <PublicKey><Fingerprint>ABC</FingerPrint><Path>/x/y/z</Path>
    #   ...
    # </PublicKeys></SSH>
    # Under some circumstances, there may be a <Value> element along with the
    # Fingerprint and Path. Pass those along if they appear.
    results = find_child(sshnode, lambda n: n.localName == "PublicKeys")
    if len(results) == 0:
        return []
    if len(results) > 1:
        raise BrokenAzureDataSource(
            "Multiple 'PublicKeys'(%s) in SSH node" % len(results)
        )

    pubkeys_node = results[0]
    pubkeys = find_child(pubkeys_node, lambda n: n.localName == "PublicKey")

    if len(pubkeys) == 0:
        return []

    found = []
    text_node = minidom.Document.TEXT_NODE

    for pk_node in pubkeys:
        if not pk_node.hasChildNodes():
            continue

        cur = {"fingerprint": "", "path": "", "value": ""}
        for child in pk_node.childNodes:
            if child.nodeType == text_node or not child.localName:
                continue

            name = child.localName.lower()

            if name not in cur.keys():
                continue

            if (
                len(child.childNodes) != 1
                or child.childNodes[0].nodeType != text_node
            ):
                continue

            cur[name] = child.childNodes[0].wholeText.strip()
        found.append(cur)

    return found


@azure_ds_telemetry_reporter
def read_azure_ovf(contents):
    try:
        dom = minidom.parseString(contents)
    except Exception as e:
        error_str = "Invalid ovf-env.xml: %s" % e
        report_diagnostic_event(error_str, logger_func=LOG.warning)
        raise BrokenAzureDataSource(error_str) from e

    results = find_child(
        dom.documentElement, lambda n: n.localName == "ProvisioningSection"
    )

    if len(results) == 0:
        raise NonAzureDataSource("No ProvisioningSection")
    if len(results) > 1:
        raise BrokenAzureDataSource(
            "found '%d' ProvisioningSection items" % len(results)
        )
    provSection = results[0]

    lpcs_nodes = find_child(
        provSection,
        lambda n: n.localName == "LinuxProvisioningConfigurationSet",
    )

    if len(lpcs_nodes) == 0:
        raise NonAzureDataSource("No LinuxProvisioningConfigurationSet")
    if len(lpcs_nodes) > 1:
        raise BrokenAzureDataSource(
            "found '%d' %ss"
            % (len(lpcs_nodes), "LinuxProvisioningConfigurationSet")
        )
    lpcs = lpcs_nodes[0]

    if not lpcs.hasChildNodes():
        raise BrokenAzureDataSource("no child nodes of configuration set")

    md_props = "seedfrom"
    md: Dict[str, Any] = {"azure_data": {}}
    cfg = {}
    ud = ""
    password = None
    username = None

    for child in lpcs.childNodes:
        if child.nodeType == dom.TEXT_NODE or not child.localName:
            continue

        name = child.localName.lower()

        simple = False
        value = ""
        if (
            len(child.childNodes) == 1
            and child.childNodes[0].nodeType == dom.TEXT_NODE
        ):
            simple = True
            value = child.childNodes[0].wholeText

        attrs = dict([(k, v) for k, v in child.attributes.items()])

        # we accept either UserData or CustomData.  If both are present
        # then behavior is undefined.
        if name == "userdata" or name == "customdata":
            if attrs.get("encoding") in (None, "base64"):
                ud = base64.b64decode("".join(value.split()))
            else:
                ud = value
        elif name == "username":
            username = value
        elif name == "userpassword":
            password = value
        elif name == "hostname":
            md["local-hostname"] = value
        elif name == "dscfg":
            if attrs.get("encoding") in (None, "base64"):
                dscfg = base64.b64decode("".join(value.split()))
            else:
                dscfg = value
            cfg["datasource"] = {DS_NAME: util.load_yaml(dscfg, default={})}
        elif name == "ssh":
            cfg["_pubkeys"] = load_azure_ovf_pubkeys(child)
        elif name == "disablesshpasswordauthentication":
            cfg["ssh_pwauth"] = util.is_false(value)
        elif simple:
            if name in md_props:
                md[name] = value
            else:
                md["azure_data"][name] = value

    defuser = {}
    if username:
        defuser["name"] = username
    if password:
        defuser["lock_passwd"] = False
        if DEF_PASSWD_REDACTION != password:
            defuser["passwd"] = cfg["password"] = encrypt_pass(password)

    if defuser:
        cfg["system_info"] = {"default_user": defuser}

    if "ssh_pwauth" not in cfg and password:
        cfg["ssh_pwauth"] = True

    preprovisioning_cfg = _get_preprovisioning_cfgs(dom)
    cfg = util.mergemanydict([cfg, preprovisioning_cfg])

    return (md, ud, cfg)


@azure_ds_telemetry_reporter
def _get_preprovisioning_cfgs(dom):
    """Read the preprovisioning related flags from ovf and populates a dict
    with the info.

    Two flags are in use today: PreprovisionedVm bool and
    PreprovisionedVMType enum. In the long term, the PreprovisionedVm bool
    will be deprecated in favor of PreprovisionedVMType string/enum.

    Only these combinations of values are possible today:
        - PreprovisionedVm=True and PreprovisionedVMType=Running
        - PreprovisionedVm=False and PreprovisionedVMType=Savable
        - PreprovisionedVm is missing and PreprovisionedVMType=Running/Savable
        - PreprovisionedVm=False and PreprovisionedVMType is missing

    More specifically, this will never happen:
        - PreprovisionedVm=True and PreprovisionedVMType=Savable
    """
    cfg = {"PreprovisionedVm": False, "PreprovisionedVMType": None}

    platform_settings_section = find_child(
        dom.documentElement, lambda n: n.localName == "PlatformSettingsSection"
    )
    if not platform_settings_section or len(platform_settings_section) == 0:
        LOG.debug("PlatformSettingsSection not found")
        return cfg
    platform_settings = find_child(
        platform_settings_section[0],
        lambda n: n.localName == "PlatformSettings",
    )
    if not platform_settings or len(platform_settings) == 0:
        LOG.debug("PlatformSettings not found")
        return cfg

    # Read the PreprovisionedVm bool flag. This should be deprecated when the
    # platform has removed PreprovisionedVm and only surfaces
    # PreprovisionedVMType.
    cfg["PreprovisionedVm"] = _get_preprovisionedvm_cfg_value(
        platform_settings
    )

    cfg["PreprovisionedVMType"] = _get_preprovisionedvmtype_cfg_value(
        platform_settings
    )
    return cfg


@azure_ds_telemetry_reporter
def _get_preprovisionedvm_cfg_value(platform_settings):
    preprovisionedVm = False

    # Read the PreprovisionedVm bool flag. This should be deprecated when the
    # platform has removed PreprovisionedVm and only surfaces
    # PreprovisionedVMType.
    preprovisionedVmVal = find_child(
        platform_settings[0], lambda n: n.localName == "PreprovisionedVm"
    )
    if not preprovisionedVmVal or len(preprovisionedVmVal) == 0:
        LOG.debug("PreprovisionedVm not found")
        return preprovisionedVm
    preprovisionedVm = util.translate_bool(
        preprovisionedVmVal[0].firstChild.nodeValue
    )

    report_diagnostic_event(
        "PreprovisionedVm: %s" % preprovisionedVm, logger_func=LOG.info
    )

    return preprovisionedVm


@azure_ds_telemetry_reporter
def _get_preprovisionedvmtype_cfg_value(platform_settings):
    preprovisionedVMType = None

    # Read the PreprovisionedVMType value from the ovf. It can be
    # 'Running' or 'Savable' or not exist. This enum value is intended to
    # replace PreprovisionedVm bool flag in the long term.
    # A Running VM is the same as preprovisioned VMs of today. This is
    # equivalent to having PreprovisionedVm=True.
    # A Savable VM is one whose nic is hot-detached immediately after it
    # reports ready the first time to free up the network resources.
    # Once assigned to customer, the customer-requested nics are
    # hot-attached to it and reprovision happens like today.
    preprovisionedVMTypeVal = find_child(
        platform_settings[0], lambda n: n.localName == "PreprovisionedVMType"
    )
    if (
        not preprovisionedVMTypeVal
        or len(preprovisionedVMTypeVal) == 0
        or preprovisionedVMTypeVal[0].firstChild is None
    ):
        LOG.debug("PreprovisionedVMType not found")
        return preprovisionedVMType

    preprovisionedVMType = preprovisionedVMTypeVal[0].firstChild.nodeValue

    report_diagnostic_event(
        "PreprovisionedVMType: %s" % preprovisionedVMType, logger_func=LOG.info
    )

    return preprovisionedVMType


def encrypt_pass(password, salt_id="$6$"):
    return crypt.crypt(password, salt_id + util.rand_str(strlen=16))


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
    seed = util.load_file(source, quiet=True, decode=False)

    # The seed generally contains non-Unicode characters. load_file puts
    # them into a str (in python 2) or bytes (in python 3). In python 2,
    # bad octets in a str cause util.json_dumps() to throw an exception. In
    # python 3, bytes is a non-serializable type, and the handler load_file
    # uses applies b64 encoding *again* to handle it. The simplest solution
    # is to just b64encode the data and then decode it to a serializable
    # string. Same number of bits of entropy, just with 25% more zeroes.
    # There's no need to undo this base64-encoding when the random seed is
    # actually used in cc_seed_random.py.
    return base64.b64encode(seed).decode()  # type: ignore


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
def parse_network_config(imds_metadata) -> dict:
    """Convert imds_metadata dictionary to network v2 configuration.
    Parses network configuration from imds metadata if present or generate
    fallback network config excluding mlx4_core devices.

    @param: imds_metadata: Dict of content read from IMDS network service.
    @return: Dictionary containing network version 2 standard configuration.
    """
    if imds_metadata != sources.UNSET and imds_metadata:
        try:
            return _generate_network_config_from_imds_metadata(imds_metadata)
        except Exception as e:
            LOG.error(
                "Failed generating network config "
                "from IMDS network metadata: %s",
                str(e),
            )
    try:
        return _generate_network_config_from_fallback_config()
    except Exception as e:
        LOG.error("Failed generating fallback network config: %s", str(e))
    return {}


@azure_ds_telemetry_reporter
def _generate_network_config_from_imds_metadata(imds_metadata) -> dict:
    """Convert imds_metadata dictionary to network v2 configuration.
    Parses network configuration from imds metadata.

    @param: imds_metadata: Dict of content read from IMDS network service.
    @return: Dictionary containing network version 2 standard configuration.
    """
    netconfig: Dict[str, Any] = {"version": 2, "ethernets": {}}
    network_metadata = imds_metadata["network"]
    for idx, intf in enumerate(network_metadata["interface"]):
        has_ip_address = False
        # First IPv4 and/or IPv6 address will be obtained via DHCP.
        # Any additional IPs of each type will be set as static
        # addresses.
        nicname = "eth{idx}".format(idx=idx)
        dhcp_override = {"route-metric": (idx + 1) * 100}
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
            # With netvsc, we can get two interfaces that
            # share the same MAC, so we need to make sure
            # our match condition also contains the driver
            driver = device_driver(nicname)
            if driver and driver == "hv_netvsc":
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
    """Generate fallback network config excluding blacklisted devices.

    @return: Dictionary containing network version 2 standard configuration.
    """
    cfg = net.generate_fallback_config(
        blacklist_drivers=BLACKLIST_DRIVERS, config_driver=True
    )
    if cfg is None:
        return {}
    return cfg


@azure_ds_telemetry_reporter
def get_metadata_from_imds(
    retries,
    md_type=MetadataType.ALL,
    api_version=IMDS_VER_MIN,
    exc_cb=retry_on_url_exc,
    infinite=False,
):
    """Query Azure's instance metadata service, returning a dictionary.

    For more info on IMDS:
        https://docs.microsoft.com/en-us/azure/virtual-machines/windows/instance-metadata-service

    @param retries: The number of retries of the IMDS_URL.
    @param md_type: Metadata type for IMDS request.
    @param api_version: IMDS api-version to use in the request.

    @return: A dict of instance metadata containing compute and network
        info.
    """
    kwargs = {
        "logfunc": LOG.debug,
        "msg": "Crawl of Azure Instance Metadata Service (IMDS)",
        "func": _get_metadata_from_imds,
        "args": (retries, exc_cb, md_type, api_version, infinite),
    }
    try:
        return util.log_time(**kwargs)
    except Exception as e:
        report_diagnostic_event(
            "exception while getting metadata: %s" % e,
            logger_func=LOG.warning,
        )
        raise


@azure_ds_telemetry_reporter
def _get_metadata_from_imds(
    retries,
    exc_cb,
    md_type=MetadataType.ALL,
    api_version=IMDS_VER_MIN,
    infinite=False,
):
    url = "{}?api-version={}".format(md_type.value, api_version)
    headers = {"Metadata": "true"}

    # support for extended metadata begins with 2021-03-01
    if api_version >= IMDS_EXTENDED_VER_MIN and md_type == MetadataType.ALL:
        url = url + "&extended=true"

    try:
        response = readurl(
            url,
            timeout=IMDS_TIMEOUT_IN_SECONDS,
            headers=headers,
            retries=retries,
            exception_cb=exc_cb,
            infinite=infinite,
        )
    except Exception as e:
        # pylint:disable=no-member
        if isinstance(e, UrlError) and e.code == 400:
            raise
        else:
            report_diagnostic_event(
                "Ignoring IMDS instance metadata. "
                "Get metadata from IMDS failed: %s" % e,
                logger_func=LOG.warning,
            )
            return {}
    try:
        from json.decoder import JSONDecodeError

        json_decode_error = JSONDecodeError
    except ImportError:
        json_decode_error = ValueError

    try:
        return util.load_json(response.contents)
    except json_decode_error as e:
        report_diagnostic_event(
            "Ignoring non-json IMDS instance metadata response: %s. "
            "Loading non-json IMDS response failed: %s"
            % (response.contents, e),
            logger_func=LOG.warning,
        )
    return {}


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


def _is_platform_viable(seed_dir):
    """Check platform environment to report if this datasource may run."""
    with events.ReportEventStack(
        name="check-platform-viability",
        description="found azure asset tag",
        parent=azure_ds_reporter,
    ) as evt:
        asset_tag = dmi.read_dmi_data("chassis-asset-tag")
        if asset_tag == AZURE_CHASSIS_ASSET_TAG:
            return True
        msg = "Non-Azure DMI asset tag '%s' discovered." % asset_tag
        evt.description = msg
        report_diagnostic_event(msg, logger_func=LOG.debug)
        if os.path.exists(os.path.join(seed_dir, "ovf-env.xml")):
            return True
        return False


class BrokenAzureDataSource(Exception):
    pass


class NonAzureDataSource(Exception):
    pass


# Legacy: Must be present in case we load an old pkl object
DataSourceAzureNet = DataSourceAzure

# Used to match classes to dependencies
datasources = [
    (DataSourceAzure, (sources.DEP_FILESYSTEM,)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)


# vi: ts=4 expandtab
