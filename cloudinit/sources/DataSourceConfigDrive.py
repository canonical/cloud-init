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
    "dsmode": DEFAULT_MODE,
}
CFG_DRIVE_DEV_ENV = 'CLOUD_INIT_CONFIG_DRIVE_DEVICE'


class DataSourceConfigDrive(sources.DataSource):
    def __init__(self, sys_cfg, distro, paths):
        sources.DataSource.__init__(self, sys_cfg, distro, paths)
        self.seed = None
        self.cfg = {}
        self.dsmode = 'local'
        self.seed_dir = os.path.join(paths.seed_dir, 'config_drive')
        self.version = None

    def __str__(self):
        mstr = "%s [%s,ver=%s]" % (util.obj_name(self), self.dsmode,
                                   self.version)
        mstr += "[seed=%s]" % (self.seed)
        return mstr

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
            fslist = util.find_devs_with("TYPE=vfat")
            fslist.extend(util.find_devs_with("TYPE=iso9660"))

            label_list = util.find_devs_with("LABEL=config-2")
            devlist = list(set(fslist) & set(label_list))

            dev = find_cfg_drive_device()
            if dev not in devlist:
                devlist.append(dev)

            devlist.sort(reverse=True)

            for dev in devlist:
                try:
                    results = util.mount_cb(dev, read_config_drive_dir)
                    found = dev
                    break
                except (NonConfigDriveDir, util.MountFailedError):
                    pass

        if not found:
            return False

        if 'dsconfig' in md:
            self.cfg = md['dscfg']

        md = util.mergedict(md, DEFAULT_METADATA)

        # Update interfaces and ifup only on the local datasource
        # this way the DataSourceConfigDriveNet doesn't do it also.
        if 'network-interfaces' in md and self.dsmode == "local":
            LOG.debug("Updating network interfaces from config drive (%s)",
                     md['dsmode'])
            self.distro.apply_network(md['network-interfaces'])

        self.seed = found
        self.metadata = results['metadata']
        self.userdata_raw = results.get('userdata')

        if md['dsmode'] == self.dsmode:
            return True

        LOG.debug("%s: not claiming datasource, dsmode=%s", self, md['dsmode'])
        return False

    def get_public_ssh_keys(self):
        if not 'public-keys' in self.metadata:
            return []
        return self.metadata['public-keys']

    # The data sources' config_obj is a cloud-config formated
    # object that came to it from ways other than cloud-config
    # because cloud-config content would be handled elsewhere
    def get_config_obj(self):
        return self.cfg


class DataSourceConfigDriveNet(DataSourceConfigDrive):
    def __init__(self, sys_cfg, distro, paths):
        DataSourceConfigDrive.__init__(self, sys_cfg, distro, paths)
        self.dsmode = 'net'


class NonConfigDriveDir(Exception):
    pass


class BrokenConfigDriveDir(Exception):
    pass


def find_cfg_drive_device():
    """Get the config drive device.  Return a string like '/dev/vdb'
       or None (if there is no non-root device attached). This does not
       check the contents, only reports that if there *were* a config_drive
       attached, it would be this device.
       Note: per config_drive documentation, this is
       "associated as the last available disk on the instance"
    """

    # This seems to be for debugging??
    if CFG_DRIVE_DEV_ENV in os.environ:
        return os.environ[CFG_DRIVE_DEV_ENV]

    # We are looking for a raw block device (sda, not sda1) with a vfat
    # filesystem on it....
    letters = "abcdefghijklmnopqrstuvwxyz"
    devs = util.find_devs_with("TYPE=vfat")

    # Filter out anything not ending in a letter (ignore partitions)
    devs = [f for f in devs if f[-1] in letters]

    # Sort them in reverse so "last" device is first
    devs.sort(reverse=True)

    if devs:
        return devs[0]

    return None


def read_config_drive_dir(source_dir):
    last_e = NonConfigDriveDir("Not found")
    for finder in (read_config_drive_dir_v2, read_config_drive_dir_v1):
        try:
            data = finder(source_dir)
            return data
        except NonConfigDriveDir as exc:
            last_e = exc
    raise last_e


def read_config_drive_dir_v2(source_dir, version="latest"):
    datafiles = (
        ('metadata',
         "openstack/%s/meta_data.json" % version, True, json.loads),
        ('userdata', "openstack/%s/user_data" % version, False, None),
        ('ec2-metadata', "ec2/latest/metadata.json", False, json.loads),
    )

    results = {}
    for (name, path, required, process) in datafiles:
        fpath = os.path.join(source_dir, path)
        data = None
        found = False
        if os.path.isfile(fpath):
            try:
                with open(fpath) as fp:
                    data = fp.read()
            except Exception as exc:
                raise BrokenConfigDriveDir("failed to read: %s" % fpath)
            found = True
        elif required:
            raise NonConfigDriveDir("missing mandatory %s" % fpath)

        if found and process:
            try:
                data = process(data)
            except Exception as exc:
                raise BrokenConfigDriveDir("failed to process: %s" % fpath)

        if found:
            results[name] = data

    def read_content_path(item):
        # do not use os.path.join here, as content_path starts with /
        cpath = os.path.sep.join((source_dir, "openstack",
                                  "./%s" % item['content_path']))
        with open(cpath) as fp:
            return(fp.read())

    files = {}
    try:
        for item in results['metadata'].get('files', {}):
            files[item['path']] = read_content_path(item)

        item = results['metadata'].get("network_config", None)
        if item:
            results['network_config'] = read_content_path(item)
    except Exception as exc:
        raise BrokenConfigDriveDir("failed to read file %s: %s" % (item, exc))

    results['files'] = files
    results['cfgdrive_ver'] = 2
    return results


def read_config_drive_dir_v1(source_dir):
    """
    read source_dir, and return a tuple with metadata dict, user-data,
    files and version (1).  If not a valid dir, raise a NonConfigDriveDir
    """

    # TODO(harlowja): fix this for other operating systems...
    # Ie: this is where https://fedorahosted.org/netcf/ or similar should
    # be hooked in... (or could be)
    found = {}
    for af in CFG_DRIVE_FILES_V1:
        fn = os.path.join(source_dir, af)
        if os.path.isfile(fn):
            found[af] = fn

    if len(found) == 0:
        raise NonConfigDriveDir("%s: %s" % (source_dir, "no files found"))

    md = {}
    ud = ""
    keydata = ""
    if "etc/network/interfaces" in found:
        fn = found["etc/network/interfaces"]
        md['network-interfaces'] = util.load_file(fn)

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

    # Key data override??
    keydata = meta_js.get('public-keys', keydata)
    if keydata:
        lines = keydata.splitlines()
        md['public-keys'] = [l for l in lines
            if len(l) and not l.startswith("#")]

    for copy in ('dsmode', 'instance-id', 'dscfg'):
        if copy in meta_js:
            md[copy] = meta_js[copy]

    if 'user-data' in meta_js:
        ud = meta_js['user-data']

    # metadata, user-data, 'files', 1
    return {'metadata': md, 'userdata': ud, 'files': [], 'cfgdrive_ver': 1}


# Used to match classes to dependencies
datasources = [
  (DataSourceConfigDrive, (sources.DEP_FILESYSTEM, )),
  (DataSourceConfigDriveNet, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
