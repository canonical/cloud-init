# This file is part of cloud-init. See LICENSE file for license information.
"""Datasource for Oracle (OCI/Oracle Cloud Infrastructure)

OCI provides a OpenStack like metadata service which provides only
'2013-10-17' and 'latest' versions..

Notes:
 * This datasource does not support the OCI-Classic. OCI-Classic
   provides an EC2 lookalike metadata service.
 * The uuid provided in DMI data is not the same as the meta-data provided
   instance-id, but has an equivalent lifespan.
 * We do need to support upgrade from an instance that cloud-init
   identified as OpenStack.
 * Both bare-metal and vms use iscsi root
 * Both bare-metal and vms provide chassis-asset-tag of OracleCloud.com
"""

from cloudinit.url_helper import combine_url, readurl, UrlError
from cloudinit.net import dhcp, get_interfaces_by_mac, is_netfail_master
from cloudinit import net
from cloudinit import sources
from cloudinit import util
from cloudinit.net import cmdline
from cloudinit import log as logging

import json
import re

LOG = logging.getLogger(__name__)

BUILTIN_DS_CONFIG = {
    # Don't use IMDS to configure secondary NICs by default
    'configure_secondary_nics': False,
}
CHASSIS_ASSET_TAG = "OracleCloud.com"
METADATA_ENDPOINT = "http://169.254.169.254/openstack/"
VNIC_METADATA_URL = 'http://169.254.169.254/opc/v1/vnics/'
# https://docs.cloud.oracle.com/iaas/Content/Network/Troubleshoot/connectionhang.htm#Overview,
# indicates that an MTU of 9000 is used within OCI
MTU = 9000


