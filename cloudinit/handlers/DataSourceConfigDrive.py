#    Copyright (C) 2012 Canonical Ltd.
#
#    Author: Scott Moser <scott.moser@canonical.com>
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

import cloudinit.DataSource as DataSource

from cloudinit import seeddir as base_seeddir
from cloudinit import log
import cloudinit.util as util
import os.path
import os
import json
import subprocess

DEFAULT_IID = "iid-dsconfigdrive"


class DataSourceConfigDrive(DataSource.DataSource):
    seed = None
    seeddir = base_seeddir + '/config_drive'
    cfg = {}
    userdata_raw = None
    metadata = None
    dsmode = "local"

    def __str__(self):
        mstr = "DataSourceConfigDrive[%s]" % self.dsmode
        mstr = mstr + " [seed=%s]" % self.seed
        return(mstr)

    def get_data(self):
        found = None
        md = {}
        ud = ""

        defaults = {"instance-id": DEFAULT_IID, "dsmode": "pass"}

        if os.path.isdir(self.seeddir):
            try:
                (md, ud) = read_config_drive_dir(self.seeddir)
                found = self.seeddir
            except nonConfigDriveDir:
                pass

        if not found:
            dev = cfg_drive_device()
            if dev:
                try:
                    (md, ud) = util.mount_callback_umount(dev,
                        read_config_drive_dir)
                    found = dev
                except (nonConfigDriveDir, util.mountFailedError):
                    pass

        if not found:
            return False

        if 'dsconfig' in md:
            self.cfg = md['dscfg']

        md = util.mergedict(md, defaults)

        # update interfaces and ifup only on the local datasource
        # this way the DataSourceConfigDriveNet doesn't do it also.
        if 'network-interfaces' in md and self.dsmode == "local":
            if md['dsmode'] == "pass":
                log.info("updating network interfaces from configdrive")
            else:
                log.debug("updating network interfaces from configdrive")

            util.write_file("/etc/network/interfaces",
                md['network-interfaces'])
            try:
                (out, err) = util.subp(['ifup', '--all'])
                if len(out) or len(err):
                    log.warn("ifup --all had stderr: %s" % err)

            except subprocess.CalledProcessError as exc:
                log.warn("ifup --all failed: %s" % (exc.output[1]))

        self.seed = found
        self.metadata = md
        self.userdata_raw = ud

        if md['dsmode'] == self.dsmode:
            return True

        log.debug("%s: not claiming datasource, dsmode=%s" %
            (self, md['dsmode']))
        return False

    def get_public_ssh_keys(self):
        if not 'public-keys' in self.metadata:
            return([])
        return(self.metadata['public-keys'])

    # the data sources' config_obj is a cloud-config formated
    # object that came to it from ways other than cloud-config
    # because cloud-config content would be handled elsewhere
    def get_config_obj(self):
        return(self.cfg)


class DataSourceConfigDriveNet(DataSourceConfigDrive):
    dsmode = "net"


class nonConfigDriveDir(Exception):
    pass


def cfg_drive_device():
    """ get the config drive device.  return a string like '/dev/vdb'
        or None (if there is no non-root device attached). This does not
        check the contents, only reports that if there *were* a config_drive
        attached, it would be this device.
        per config_drive documentation, this is
         "associated as the last available disk on the instance"
    """

    if 'CLOUD_INIT_CONFIG_DRIVE_DEVICE' in os.environ:
        return(os.environ['CLOUD_INIT_CONFIG_DRIVE_DEVICE'])

    # we are looking for a raw block device (sda, not sda1) with a vfat
    # filesystem on it.

    letters = "abcdefghijklmnopqrstuvwxyz"
    devs = util.find_devs_with("TYPE=vfat")

    # filter out anything not ending in a letter (ignore partitions)
    devs = [f for f in devs if f[-1] in letters]

    # sort them in reverse so "last" device is first
    devs.sort(reverse=True)

    if len(devs):
        return(devs[0])

    return(None)


def read_config_drive_dir(source_dir):
    """
    read_config_drive_dir(source_dir):
       read source_dir, and return a tuple with metadata dict and user-data
       string populated.  If not a valid dir, raise a nonConfigDriveDir
    """
    md = {}
    ud = ""

    flist = ("etc/network/interfaces", "root/.ssh/authorized_keys", "meta.js")
    found = [f for f in flist if os.path.isfile("%s/%s" % (source_dir, f))]
    keydata = ""

    if len(found) == 0:
        raise nonConfigDriveDir("%s: %s" % (source_dir, "no files found"))

    if "etc/network/interfaces" in found:
        with open("%s/%s" % (source_dir, "/etc/network/interfaces")) as fp:
            md['network-interfaces'] = fp.read()

    if "root/.ssh/authorized_keys" in found:
        with open("%s/%s" % (source_dir, "root/.ssh/authorized_keys")) as fp:
            keydata = fp.read()

    meta_js = {}

    if "meta.js" in found:
        content = ''
        with open("%s/%s" % (source_dir, "meta.js")) as fp:
            content = fp.read()
        md['meta_js'] = content
        try:
            meta_js = json.loads(content)
        except ValueError:
            raise nonConfigDriveDir("%s: %s" %
                (source_dir, "invalid json in meta.js"))

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

    return(md, ud)

datasources = (
  (DataSourceConfigDrive, (DataSource.DEP_FILESYSTEM, )),
  (DataSourceConfigDriveNet,
    (DataSource.DEP_FILESYSTEM, DataSource.DEP_NETWORK)),
)


# return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return(DataSource.list_from_depends(depends, datasources))

if __name__ == "__main__":
    def main():
        import sys
        import pprint
        print cfg_drive_device()
        (md, ud) = read_config_drive_dir(sys.argv[1])
        print "=== md ==="
        pprint.pprint(md)
        print "=== ud ==="
        print(ud)

    main()

# vi: ts=4 expandtab
