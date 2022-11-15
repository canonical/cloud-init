# This file is part of cloud-init. See LICENSE file for license information.
"""Datasource for Oracle (OCI/Oracle Cloud Infrastructure)

Notes:
 * This datasource does not support OCI Classic. OCI Classic provides an EC2
   lookalike metadata service.
 * The UUID provided in DMI data is not the same as the meta-data provided
   instance-id, but has an equivalent lifespan.
 * We do need to support upgrade from an instance that cloud-init
   identified as OpenStack.
 * Bare metal instances use iSCSI root, virtual machine instances do not.
 * Both bare metal and virtual machine instances provide a chassis-asset-tag of
   OracleCloud.com.
"""

import base64
import ipaddress
from collections import namedtuple
from typing import Optional, Tuple

from cloudinit import dmi
from cloudinit import log as logging
from cloudinit import net, sources, util
from cloudinit.distros.networking import NetworkConfig
from cloudinit.net import (
    cmdline,
    ephemeral,
    get_interfaces_by_mac,
    is_netfail_master,
)
from cloudinit.url_helper import UrlError, readurl

LOG = logging.getLogger(__name__)

BUILTIN_DS_CONFIG = {
    # Don't use IMDS to configure secondary NICs by default
    "configure_secondary_nics": False,
}
CHASSIS_ASSET_TAG = "OracleCloud.com"
METADATA_ROOT = "http://169.254.169.254/opc/v{version}/"
METADATA_PATTERN = METADATA_ROOT + "{path}/"
# https://docs.cloud.oracle.com/iaas/Content/Network/Troubleshoot/connectionhang.htm#Overview,
# indicates that an MTU of 9000 is used within OCI
MTU = 9000
V2_HEADERS = {"Authorization": "Bearer Oracle"}

OpcMetadata = namedtuple("OpcMetadata", "version instance_data vnics_data")


class KlibcOracleNetworkConfigSource(cmdline.KlibcNetworkConfigSource):
    """Override super class to lower the applicability conditions.

    If any `/run/net-*.cfg` files exist, then it is applicable. Even if
    `/run/initramfs/open-iscsi.interface` does not exist.
    """

    def is_applicable(self) -> bool:
        """Override is_applicable"""
        return bool(self._files)


def _ensure_netfailover_safe(network_config: NetworkConfig) -> None:
    """
    Search network config physical interfaces to see if any of them are
    a netfailover master.  If found, we prevent matching by MAC as the other
    failover devices have the same MAC but need to be ignored.

    Note: we rely on cloudinit.net changes which prevent netfailover devices
    from being present in the provided network config.  For more details about
    netfailover devices, refer to cloudinit.net module.

    :param network_config
       A v1 or v2 network config dict with the primary NIC, and possibly
       secondary nic configured.  This dict will be mutated.

    """
    # ignore anything that's not an actual network-config
    if "version" not in network_config:
        return

    if network_config["version"] not in [1, 2]:
        LOG.debug(
            "Ignoring unknown network config version: %s",
            network_config["version"],
        )
        return

    mac_to_name = get_interfaces_by_mac()
    if network_config["version"] == 1:
        for cfg in [c for c in network_config["config"] if "type" in c]:
            if cfg["type"] == "physical":
                if "mac_address" in cfg:
                    mac = cfg["mac_address"]
                    cur_name = mac_to_name.get(mac)
                    if not cur_name:
                        continue
                    elif is_netfail_master(cur_name):
                        del cfg["mac_address"]

    elif network_config["version"] == 2:
        for _, cfg in network_config.get("ethernets", {}).items():
            if "match" in cfg:
                macaddr = cfg.get("match", {}).get("macaddress")
                if macaddr:
                    cur_name = mac_to_name.get(macaddr)
                    if not cur_name:
                        continue
                    elif is_netfail_master(cur_name):
                        del cfg["match"]["macaddress"]
                        del cfg["set-name"]
                        cfg["match"]["name"] = cur_name


