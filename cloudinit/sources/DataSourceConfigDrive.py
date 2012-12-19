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

import json
import os

from cloudinit import log as logging
from cloudinit import sources
from cloudinit import util

LOG = logging.getLogger(__name__)

# Various defaults/constants...
DEFAULT_IID = "iid-dsconfigdrive"
DEFAULT_MODE = 'pass'
CFG_DRIVE_FILES_V1 = [
    "etc/network/interfaces",
    "root/.ssh/authorized_keys",
    "meta.js",
]
DEFAULT_METADATA = {
    "instance-id": DEFAULT_IID,
}
VALID_DSMODES = ("local", "net", "pass", "disabled")


class DataSourceConfigDrive(sources.DataSource):
    def __init__(self, sys_cfg, distro, paths):
        sources.DataSource.__init__(self, sys_cfg, distro, paths)
        self.source = None
        self.dsmode = 'local'
        self.seed_dir = os.path.join(paths.seed_dir, 'config_drive')
        self.version = None
        self.ec2_metadata = None

    def __str__(self):
        mstr = "%s [%s,ver=%s]" % (util.obj_name(self), self.dsmode,
                                   self.version)
        mstr += "[source=%s]" % (self.source)
        return mstr

    def _ec2_name_to_device(self, name):
        if not self.ec2_metadata:
            return None
        bdm = self.ec2_metadata.get('block-device-mapping', {})
        for (ent_name, device) in bdm.items():
            if name == ent_name:
                return device
        return None

    def _os_name_to_device(self, name):
        device = None
        try:
            criteria = 'LABEL=%s' % (name)
            if name in ['swap']:
                criteria = 'TYPE=%s' % (name)
            dev_entries = util.find_devs_with(criteria)
            if dev_entries:
                device = dev_entries[0]
        except util.ProcessExecutionError:
            pass
        return device

    def _validate_device_name(self, device):
        if not device:
            return None
        if not device.startswith("/"):
            device = "/dev/%s" % device
        if os.path.exists(device):
            return device
        # Durn, try adjusting the mapping
        remapped = self._remap_device(os.path.basename(device))
        if remapped:
            LOG.debug("Remapped device name %s => %s", device, remapped)
            return remapped
        return None

    def device_name_to_device(self, name):
        # Translate a 'name' to a 'physical' device
        if not name:
            return None
        # Try the ec2 mapping first
        names = [name]
        if name == 'root':
            names.insert(0, 'ami')
        if name == 'ami':
            names.append('root')
        device = None
        LOG.debug("Using ec2 metadata lookup to find device %s", names)
        for n in names:
            device = self._ec2_name_to_device(n)
            device = self._validate_device_name(device)
            if device:
                break
        # Try the openstack way second
        if not device:
            LOG.debug("Using os lookup to find device %s", names)
            for n in names:
                device = self._os_name_to_device(n)
                device = self._validate_device_name(device)
                if device:
                    break
        # Ok give up...
        if not device:
            return None
        else:
            LOG.debug("Using cfg drive lookup mapped to device %s", device)
            return device

    def get_data(self):
        found = None
        md = {}

        results = {}
        if os.path.isdir(self.seed_dir):
            try:
                results = read_config_drive_dir(self.seed_dir)
                found = self.seed_dir
            except NonConfigDriveDir:
                util.logexc(LOG, "Failed reading config drive from %s",
                            self.seed_dir)
        if not found:
            devlist = find_candidate_devs()
            for dev in devlist:
                try:
                    results = util.mount_cb(dev, read_config_drive_dir)
                    found = dev
                    break
                except (NonConfigDriveDir, util.MountFailedError):
                    pass
                except BrokenConfigDriveDir:
                    util.logexc(LOG, "broken config drive: %s", dev)

        if not found:
            return False

        md = results['metadata']
        md = util.mergedict(md, DEFAULT_METADATA)

        # Perform some metadata 'fixups'
        #
        # OpenStack uses the 'hostname' key
        # while most of cloud-init uses the metadata
        # 'local-hostname' key instead so if it doesn't
        # exist we need to make sure its copied over.
        for (tgt, src) in [('local-hostname', 'hostname')]:
            if tgt not in md and src in md:
                md[tgt] = md[src]

        user_dsmode = results.get('dsmode', None)
        if user_dsmode not in VALID_DSMODES + (None,):
            LOG.warn("user specified invalid mode: %s" % user_dsmode)
            user_dsmode = None

        dsmode = get_ds_mode(cfgdrv_ver=results['cfgdrive_ver'],
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

        if ('network_config' in results and self.dsmode == "local" and
            prev_iid != cur_iid):
            LOG.debug("Updating network interfaces from config drive (%s)",
                      dsmode)
            self.distro.apply_network(results['network_config'])

        # file writing occurs in local mode (to be as early as possible)
        if self.dsmode == "local" and prev_iid != cur_iid and results['files']:
            LOG.debug("writing injected files")
            try:
                write_files(results['files'])
            except:
                util.logexc(LOG, "Failed writing files")

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
        self.version = results['cfgdrive_ver']

        return True

    def get_public_ssh_keys(self):
        name = "public_keys"
        if self.version == 1:
            name = "public-keys"
        return sources.normalize_pubkey_data(self.metadata.get(name))


class DataSourceConfigDriveNet(DataSourceConfigDrive):
    def __init__(self, sys_cfg, distro, paths):
        DataSourceConfigDrive.__init__(self, sys_cfg, distro, paths)
        self.dsmode = 'net'


class NonConfigDriveDir(Exception):
    pass


class BrokenConfigDriveDir(Exception):
    pass


def find_candidate_devs():
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

    by_fstype = (util.find_devs_with("TYPE=vfat") +
                 util.find_devs_with("TYPE=iso9660"))
    by_label = util.find_devs_with("LABEL=config-2")

    # give preference to "last available disk" (vdb over vda)
    # note, this is not a perfect rendition of that.
    by_fstype.sort(reverse=True)
    by_label.sort(reverse=True)

    # combine list of items by putting by-label items first
    # followed by fstype items, but with dupes removed
    combined = (by_label + [d for d in by_fstype if d not in by_label])

    # We are looking for block device (sda, not sda1), ignore partitions
    combined = [d for d in combined if d[-1] not in "0123456789"]

    return combined


def read_config_drive_dir(source_dir):
    last_e = NonConfigDriveDir("Not found")
    for finder in (read_config_drive_dir_v2, read_config_drive_dir_v1):
        try:
            data = finder(source_dir)
            return data
        except NonConfigDriveDir as exc:
            last_e = exc
    raise last_e


def read_config_drive_dir_v2(source_dir, version="2012-08-10"):

    if (not os.path.isdir(os.path.join(source_dir, "openstack", version)) and
        os.path.isdir(os.path.join(source_dir, "openstack", "latest"))):
        LOG.warn("version '%s' not available, attempting to use 'latest'" %
                 version)
        version = "latest"

    datafiles = (
        ('metadata',
         "openstack/%s/meta_data.json" % version, True, json.loads),
        ('userdata', "openstack/%s/user_data" % version, False, None),
        ('ec2-metadata', "ec2/latest/meta-data.json", False, json.loads),
    )

    results = {'userdata': None}
    for (name, path, required, process) in datafiles:
        fpath = os.path.join(source_dir, path)
        data = None
        found = False
        if os.path.isfile(fpath):
            try:
                data = util.load_file(fpath)
            except IOError:
                raise BrokenConfigDriveDir("Failed to read: %s" % fpath)
            found = True
        elif required:
            raise NonConfigDriveDir("Missing mandatory path: %s" % fpath)

        if found and process:
            try:
                data = process(data)
            except Exception as exc:
                raise BrokenConfigDriveDir(("Failed to process "
                                            "path: %s") % fpath)

        if found:
            results[name] = data

    # instance-id is 'uuid' for openstack. just copy it to instance-id.
    if 'instance-id' not in results['metadata']:
        try:
            results['metadata']['instance-id'] = results['metadata']['uuid']
        except KeyError:
            raise BrokenConfigDriveDir("No uuid entry in metadata")

    def read_content_path(item):
        # do not use os.path.join here, as content_path starts with /
        cpath = os.path.sep.join((source_dir, "openstack",
                                  "./%s" % item['content_path']))
        return util.load_file(cpath)

    files = {}
    try:
        for item in results['metadata'].get('files', {}):
            files[item['path']] = read_content_path(item)

        # the 'network_config' item in metadata is a content pointer
        # to the network config that should be applied.
        # in folsom, it is just a '/etc/network/interfaces' file.
        item = results['metadata'].get("network_config", None)
        if item:
            results['network_config'] = read_content_path(item)
    except Exception as exc:
        raise BrokenConfigDriveDir("Failed to read file %s: %s" % (item, exc))

    # to openstack, user can specify meta ('nova boot --meta=key=value') and
    # those will appear under metadata['meta'].
    # if they specify 'dsmode' they're indicating the mode that they intend
    # for this datasource to operate in.
    try:
        results['dsmode'] = results['metadata']['meta']['dsmode']
    except KeyError:
        pass

    results['files'] = files
    results['cfgdrive_ver'] = 2
    return results


def read_config_drive_dir_v1(source_dir):
    """
    read source_dir, and return a tuple with metadata dict, user-data,
    files and version (1).  If not a valid dir, raise a NonConfigDriveDir
    """

    found = {}
    for af in CFG_DRIVE_FILES_V1:
        fn = os.path.join(source_dir, af)
        if os.path.isfile(fn):
            found[af] = fn

    if len(found) == 0:
        raise NonConfigDriveDir("%s: %s" % (source_dir, "no files found"))

    md = {}
    keydata = ""
    if "etc/network/interfaces" in found:
        fn = found["etc/network/interfaces"]
        md['network_config'] = util.load_file(fn)

    if "root/.ssh/authorized_keys" in found:
        fn = found["root/.ssh/authorized_keys"]
        keydata = util.load_file(fn)

    meta_js = {}
    if "meta.js" in found:
        fn = found['meta.js']
        content = util.load_file(fn)
        try:
            # Just check if its really json...
            meta_js = json.loads(content)
            if not isinstance(meta_js, (dict)):
                raise TypeError("Dict expected for meta.js root node")
        except (ValueError, TypeError) as e:
            raise NonConfigDriveDir("%s: %s, %s" %
                (source_dir, "invalid json in meta.js", e))
        md['meta_js'] = content

    # keydata in meta_js is preferred over "injected"
    keydata = meta_js.get('public-keys', keydata)
    if keydata:
        lines = keydata.splitlines()
        md['public-keys'] = [l for l in lines
            if len(l) and not l.startswith("#")]

    # config-drive-v1 has no way for openstack to provide the instance-id
    # so we copy that into metadata from the user input
    if 'instance-id' in meta_js:
        md['instance-id'] = meta_js['instance-id']

    results = {'cfgdrive_ver': 1, 'metadata': md}

    # allow the user to specify 'dsmode' in a meta tag
    if 'dsmode' in meta_js:
        results['dsmode'] = meta_js['dsmode']

    # config-drive-v1 has no way of specifying user-data, so the user has
    # to cheat and stuff it in a meta tag also.
    results['userdata'] = meta_js.get('user-data')

    # this implementation does not support files
    # (other than network/interfaces and authorized_keys)
    results['files'] = []

    return results


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


def get_previous_iid(paths):
    # interestingly, for this purpose the "previous" instance-id is the current
    # instance-id.  cloud-init hasn't moved them over yet as this datasource
    # hasn't declared itself found.
    fname = os.path.join(paths.get_cpath('data'), 'instance-id')
    try:
        return util.load_file(fname)
    except IOError:
        return None


def write_files(files):
    for (name, content) in files.iteritems():
        if name[0] != os.sep:
            name = os.sep + name
        util.write_file(name, content, mode=0660)


# Used to match classes to dependencies
datasources = [
  (DataSourceConfigDrive, (sources.DEP_FILESYSTEM, )),
  (DataSourceConfigDriveNet, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
