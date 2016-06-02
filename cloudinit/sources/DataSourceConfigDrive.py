# vi: ts=4 expandtab
#
#    Copyright (C) 2012 Canonical Ltd.
#    Copyright (C) 2012 Yahoo! Inc.
#
#    Author: Scott Moser <scott.moser@canonical.com>
#    Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License version 3, as
#    published by the Free Software Foundation.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

import copy
import os

from cloudinit import log as logging
from cloudinit import net
from cloudinit import sources
from cloudinit import util

from cloudinit.sources.helpers import openstack

LOG = logging.getLogger(__name__)

# Various defaults/constants...
DEFAULT_IID = "iid-dsconfigdrive"
DEFAULT_MODE = 'pass'
DEFAULT_METADATA = {
    "instance-id": DEFAULT_IID,
}
FS_TYPES = ('vfat', 'iso9660')
LABEL_TYPES = ('config-2',)
POSSIBLE_MOUNTS = ('sr', 'cd')
OPTICAL_DEVICES = tuple(('/dev/%s%s' % (z, i) for z in POSSIBLE_MOUNTS
                        for i in range(0, 2)))


class DataSourceConfigDrive(openstack.SourceMixin, sources.DataSource):
    def __init__(self, sys_cfg, distro, paths):
        super(DataSourceConfigDrive, self).__init__(sys_cfg, distro, paths)
        self.source = None
        self.seed_dir = os.path.join(paths.seed_dir, 'config_drive')
        self.version = None
        self.ec2_metadata = None
        self._network_config = None
        self.network_json = None
        self.network_eni = None
        self.files = {}

    def __str__(self):
        root = sources.DataSource.__str__(self)
        mstr = "%s [%s,ver=%s]" % (root, self.dsmode, self.version)
        mstr += "[source=%s]" % (self.source)
        return mstr

    def get_data(self):
        found = None
        md = {}
        results = {}
        if os.path.isdir(self.seed_dir):
            try:
                results = read_config_drive(self.seed_dir)
                found = self.seed_dir
            except openstack.NonReadable:
                util.logexc(LOG, "Failed reading config drive from %s",
                            self.seed_dir)
        if not found:
            for dev in find_candidate_devs():
                try:
                    # Set mtype if freebsd and turn off sync
                    if dev.startswith("/dev/cd"):
                        mtype = "cd9660"
                        sync = False
                    else:
                        mtype = None
                        sync = True
                    results = util.mount_cb(dev, read_config_drive,
                                            mtype=mtype, sync=sync)
                    found = dev
                except openstack.NonReadable:
                    pass
                except util.MountFailedError:
                    pass
                except openstack.BrokenMetadata:
                    util.logexc(LOG, "Broken config drive: %s", dev)
                if found:
                    break
        if not found:
            return False

        md = results.get('metadata', {})
        md = util.mergemanydict([md, DEFAULT_METADATA])

        self.dsmode = self._determine_dsmode(
            [results.get('dsmode'), self.ds_cfg.get('dsmode'),
             sources.DSMODE_PASS if results['version'] == 1 else None])

        if self.dsmode == sources.DSMODE_DISABLED:
            return False

        # This is legacy and sneaky.  If dsmode is 'pass' then write
        # 'injected files' and apply legacy ENI network format.
        prev_iid = get_previous_iid(self.paths)
        cur_iid = md['instance-id']
        if prev_iid != cur_iid and self.dsmode == sources.DSMODE_PASS:
            on_first_boot(results, distro=self.distro)
            LOG.debug("%s: not claiming datasource, dsmode=%s", self,
                      self.dsmode)
            return False

        self.source = found
        self.metadata = md
        self.ec2_metadata = results.get('ec2-metadata')
        self.userdata_raw = results.get('userdata')
        self.version = results['version']
        self.files.update(results.get('files', {}))

        vd = results.get('vendordata')
        self.vendordata_pure = vd
        try:
            self.vendordata_raw = openstack.convert_vendordata_json(vd)
        except ValueError as e:
            LOG.warn("Invalid content in vendor-data: %s", e)
            self.vendordata_raw = None

        # network_config is an /etc/network/interfaces formated file and is
        # obsolete compared to networkdata (from network_data.json) but both
        # might be present.
        self.network_eni = results.get("network_config")
        self.network_json = results.get('networkdata')
        return True

    def check_instance_id(self, sys_cfg):
        # quickly (local check only) if self.instance_id is still valid
        return sources.instance_id_matches_system_uuid(self.get_instance_id())

    @property
    def network_config(self):
        if self._network_config is None:
            if self.network_json is not None:
                LOG.debug("network config provided via network_json")
                self._network_config = convert_network_data(self.network_json)
            elif self.network_eni is not None:
                self._network_config = net.convert_eni_data(self.network_eni)
                LOG.debug("network config provided via converted eni data")
            else:
                LOG.debug("no network configuration available")
        return self._network_config


