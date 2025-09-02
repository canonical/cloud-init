# Author: Jonas Keidel <jonas.keidel@hetzner.com>
# Author: Markus Schade <markus.schade@hetzner.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
#
"""Hetzner Cloud API Documentation
https://docs.hetzner.cloud/"""

import logging

import cloudinit.sources.helpers.hetzner as hc_helper
from cloudinit import dmi, net, sources, url_helper, util
from cloudinit.event import EventScope, EventType
from cloudinit.net.dhcp import NoDHCPLeaseError
from cloudinit.net.ephemeral import EphemeralIPNetwork

LOG = logging.getLogger(__name__)

BUILTIN_DS_CONFIG = {
    "metadata_path": "metadata",
    "metadata_private_networks_path": "metadata/private-networks",
    "userdata_path": "userdata",
}

MD_RETRIES = 60
MD_TIMEOUT = 2
MD_WAIT_RETRY = 2
MD_MAX_WAIT = 120
MD_SLEEP_TIME = 2

# Do not re-configure the network on non-Hetzner network interface
# changes. Currently, Hetzner private network addresses start with 0x86.
EXTRA_HOTPLUG_UDEV_RULES = """
SUBSYSTEM=="net", ATTR{address}=="86:*", GOTO="cloudinit_hook"
GOTO="cloudinit_end"
"""


def base_urls_v1():
    return (
        f"http://[fe80::a9fe:a9fe%25{net.find_fallback_nic()}]/hetzner/v1/",
        "http://169.254.169.254/hetzner/v1/",
    )


