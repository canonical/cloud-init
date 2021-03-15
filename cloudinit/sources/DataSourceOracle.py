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
from collections import namedtuple
from contextlib import suppress as noop

from cloudinit import dmi
from cloudinit import log as logging
from cloudinit import net, sources, util
from cloudinit.net import (
    cmdline,
    dhcp,
    get_interfaces_by_mac,
    is_netfail_master,
)
from cloudinit.url_helper import UrlError, readurl

LOG = logging.getLogger(__name__)

BUILTIN_DS_CONFIG = {
    # Don't use IMDS to configure secondary NICs by default
    'configure_secondary_nics': False,
}
CHASSIS_ASSET_TAG = "OracleCloud.com"
METADATA_ROOT = "http://169.254.169.254/opc/v{version}/"
METADATA_PATTERN = METADATA_ROOT + "{path}/"
# https://docs.cloud.oracle.com/iaas/Content/Network/Troubleshoot/connectionhang.htm#Overview,
# indicates that an MTU of 9000 is used within OCI
MTU = 9000

OpcMetadata = namedtuple("OpcMetadata", "version instance_data vnics_data")


def _ensure_netfailover_safe(network_config):
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
    if 'version' not in network_config:
        return

    if network_config['version'] not in [1, 2]:
        LOG.debug('Ignoring unknown network config version: %s',
                  network_config['version'])
        return

    mac_to_name = get_interfaces_by_mac()
    if network_config['version'] == 1:
        for cfg in [c for c in network_config['config'] if 'type' in c]:
            if cfg['type'] == 'physical':
                if 'mac_address' in cfg:
                    mac = cfg['mac_address']
                    cur_name = mac_to_name.get(mac)
                    if not cur_name:
                        continue
                    elif is_netfail_master(cur_name):
                        del cfg['mac_address']

    elif network_config['version'] == 2:
        for _, cfg in network_config.get('ethernets', {}).items():
            if 'match' in cfg:
                macaddr = cfg.get('match', {}).get('macaddress')
                if macaddr:
                    cur_name = mac_to_name.get(macaddr)
                    if not cur_name:
                        continue
                    elif is_netfail_master(cur_name):
                        del cfg['match']['macaddress']
                        del cfg['set-name']
                        cfg['match']['name'] = cur_name