def _add_network_config_from_opc_imds(network_config):
    """
    Fetch data from Oracle's IMDS, generate secondary NIC config, merge it.

    The primary NIC configuration should not be modified based on the IMDS
    values, as it should continue to be configured for DHCP.  As such, this
    takes an existing network_config dict which is expected to have the primary
    NIC configuration already present.  It will mutate the given dict to
    include the secondary VNICs.

    :param network_config:
        A v1 or v2 network config dict with the primary NIC already configured.
        This dict will be mutated.

    :raises:
        Exceptions are not handled within this function.  Likely exceptions are
        those raised by url_helper.readurl (if communicating with the IMDS
        fails), ValueError/JSONDecodeError (if the IMDS returns invalid JSON),
        and KeyError/IndexError (if the IMDS returns valid JSON with unexpected
        contents).
    """
    resp = readurl(VNIC_METADATA_URL)
    vnics = json.loads(str(resp))

    if 'nicIndex' in vnics[0]:
        # TODO: Once configure_secondary_nics defaults to True, lower the level
        # of this log message.  (Currently, if we're running this code at all,
        # someone has explicitly opted-in to secondary VNIC configuration, so
        # we should warn them that it didn't happen.  Once it's default, this
        # would be emitted on every Bare Metal Machine launch, which means INFO
        # or DEBUG would be more appropriate.)
        LOG.warning(
            'VNIC metadata indicates this is a bare metal machine; skipping'
            ' secondary VNIC configuration.'
        )
        return

    interfaces_by_mac = get_interfaces_by_mac()

    for vnic_dict in vnics[1:]:
        # We skip the first entry in the response because the primary interface
        # is already configured by iSCSI boot; applying configuration from the
        # IMDS is not required.
        mac_address = vnic_dict['macAddr'].lower()
        if mac_address not in interfaces_by_mac:
            LOG.debug('Interface with MAC %s not found; skipping', mac_address)
            continue
        name = interfaces_by_mac[mac_address]

        if network_config['version'] == 1:
            subnet = {
                'type': 'static',
                'address': vnic_dict['privateIp'],
            }
            network_config['config'].append({
                'name': name,
                'type': 'physical',
                'mac_address': mac_address,
                'mtu': MTU,
                'subnets': [subnet],
            })
        elif network_config['version'] == 2:
            network_config['ethernets'][name] = {
                'addresses': [vnic_dict['privateIp']],
                'mtu': MTU, 'dhcp4': False, 'dhcp6': False,
                'match': {'macaddress': mac_address}}


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

        self.ds_cfg = util.mergemanydict([
            util.get_cfg_by_path(sys_cfg, ['datasource', self.dsname], {}),
            BUILTIN_DS_CONFIG])

    def _is_platform_viable(self):
        """Check platform environment to report if this datasource may run."""
        return _is_platform_viable()

    def _get_data(self):
        if not self._is_platform_viable():
            return False

        # network may be configured if iscsi root.  If that is the case
        # then read_initramfs_config will return non-None.
        if _is_iscsi_root():
            data = self.crawl_metadata()
        else:
            with dhcp.EphemeralDHCPv4(net.find_fallback_nic()):
                data = self.crawl_metadata()

        self._crawled_metadata = data
        vdata = data['2013-10-17']

        self.userdata_raw = vdata.get('user_data')
        self.system_uuid = vdata['system_uuid']

        vd = vdata.get('vendor_data')
        if vd:
            self.vendordata_pure = vd
            try:
                self.vendordata_raw = sources.convert_vendordata(vd)
            except ValueError as e:
                LOG.warning("Invalid content in vendor-data: %s", e)
                self.vendordata_raw = None

        mdcopies = ('public_keys',)
        md = dict([(k, vdata['meta_data'].get(k))
                   for k in mdcopies if k in vdata['meta_data']])

        mdtrans = (
            # oracle meta_data.json name, cloudinit.datasource.metadata name
            ('availability_zone', 'availability-zone'),
            ('hostname', 'local-hostname'),
            ('launch_index', 'launch-index'),
            ('uuid', 'instance-id'),
        )
        for dsname, ciname in mdtrans:
            if dsname in vdata['meta_data']:
                md[ciname] = vdata['meta_data'][dsname]

        self.metadata = md
        return True

    def crawl_metadata(self):
        return read_metadata()

    def _get_subplatform(self):
        """Return the subplatform metadata source details."""
        return 'metadata (%s)' % METADATA_ENDPOINT

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

        One thing to note here is that this method is not currently
        considered at all if there is is kernel/initramfs provided
        data.  In that case, stages considers that the cmdline data
        overrides datasource provided data and does not consult here.

        We nonetheless return cmdline provided config if present
        and fallback to generate fallback."""
        if self._network_config == sources.UNSET:
            # this is v1
            self._network_config = cmdline.read_initramfs_config()

            if not self._network_config:
                # this is now v2
                self._network_config = self.distro.generate_fallback_config()

            if self.ds_cfg.get('configure_secondary_nics'):
                try:
                    # Mutate self._network_config to include secondary VNICs
                    _add_network_config_from_opc_imds(self._network_config)
                except Exception:
                    util.logexc(
                        LOG,
                        "Failed to fetch secondary network configuration!")

            # we need to verify that the nic selected is not a netfail over
            # device and, if it is a netfail master, then we need to avoid
            # emitting any match by mac
            _ensure_netfailover_safe(self._network_config)

        return self._network_config


def _read_system_uuid():
    sys_uuid = util.read_dmi_data('system-uuid')
    return None if sys_uuid is None else sys_uuid.lower()


def _is_platform_viable():
    asset_tag = util.read_dmi_data('chassis-asset-tag')
    return asset_tag == CHASSIS_ASSET_TAG


def _is_iscsi_root():
    return bool(cmdline.read_initramfs_config())


def _load_index(content):
    """Return a list entries parsed from content.

    OpenStack's metadata service returns a newline delimited list
    of items.  Oracle's implementation has html formatted list of links.
    The parser here just grabs targets from <a href="target">
    and throws away "../".

    Oracle has accepted that to be buggy and may fix in the future
    to instead return a '\n' delimited plain text list.  This function
    will continue to work if that change is made."""
    if not content.lower().startswith("<html>"):
        return content.splitlines()
    items = re.findall(
        r'href="(?P<target>[^"]*)"', content, re.MULTILINE | re.IGNORECASE)
    return [i for i in items if not i.startswith(".")]


def read_metadata(endpoint_base=METADATA_ENDPOINT, sys_uuid=None,
                  version='2013-10-17'):
    """Read metadata, return a dictionary.

    Each path listed in the index will be represented in the dictionary.
    If the path ends in .json, then the content will be decoded and
    populated into the dictionary.

    The system uuid (/sys/class/dmi/id/product_uuid) is also populated.
    Example: given paths = ('user_data', 'meta_data.json')
    This would return:
      {version: {'user_data': b'blob', 'meta_data': json.loads(blob.decode())
                 'system_uuid': '3b54f2e0-3ab2-458d-b770-af9926eee3b2'}}
    """
    endpoint = combine_url(endpoint_base, version) + "/"
    if sys_uuid is None:
        sys_uuid = _read_system_uuid()
    if not sys_uuid:
        raise sources.BrokenMetadata("Failed to read system uuid.")

    try:
        resp = readurl(endpoint)
        if not resp.ok():
            raise sources.BrokenMetadata(
                "Bad response from %s: %s" % (endpoint, resp.code))
    except UrlError as e:
        raise sources.BrokenMetadata(
            "Failed to read index at %s: %s" % (endpoint, e))

    entries = _load_index(resp.contents.decode('utf-8'))
    LOG.debug("index url %s contained: %s", endpoint, entries)

    # meta_data.json is required.
    mdj = 'meta_data.json'
    if mdj not in entries:
        raise sources.BrokenMetadata(
            "Required field '%s' missing in index at %s" % (mdj, endpoint))

    ret = {'system_uuid': sys_uuid}
    for path in entries:
        response = readurl(combine_url(endpoint, path))
        if path.endswith(".json"):
            ret[path.rpartition(".")[0]] = (
                json.loads(response.contents.decode('utf-8')))
        else:
            ret[path] = response.contents

    return {version: ret}


# Used to match classes to dependencies
datasources = [
    (DataSourceOracle, (sources.DEP_FILESYSTEM,)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)


if __name__ == "__main__":
    import argparse
    import os

    parser = argparse.ArgumentParser(description='Query Oracle Cloud Metadata')
    parser.add_argument("--endpoint", metavar="URL",
                        help="The url of the metadata service.",
                        default=METADATA_ENDPOINT)
    args = parser.parse_args()
    sys_uuid = "uuid-not-available-not-root" if os.geteuid() != 0 else None

    data = read_metadata(endpoint_base=args.endpoint, sys_uuid=sys_uuid)
    data['is_platform_viable'] = _is_platform_viable()
    print(util.json_dumps(data))

# vi: ts=4 expandtab