class DataSourceOracle(sources.DataSource):

    dsname = "Oracle"
    system_uuid = None
    vendordata_pure = None
    network_config_sources: Tuple[sources.NetworkConfigSource, ...] = (
        sources.NetworkConfigSource.CMD_LINE,
        sources.NetworkConfigSource.DS,
        sources.NetworkConfigSource.INITRAMFS,
        sources.NetworkConfigSource.SYSTEM_CFG,
    )

    _network_config: dict = {"config": [], "version": 1}

    def __init__(self, sys_cfg, *args, **kwargs):
        super(DataSourceOracle, self).__init__(sys_cfg, *args, **kwargs)
        self._vnics_data = None

        self.ds_cfg = util.mergemanydict(
            [
                util.get_cfg_by_path(sys_cfg, ["datasource", self.dsname], {}),
                BUILTIN_DS_CONFIG,
            ]
        )
        self._network_config_source = KlibcOracleNetworkConfigSource()

    def _has_network_config(self) -> bool:
        return bool(self._network_config.get("config", []))

    def _is_platform_viable(self) -> bool:
        """Check platform environment to report if this datasource may run."""
        return _is_platform_viable()

    def _get_data(self):
        if not self._is_platform_viable():
            return False

        self.system_uuid = _read_system_uuid()

        network_context = ephemeral.EphemeralDHCPv4(
            iface=net.find_fallback_nic(),
            connectivity_url_data={
                "url": METADATA_PATTERN.format(version=2, path="instance"),
                "headers": V2_HEADERS,
            },
            tmp_dir=self.distro.get_tmp_exec_path(),
        )
        fetch_primary_nic = not self._is_iscsi_root()
        fetch_secondary_nics = self.ds_cfg.get(
            "configure_secondary_nics",
            BUILTIN_DS_CONFIG["configure_secondary_nics"],
        )
        with network_context:
            fetched_metadata = read_opc_metadata(
                fetch_vnics_data=fetch_primary_nic or fetch_secondary_nics
            )

        data = self._crawled_metadata = fetched_metadata.instance_data
        self.metadata_address = METADATA_ROOT.format(
            version=fetched_metadata.version
        )
        self._vnics_data = fetched_metadata.vnics_data

        self.metadata = {
            "availability-zone": data["ociAdName"],
            "instance-id": data["id"],
            "launch-index": 0,
            "local-hostname": data["hostname"],
            "name": data["displayName"],
        }

        if "metadata" in data:
            user_data = data["metadata"].get("user_data")
            if user_data:
                self.userdata_raw = base64.b64decode(user_data)
            self.metadata["public_keys"] = data["metadata"].get(
                "ssh_authorized_keys"
            )

        return True

    def check_instance_id(self, sys_cfg) -> bool:
        """quickly check (local only) if self.instance_id is still valid

        On Oracle, the dmi-provided system uuid differs from the instance-id
        but has the same life-span."""
        return sources.instance_id_matches_system_uuid(self.system_uuid)

    def get_public_ssh_keys(self):
        return sources.normalize_pubkey_data(self.metadata.get("public_keys"))

    def _is_iscsi_root(self) -> bool:
        """Return whether we are on a iscsi machine."""
        return self._network_config_source.is_applicable()

    def _get_iscsi_config(self) -> dict:
        return self._network_config_source.render_config()

    @property
    def network_config(self):
        """Network config is read from initramfs provided files

        Priority for primary network_config selection:
        - iscsi
        - imds

        If none is present, then we fall back to fallback configuration.
        """
        if self._has_network_config():
            return self._network_config

        set_primary = False
        # this is v1
        if self._is_iscsi_root():
            self._network_config = self._get_iscsi_config()
        if not self._has_network_config():
            LOG.warning(
                "Could not obtain network configuration from initramfs. "
                "Falling back to IMDS."
            )
            set_primary = True

        set_secondary = self.ds_cfg.get(
            "configure_secondary_nics",
            BUILTIN_DS_CONFIG["configure_secondary_nics"],
        )
        if set_primary or set_secondary:
            try:
                # Mutate self._network_config to include primary and/or
                # secondary VNICs
                self._add_network_config_from_opc_imds(set_primary)
            except Exception:
                util.logexc(
                    LOG,
                    "Failed to parse IMDS network configuration!",
                )

        # we need to verify that the nic selected is not a netfail over
        # device and, if it is a netfail master, then we need to avoid
        # emitting any match by mac
        _ensure_netfailover_safe(self._network_config)

        return self._network_config

    def _add_network_config_from_opc_imds(self, set_primary: bool = False):
        """Generate primary and/or secondary NIC config from IMDS and merge it.

        It will mutate the network config to include the secondary VNICs.

        :param set_primary: If True set primary interface.
        :raises:
            Exceptions are not handled within this function.  Likely
            exceptions are KeyError/IndexError
            (if the IMDS returns valid JSON with unexpected contents).
        """
        if self._vnics_data is None:
            LOG.warning("NIC data is UNSET but should not be")
            return

        if not set_primary and ("nicIndex" in self._vnics_data[0]):
            # TODO: Once configure_secondary_nics defaults to True, lower the
            # level of this log message.  (Currently, if we're running this
            # code at all, someone has explicitly opted-in to secondary
            # VNIC configuration, so we should warn them that it didn't
            # happen.  Once it's default, this would be emitted on every Bare
            # Metal Machine launch, which means INFO or DEBUG would be more
            # appropriate.)
            LOG.warning(
                "VNIC metadata indicates this is a bare metal machine; "
                "skipping secondary VNIC configuration."
            )
            return

        interfaces_by_mac = get_interfaces_by_mac()

        vnics_data = self._vnics_data if set_primary else self._vnics_data[1:]

        for index, vnic_dict in enumerate(vnics_data):
            is_primary = set_primary and index == 0
            mac_address = vnic_dict["macAddr"].lower()
            if mac_address not in interfaces_by_mac:
                LOG.warning(
                    "Interface with MAC %s not found; skipping",
                    mac_address,
                )
                continue
            name = interfaces_by_mac[mac_address]
            network = ipaddress.ip_network(vnic_dict["subnetCidrBlock"])

            if self._network_config["version"] == 1:
                if is_primary:
                    subnet = {"type": "dhcp"}
                else:
                    subnet = {
                        "type": "static",
                        "address": (
                            f"{vnic_dict['privateIp']}/{network.prefixlen}"
                        ),
                    }
                interface_config = {
                    "name": name,
                    "type": "physical",
                    "mac_address": mac_address,
                    "mtu": MTU,
                    "subnets": [subnet],
                }
                self._network_config["config"].append(interface_config)
            elif self._network_config["version"] == 2:
                # Why does this elif exist???
                # Are there plans to switch to v2?
                interface_config = {
                    "mtu": MTU,
                    "match": {"macaddress": mac_address},
                    "dhcp6": False,
                    "dhcp4": is_primary,
                }
                if not is_primary:
                    interface_config["addresses"] = [
                        f"{vnic_dict['privateIp']}/{network.prefixlen}"
                    ]
                self._network_config["ethernets"][name] = interface_config