class DataSourceHetzner(sources.DataSource):
    dsname = "Hetzner"

    default_update_events = {
        EventScope.NETWORK: {
            EventType.BOOT_NEW_INSTANCE,
            EventType.BOOT,
            EventType.HOTPLUG,
        }
    }

    def __init__(self, sys_cfg, distro, paths):
        sources.DataSource.__init__(self, sys_cfg, distro, paths)
        self.distro = distro
        self.metadata = {}
        self.ds_cfg = util.mergemanydict(
            [
                util.get_cfg_by_path(sys_cfg, ["datasource", "Hetzner"], {}),
                BUILTIN_DS_CONFIG,
            ]
        )
        self.metadata_path = self.ds_cfg["metadata_path"]
        self.metadata_private_networks_path = self.ds_cfg[
            "metadata_private_networks_path"
        ]
        self.userdata_path = self.ds_cfg["userdata_path"]
        self.retries = self.ds_cfg.get("retries", MD_RETRIES)
        self.timeout = self.ds_cfg.get("timeout", MD_TIMEOUT)
        self.wait_retry = self.ds_cfg.get("wait_retry", MD_WAIT_RETRY)
        self.max_wait = self.ds_cfg.get("max_wait", MD_MAX_WAIT)
        self.sleep_time = self.ds_cfg.get("sleep_time", MD_SLEEP_TIME)
        self._network_config = sources.UNSET
        self.dsmode = sources.DSMODE_NETWORK
        self.metadata_full = None

        self.extra_hotplug_udev_rules = EXTRA_HOTPLUG_UDEV_RULES

    def _unpickle(self, ci_pkl_version: int) -> None:
        super()._unpickle(ci_pkl_version)
        self.extra_hotplug_udev_rules = EXTRA_HOTPLUG_UDEV_RULES
        self.wait_retry = self.ds_cfg.get("wait_retry", MD_WAIT_RETRY)
        self.max_wait = self.ds_cfg.get("max_wait", MD_MAX_WAIT)
        self.sleep_time = self.ds_cfg.get("sleep_time", MD_SLEEP_TIME)
        self.metadata_path = self.ds_cfg["metadata_path"]
        self.metadata_private_networks_path = self.ds_cfg[
            "metadata_private_networks_path"
        ]
        self.userdata_path = self.ds_cfg["userdata_path"]

    def _get_data(self):
        (on_hetzner, serial) = get_hcloud_data()

        if not on_hetzner:
            return False

        base_urls = base_urls_v1()
        try:
            with EphemeralIPNetwork(
                self.distro,
                interface=net.find_fallback_nic(),
                ipv4=True,
                ipv6=True,
                connectivity_urls_data=[
                    {
                        "url": url_helper.combine_url(
                            url, "metadata/instance-id"
                        )
                    }
                    for url in base_urls
                ],
            ):
                url, contents = hc_helper.get_metadata(
                    [
                        url_helper.combine_url(url, self.metadata_path)
                        for url in base_urls
                    ],
                    max_wait=self.max_wait,
                    timeout=self.timeout,
                    sleep_time=self.sleep_time,
                )
                LOG.debug("Using metadata source: '%s'", url)
                md = util.load_yaml(contents.decode(), allowed=(dict, list))
                url, contents = hc_helper.get_metadata(
                    [
                        url_helper.combine_url(
                            url, self.metadata_private_networks_path
                        )
                        for url in base_urls
                    ],
                    max_wait=self.max_wait,
                    timeout=self.timeout,
                    sleep_time=self.sleep_time,
                )
                LOG.debug("Using private_networks source: '%s'", url)
                md["private-networks"] = util.load_yaml(
                    contents.decode(), allowed=(dict, list)
                )
                url, ud = hc_helper.get_metadata(
                    [
                        url_helper.combine_url(url, self.userdata_path)
                        for url in base_urls
                    ],
                    max_wait=self.max_wait,
                    timeout=self.timeout,
                    sleep_time=self.sleep_time,
                )
                LOG.debug("Using userdata source: '%s'", url)
                if not ud:
                    LOG.debug("Got empty userdata")
        except NoDHCPLeaseError as e:
            LOG.error("Bailing, DHCP Exception: %s", e)
            raise

        # Hetzner cloud does not support binary user-data. So here, do a
        # base64 decode of the data if we can. The end result being that a
        # user can provide base64 encoded (possibly gzipped) data as user-data.
        #
        # The fallout is that in the event of b64 encoded user-data,
        # /var/lib/cloud-init/cloud-config.txt will not be identical to the
        # user-data provided.  It will be decoded.
        self.userdata_raw = util.maybe_b64decode(ud)
        self.metadata_full = md

        # hostname is name provided by user at launch.  The API enforces it is
        # a valid hostname, but it is not guaranteed to be resolvable in dns or
        # fully qualified.
        self.metadata["instance-id"] = md["instance-id"]
        self.metadata["local-hostname"] = md["hostname"]
        self.metadata["network-config"] = md.get("network-config", None)
        self.metadata["public-keys"] = md.get("public-keys", None)
        self.metadata["private-networks"] = md.get("private-networks", [])
        self.vendordata_raw = md.get("vendor_data", None)

        # instance-id and serial from SMBIOS should be identical
        if self.get_instance_id() != serial:
            raise RuntimeError(
                "SMBIOS serial does not match instance ID from metadata"
            )

        return True

    def check_instance_id(self, sys_cfg):
        return sources.instance_id_matches_system_uuid(
            self.get_instance_id(), "system-serial-number"
        )

    @property
    def network_config(self):
        """Configure the networking. This needs to be done each boot, since
        the IP information may have changed due to snapshot and/or
        migration.
        """

        if self._network_config is None:
            LOG.warning(
                "Found None as cached _network_config. Resetting to %s",
                sources.UNSET,
            )
            self._network_config = sources.UNSET

        if self._network_config != sources.UNSET:
            return self._network_config

        _net_config = self.metadata["network-config"]
        if not _net_config:
            raise RuntimeError("Unable to get meta-data from server....")

        _private_networks = self.metadata.get("private-networks", [])
        _private_networks_config = []
        for _private_network in _private_networks:
            _private_networks_config.extend(
                [
                    {
                        "type": "physical",
                        "mac_address": _private_network["mac_address"],
                        "name": hc_helper.get_interface_name_from_mac(
                            _private_network["mac_address"]
                        ),
                        "subnets": [
                            {
                                "ipv4": True,
                                "type": "dhcp",
                            }
                        ],
                    }
                ]
            )
        _net_config["config"].extend(_private_networks_config)
        self._network_config = _net_config
        return self._network_config


def get_hcloud_data():
    vendor_name = dmi.read_dmi_data("system-manufacturer")
    if vendor_name != "Hetzner":
        return False, None

    serial = dmi.read_dmi_data("system-serial-number")
    if serial:
        LOG.debug("Running on Hetzner Cloud: serial=%s", serial)
    else:
        raise RuntimeError("Hetzner Cloud detected, but no serial found")

    return True, serial


# Used to match classes to dependencies
datasources = [
    (DataSourceHetzner, (sources.DEP_FILESYSTEM,)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