def read_config_drive(source_dir):
    reader = openstack.ConfigDriveReader(source_dir)
    finders = [
        (reader.read_v2, [], {}),
        (reader.read_v1, [], {}),
    ]
    excps = []
    for (functor, args, kwargs) in finders:
        try:
            return functor(*args, **kwargs)
        except openstack.NonReadable as e:
            excps.append(e)
    raise excps[-1]


def get_previous_iid(paths):
    # interestingly, for this purpose the "previous" instance-id is the current
    # instance-id.  cloud-init hasn't moved them over yet as this datasource
    # hasn't declared itself found.
    fname = os.path.join(paths.get_cpath('data'), 'instance-id')
    try:
        return util.load_file(fname).rstrip("\n")
    except IOError:
        return None


def on_first_boot(data, distro=None):
    """Performs any first-boot actions using data read from a config-drive."""
    if not isinstance(data, dict):
        raise TypeError("Config-drive data expected to be a dict; not %s"
                        % (type(data)))
    net_conf = data.get("network_config", '')
    if net_conf and distro:
        LOG.warn("Updating network interfaces from config drive")
        distro.apply_network(net_conf)
    write_injected_files(data.get('files'))


def write_injected_files(files):
    if files:
        LOG.debug("Writing %s injected files", len(files))
        for (filename, content) in files.items():
            if not filename.startswith(os.sep):
                filename = os.sep + filename
            try:
                util.write_file(filename, content, mode=0o660)
            except IOError:
                util.logexc(LOG, "Failed writing file: %s", filename)


def find_candidate_devs(probe_optical=True):
    """Return a list of devices that may contain the config drive.

    The returned list is sorted by search order where the first item has
    should be searched first (highest priority)

    config drive v1:
       Per documentation, this is "associated as the last available disk on the
       instance", and should be VFAT.
       Currently, we do not restrict search list to "last available disk"

    config drive v2:
       Disk should be:
        * either vfat or iso9660 formated
        * labeled with 'config-2'
    """
    # query optical drive to get it in blkid cache for 2.6 kernels
    if probe_optical:
        for device in OPTICAL_DEVICES:
            try:
                util.find_devs_with(path=device)
            except util.ProcessExecutionError:
                pass

    by_fstype = []
    for fs_type in FS_TYPES:
        by_fstype.extend(util.find_devs_with("TYPE=%s" % (fs_type)))

    by_label = []
    for label in LABEL_TYPES:
        by_label.extend(util.find_devs_with("LABEL=%s" % (label)))

    # give preference to "last available disk" (vdb over vda)
    # note, this is not a perfect rendition of that.
    by_fstype.sort(reverse=True)
    by_label.sort(reverse=True)

    # combine list of items by putting by-label items first
    # followed by fstype items, but with dupes removed
    candidates = (by_label + [d for d in by_fstype if d not in by_label])

    # We are looking for a block device or partition with necessary label or
    # an unpartitioned block device (ex sda, not sda1)
    devices = [d for d in candidates
               if d in by_label or not util.is_partition(d)]
    return devices