def _read_system_uuid() -> Optional[str]:
    sys_uuid = dmi.read_dmi_data("system-uuid")
    return None if sys_uuid is None else sys_uuid.lower()


def _is_platform_viable() -> bool:
    asset_tag = dmi.read_dmi_data("chassis-asset-tag")
    return asset_tag == CHASSIS_ASSET_TAG


def _fetch(metadata_version: int, path: str, retries: int = 2) -> dict:
    return readurl(
        url=METADATA_PATTERN.format(version=metadata_version, path=path),
        headers=V2_HEADERS if metadata_version > 1 else None,
        retries=retries,
    )._response.json()


def read_opc_metadata(*, fetch_vnics_data: bool = False) -> OpcMetadata:
    """Fetch metadata from the /opc/ routes.

    :return:
        A namedtuple containing:
          The metadata version as an integer
          The JSON-decoded value of the instance data endpoint on the IMDS
          The JSON-decoded value of the vnics data endpoint if
            `fetch_vnics_data` is True, else None

    """
    # Per Oracle, there are short windows (measured in milliseconds) throughout
    # an instance's lifetime where the IMDS is being updated and may 404 as a
    # result.  To work around these windows, we retry a couple of times.
    metadata_version = 2
    try:
        instance_data = _fetch(metadata_version, path="instance")
    except UrlError:
        metadata_version = 1
        instance_data = _fetch(metadata_version, path="instance")

    vnics_data = None
    if fetch_vnics_data:
        try:
            vnics_data = _fetch(metadata_version, path="vnics")
        except UrlError:
            util.logexc(LOG, "Failed to fetch IMDS network configuration!")
    return OpcMetadata(metadata_version, instance_data, vnics_data)


# Used to match classes to dependencies
datasources = [
    (DataSourceOracle, (sources.DEP_FILESYSTEM,)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)


if __name__ == "__main__":
    import argparse

    description = """
        Query Oracle Cloud metadata and emit a JSON object with two keys:
        `read_opc_metadata` and `_is_platform_viable`.  The values of each are
        the return values of the corresponding functions defined in
        DataSourceOracle.py."""
    parser = argparse.ArgumentParser(description=description)
    parser.parse_args()
    print(
        util.json_dumps(
            {
                "read_opc_metadata": read_opc_metadata(),
                "_is_platform_viable": _is_platform_viable(),
            }
        )
    )

# vi: ts=4 expandtab
