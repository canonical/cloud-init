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

import os

from cloudinit import log as logging
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
VALID_DSMODES = ("local", "net", "pass", "disabled")
FS_TYPES = ('vfat', 'iso9660')
LABEL_TYPES = ('config-2',)
POSSIBLE_MOUNTS = ('sr', 'cd')
OPTICAL_DEVICES = tuple(('/dev/%s%s' % (z, i) for z in POSSIBLE_MOUNTS
                  for i in range(0, 2)))


class DataSourceConfigDrive(openstack.SourceMixin, sources.DataSource):
    def __init__(self, sys_cfg, distro, paths):
        super(DataSourceConfigDrive, self).__init__(sys_cfg, distro, paths)
        self.source = None
        self.dsmode = 'local'
        self.seed_dir = os.path.join(paths.seed_dir, 'config_drive')
        self.version = None
        self.ec2_metadata = None
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
                    results = util.mount_cb(dev, read_config_drive, mtype=mtype,
                                            sync=sync)
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
        user_dsmode = results.get('dsmode', None)
        if user_dsmode not in VALID_DSMODES + (None,):
            LOG.warn("User specified invalid mode: %s", user_dsmode)
            user_dsmode = None

        dsmode = get_ds_mode(cfgdrv_ver=results['version'],
                             ds_cfg=self.ds_cfg.get('dsmode'),
                             user=user_dsmode)

        if dsmode == "disabled":
            # most likely user specified
            return False

        # TODO(smoser): fix this, its dirty.
        # we want to do some things (writing files and network config)
        # only on first boot, and even then, we want to do so in the
        # local datasource (so they happen earlier) even if the configured
        # dsmode is 'net' or 'pass'. To do this, we check the previous
        # instance-id
        prev_iid = get_previous_iid(self.paths)
        cur_iid = md['instance-id']
        if prev_iid != cur_iid and self.dsmode == "local":
            on_first_boot(results, distro=self.distro)

        # dsmode != self.dsmode here if:
        #  * dsmode = "pass",  pass means it should only copy files and then
        #    pass to another datasource
        #  * dsmode = "net" and self.dsmode = "local"
        #    so that user boothooks would be applied with network, the
        #    local datasource just gets out of the way, and lets the net claim
        if dsmode != self.dsmode:
            LOG.debug("%s: not claiming datasource, dsmode=%s", self, dsmode)
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

        return True


class DataSourceConfigDriveNet(DataSourceConfigDrive):
    def __init__(self, sys_cfg, distro, paths):
        DataSourceConfigDrive.__init__(self, sys_cfg, distro, paths)
        self.dsmode = 'net'


def get_ds_mode(cfgdrv_ver, ds_cfg=None, user=None):
    """Determine what mode should be used.
    valid values are 'pass', 'disabled', 'local', 'net'
    """
    # user passed data trumps everything
    if user is not None:
        return user

    if ds_cfg is not None:
        return ds_cfg

    # at config-drive version 1, the default behavior was pass.  That
    # meant to not use use it as primary data source, but expect a ec2 metadata
    # source. for version 2, we default to 'net', which means
    # the DataSourceConfigDriveNet, would be used.
    #
    # this could change in the future.  If there was definitive metadata
    # that indicated presense of an openstack metadata service, then
    # we could change to 'pass' by default also. The motivation for that
    # would be 'cloud-init query' as the web service could be more dynamic
    if cfgdrv_ver == 1:
        return "pass"
    return "net"


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
        LOG.debug("Updating network interfaces from config drive")
        distro.apply_network(net_conf)
    files = data.get('files', {})
    if files:
        LOG.debug("Writing %s injected files", len(files))
        for (filename, content) in files.iteritems():
            if not filename.startswith(os.sep):
                filename = os.sep + filename
            try:
                util.write_file(filename, content, mode=0660)
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


# Used to match classes to dependencies
datasources = [
    (DataSourceConfigDrive, (sources.DEP_FILESYSTEM, )),
    (DataSourceConfigDriveNet, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