# Convert OpenStack ConfigDrive NetworkData json to network_config yaml
def convert_network_data(network_json=None):
    """Return a dictionary of network_config by parsing provided
       OpenStack ConfigDrive NetworkData json format

    OpenStack network_data.json provides a 3 element dictionary
      - "links" (links are network devices, physical or virtual)
      - "networks" (networks are ip network configurations for one or more
                    links)
      -  services (non-ip services, like dns)

    networks and links are combined via network items referencing specific
    links via a 'link_id' which maps to a links 'id' field.

    To convert this format to network_config yaml, we first iterate over the
    links and then walk the network list to determine if any of the networks
    utilize the current link; if so we generate a subnet entry for the device

    We also need to map network_data.json fields to network_config fields. For
    example, the network_data links 'id' field is equivalent to network_config
    'name' field for devices.  We apply more of this mapping to the various
    link types that we encounter.

    There are additional fields that are populated in the network_data.json
    from OpenStack that are not relevant to network_config yaml, so we
    enumerate a dictionary of valid keys for network_yaml and apply filtering
    to drop these superflous keys from the network_config yaml.
    """
    if network_json is None:
        return None

    # dict of network_config key for filtering network_json
    valid_keys = {
        'physical': [
            'name',
            'type',
            'mac_address',
            'subnets',
            'params',
        ],
        'subnet': [
            'type',
            'address',
            'netmask',
            'broadcast',
            'metric',
            'gateway',
            'pointopoint',
            'mtu',
            'scope',
            'dns_nameservers',
            'dns_search',
            'routes',
        ],
    }

    links = network_json.get('links', [])
    networks = network_json.get('networks', [])
    services = network_json.get('services', [])

    config = []
    for link in links:
        subnets = []
        cfg = {k: v for k, v in link.items()
               if k in valid_keys['physical']}
        cfg.update({'name': link['id']})
        for network in [net for net in networks
                        if net['link'] == link['id']]:
            subnet = {k: v for k, v in network.items()
                      if k in valid_keys['subnet']}
            if 'dhcp' in network['type']:
                t = 'dhcp6' if network['type'].startswith('ipv6') else 'dhcp4'
                subnet.update({
                    'type': t,
                })
            else:
                subnet.update({
                    'type': 'static',
                    'address': network.get('ip_address'),
                })
            subnets.append(subnet)
        cfg.update({'subnets': subnets})
        if link['type'] in ['ethernet', 'vif', 'ovs', 'phy']:
            cfg.update({
                'type': 'physical',
                'mac_address': link['ethernet_mac_address']})
        elif link['type'] in ['bond']:
            params = {}
            for k, v in link.items():
                if k == 'bond_links':
                    continue
                elif k.startswith('bond'):
                    params.update({k: v})
            cfg.update({
                'bond_interfaces': copy.deepcopy(link['bond_links']),
                'params': params,
            })
        elif link['type'] in ['vlan']:
            cfg.update({
                'name': "%s.%s" % (link['vlan_link'],
                                   link['vlan_id']),
                'vlan_link': link['vlan_link'],
                'vlan_id': link['vlan_id'],
                'mac_address': link['vlan_mac_address'],
            })
        else:
            raise ValueError(
                'Unknown network_data link type: %s' % link['type'])

        config.append(cfg)

    for service in services:
        cfg = service
        cfg.update({'type': 'nameserver'})
        config.append(cfg)

    return {'version': 1, 'config': config}


# Legacy: Must be present in case we load an old pkl object
DataSourceConfigDriveNet = DataSourceConfigDrive

# Used to match classes to dependencies
datasources = [
    (DataSourceConfigDrive, (sources.DEP_FILESYSTEM, )),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
