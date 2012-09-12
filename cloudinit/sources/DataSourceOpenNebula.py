# vi: ts=4 expandtab
#
#    Copyright (C) 2012 Canonical Ltd.
#    Copyright (C) 2012 Yahoo! Inc.
#    Copyright (C) 2012 CERIT-Scientific Cloud
#
#    Author: Scott Moser <scott.moser@canonical.com>
#    Author: Joshua Harlow <harlowja@yahoo-inc.com>
#    Author: Vlastimil Holer <xholer@mail.muni.cz>
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
import re
import subprocess

from cloudinit import log as logging
from cloudinit import sources
from cloudinit import util

LOG = logging.getLogger(__name__)

DEFAULT_IID = "iid-dsopennebula"
CONTEXT_DISK_FILES = ["context.sh"]

class DataSourceOpenNebula(sources.DataSource):
    def __init__(self, sys_cfg, distro, paths):
        sources.DataSource.__init__(self, sys_cfg, distro, paths)
        self.dsmode = 'local'
        self.seed = None
        self.seed_dir = os.path.join(paths.seed_dir, 'opennebula')

    def __str__(self):
        mstr = "%s [seed=%s][dsmode=%s]" % (util.obj_name(self),
                                            self.seed, self.dsmode)
        return mstr

    def get_data(self):
        defaults = {
            "instance-id": DEFAULT_IID,
            "dsmode": self.dsmode,
        }

        found = None
        md = {}
        ud = ""

        results = {}
        if os.path.isdir(self.seed_dir):
            try:
                results=read_on_context_device_dir(self.seed_dir)
                found = self.seed_dir
            except NonContextDeviceDir:
                util.logexc(LOG, "Failed reading context device from %s",
                            self.seed_dir)
        if not found:
            devlist = find_candidate_devs()
            for dev in devlist:
                try:
                    results = util.mount_cb(dev, read_context_disk_dir)
                    found = dev
                    break
                except (NonConfigDriveDir, util.MountFailedError):
                    pass
                except BrokenConfigDriveDir:
                    util.logexc(LOG, "broken config drive: %s", dev)

        if not found:
            return False

        md = results['metadata']
        md = util.mergedict(md, defaults)

        # update interfaces and ifup only on the local datasource
        # this way the DataSourceConfigDriveNet doesn't do it also.
#       if 'network-interfaces' in md and self.dsmode == "local":
#            if md['dsmode'] == "pass":
#                log.info("updating network interfaces from configdrive")
#            else:
#                log.debug("updating network interfaces from configdrive")
#
#            util.write_file("/etc/network/interfaces",
#                md['network-interfaces'])
#            try:
#                (out, err) = util.subp(['ifup', '--all'])
#                if len(out) or len(err):
#                    log.warn("ifup --all had stderr: %s" % err)
#
#            except subprocess.CalledProcessError as exc:
#                log.warn("ifup --all failed: %s" % (exc.output[1]))
#

        if md['dsmode'] == self.dsmode:
            self.seed = found
            self.metadata = md
            self.userdata_raw = ud
            return True

        LOG.debug("%s: not claiming datasource, dsmode=%s", self, md['dsmode'])
        return False


class DataSourceOpenNebulaNet(DataSourceOpenNebula):
    dsmode = "net"


class NonContextDeviceDir(Exception):
    pass


def find_candidate_devs():
    """
    Return a list of devices that may contain the context disk.
    """
    by_fstype = util.find_devs_with("TYPE=iso9660")
    by_label = util.find_devs_with("LABEL=CDROM")

    by_fstype.sort()
    by_label.sort()

    # combine list of items by putting by-label items first
    # followed by fstype items, but with dupes removed
    combined = (by_label + [d for d in by_fstype if d not in by_label])

    # We are looking for block device (sda, not sda1), ignore partitions
    combined = [d for d in combined if d[-1] not in "0123456789"]

    return combined


def read_context_disk_dir(source_dir):
    """
    read_context_disk_dir(source_dir):
    read source_dir and return a tuple with metadata dict and user-data
    string populated.  If not a valid dir, raise a NonContextDeviceDir
    """

    found = {}
    for af in CONTEXT_DISK_FILES:
        fn = os.path.join(source_dir, af)
        if os.path.isfile(fn):
            found[af] = fn

    if len(found) == 0:
        raise NonContextDeviceDir("%s: %s" % (source_dir, "no files found"))

    context_sh = {}
    results = {
        'userdata':None,
        'metadata':{},
    }

    if "context.sh" in found:
        # let bash process the contextualization script;
        # write out data in normalized output NAME=\$?'?VALUE'?
        # TODO: don't trust context.sh! parse manually !!!
        try:
            BASH_CMD='VARS=`set | sort -u `;' \
                '. %s/context.sh;' \
                'comm -23 <(set | sort -u) <(echo "$VARS") | egrep -v "^(VARS|PIPESTATUS|_)="'

            (out,err) = util.subp(['bash',
                '--noprofile',
                '--norc',
                '-c',
                BASH_CMD % (source_dir) ])

            for (key,value) in [ l.split('=',1) for l in out.rstrip().split("\n") ]:
                # with backslash escapes
                r=re.match("^\$'(.*)'$",value)
                if r:
                    context_sh[key.lower()]=r.group(1).\
                        replace('\\\\','\\').\
                        replace('\\t','\t').\
                        replace('\\n','\n').\
                        replace("\\'","'")
                else:
                    # multiword values
                    r=re.match("^'(.*)'$",value)
                    if r:
                        context_sh[key.lower()]=r.group(1)
                    else:
                        # simple values
                        context_sh[key.lower()]=value
        except subprocess.CalledProcessError as exc:
            LOG.warn("context script faled to read" % (exc.output[1]))
        results['metadata']=context_sh

    # process single or multiple SSH keys
    if "ssh_key" in context_sh:
        lines = context_sh.get('ssh_key').splitlines()
        results['metadata']['public-keys'] = [l for l in lines
            if len(l) and not l.startswith("#")]

    # custom hostname
    if 'hostname' in context_sh:
        results['metadata']['local-hostname'] = context_sh['hostname']

    # raw user data
    if "user_data" in context_sh:
        results['userdata'] = context_sh["user_data"]
    if "userdata" in context_sh:
        results['userdata'] = context_sh["userdata"]

    return results


# Used to match classes to dependencies
datasources = [
    (DataSourceOpenNebula, (sources.DEP_FILESYSTEM, )),
    (DataSourceOpenNebulaNet, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
