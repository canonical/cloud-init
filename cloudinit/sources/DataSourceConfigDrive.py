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
CFG_DRIVE_FILES = [
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

    def __str__(self):
        mstr = "%s [%s]" % (util.obj_name(self), self.dsmode)
        mstr += "[seed=%s]" % (self.seed)
        return mstr

    def get_data(self):
        found = None
        md = {}
        ud = ""

        if os.path.isdir(self.seed_dir):
            try:
                (md, ud) = read_config_drive_dir(self.seed_dir)
                found = self.seed_dir
            except NonConfigDriveDir:
                util.logexc(LOG, "Failed reading config drive from %s",
                            self.seed_dir)
        if not found:
            dev = find_cfg_drive_device()
            if dev:
                try:
                    (md, ud) = util.mount_cb(dev, read_config_drive_dir)
                    found = dev
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
            if md['dsmode'] == "pass":
                LOG.info("Updating network interfaces from configdrive")
            else:
                LOG.debug("Updating network interfaces from configdrive")
            self.distro.apply_network(md['network-interfaces'])

        self.seed = found
        self.metadata = md
        self.userdata_raw = ud

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


def find_cfg_drive_device():
    """ Get the config drive device.  Return a string like '/dev/vdb'
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
    """
    read_config_drive_dir(source_dir):
       read source_dir, and return a tuple with metadata dict and user-data
       string populated.  If not a valid dir, raise a NonConfigDriveDir
    """

    # TODO: fix this for other operating systems...
    # Ie: this is where https://fedorahosted.org/netcf/ or similar should
    # be hooked in... (or could be)
    found = {}
    for af in CFG_DRIVE_FILES:
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

    return (md, ud)


# Used to match classes to dependencies
datasources = [
  (DataSourceConfigDrive, (sources.DEP_FILESYSTEM, )),
  (DataSourceConfigDriveNet, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