class DataSourceOracle(sources.DataSource):

    dsname = 'Oracle'
    system_uuid = None
    vendordata_pure = None
    network_config_sources = (
        sources.NetworkConfigSource.cmdline,
        sources.NetworkConfigSource.ds,
        sources.NetworkConfigSource.initramfs,
        sources.NetworkConfigSource.system_cfg,
    )

    _network_config = sources.UNSET

    def __init__(self, sys_cfg, *args, **kwargs):
        super(DataSourceOracle, self).__init__(sys_cfg, *args, **kwargs)
        self._vnics_data = None

        self.ds_cfg = util.mergemanydict([
            util.get_cfg_by_path(sys_cfg, ['datasource', self.dsname], {}),
            BUILTIN_DS_CONFIG])

    def _is_platform_viable(self):
        """Check platform environment to report if this datasource may run."""
        return _is_platform_viable()

    def _get_data(self):
        if not self._is_platform_viable():
            return False

        self.system_uuid = _read_system_uuid()

        # network may be configured if iscsi root.  If that is the case
        # then read_initramfs_config will return non-None.
        fetch_vnics_data = self.ds_cfg.get(
            'configure_secondary_nics',
            BUILTIN_DS_CONFIG["configure_secondary_nics"]
        )
        network_context = noop()
        if not _is_iscsi_root():
            network_context = dhcp.EphemeralDHCPv4(net.find_fallback_nic())
        with network_context:
            fetched_metadata = read_opc_metadata(
                fetch_vnics_data=fetch_vnics_data
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

    def check_instance_id(self, sys_cfg):
        """quickly check (local only) if self.instance_id is still valid

        On Oracle, the dmi-provided system uuid differs from the instance-id
        but has the same life-span."""
        return sources.instance_id_matches_system_uuid(self.system_uuid)

    def get_public_ssh_keys(self):
        return sources.normalize_pubkey_data(self.metadata.get('public_keys'))

    @property
    def network_config(self):
        """Network config is read from initramfs provided files

        If none is present, then we fall back to fallback configuration.
        """
        if self._network_config == sources.UNSET:
            # this is v1
            self._network_config = cmdline.read_initramfs_config()

            if not self._network_config:
                # this is now v2
                self._network_config = self.distro.generate_fallback_config()

            if self.ds_cfg.get(
                'configure_secondary_nics',
                BUILTIN_DS_CONFIG["configure_secondary_nics"]
            ):
                try:
                    # Mutate self._network_config to include secondary
                    # VNICs
                    self._add_network_config_from_opc_imds()
                except Exception:
                    util.logexc(
                        LOG,
                        "Failed to parse secondary network configuration!")

            # we need to verify that the nic selected is not a netfail over
            # device and, if it is a netfail master, then we need to avoid
            # emitting any match by mac
            _ensure_netfailover_safe(self._network_config)

        return self._network_config

    def _add_network_config_from_opc_imds(self):
        """Generate secondary NIC config from IMDS and merge it.

        The primary NIC configuration should not be modified based on the IMDS
        values, as it should continue to be configured for DHCP.  As such, this
        uses the instance's network config dict which is expected to have the
        primary NIC configuration already present.
        It will mutate the network config to include the secondary VNICs.

        :raises:
            Exceptions are not handled within this function.  Likely
            exceptions are KeyError/IndexError
            (if the IMDS returns valid JSON with unexpected contents).
        """
        if self._vnics_data is None:
            LOG.warning(
                "Secondary NIC data is UNSET but should not be")
            return

        if 'nicIndex' in self._vnics_data[0]:
            # TODO: Once configure_secondary_nics defaults to True, lower the
            # level of this log message.  (Currently, if we're running this
            # code at all, someone has explicitly opted-in to secondary
            # VNIC configuration, so we should warn them that it didn't
            # happen.  Once it's default, this would be emitted on every Bare
            # Metal Machine launch, which means INFO or DEBUG would be more
            # appropriate.)
            LOG.warning(
                'VNIC metadata indicates this is a bare metal machine; '
                'skipping secondary VNIC configuration.'
            )
            return

        interfaces_by_mac = get_interfaces_by_mac()

        for vnic_dict in self._vnics_data[1:]:
            # We skip the first entry in the response because the primary
            # interface is already configured by iSCSI boot; applying
            # configuration from the IMDS is not required.
            mac_address = vnic_dict['macAddr'].lower()
            if mac_address not in interfaces_by_mac:
                LOG.debug('Interface with MAC %s not found; skipping',
                          mac_address)
                continue
            name = interfaces_by_mac[mac_address]

            if self._network_config['version'] == 1:
                subnet = {
                    'type': 'static',
                    'address': vnic_dict['privateIp'],
                }
                self._network_config['config'].append({
                    'name': name,
                    'type': 'physical',
                    'mac_address': mac_address,
                    'mtu': MTU,
                    'subnets': [subnet],
                })
            elif self._network_config['version'] == 2:
                self._network_config['ethernets'][name] = {
                    'addresses': [vnic_dict['privateIp']],
                    'mtu': MTU, 'dhcp4': False, 'dhcp6': False,
                    'match': {'macaddress': mac_address}}


def _read_system_uuid():
    sys_uuid = dmi.read_dmi_data('system-uuid')
    return None if sys_uuid is None else sys_uuid.lower()


def _is_platform_viable():
    asset_tag = dmi.read_dmi_data('chassis-asset-tag')
    return asset_tag == CHASSIS_ASSET_TAG


def _is_iscsi_root():
    return bool(cmdline.read_initramfs_config())


def read_opc_metadata(*, fetch_vnics_data: bool = False):
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
    retries = 2

    def _fetch(metadata_version: int, path: str) -> dict:
        headers = {
            "Authorization": "Bearer Oracle"} if metadata_version > 1 else None
        return readurl(
            url=METADATA_PATTERN.format(version=metadata_version, path=path),
            headers=headers,
            retries=retries,
        )._response.json()

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
            util.logexc(LOG,
                        "Failed to fetch secondary network configuration!")
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
