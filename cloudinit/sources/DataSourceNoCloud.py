# vi: ts=4 expandtab
#
#    Copyright (C) 2009-2010 Canonical Ltd.
#    Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#    Copyright (C) 2012 Yahoo! Inc.
#
#    Author: Scott Moser <scott.moser@canonical.com>
#    Author: Juerg Hafliger <juerg.haefliger@hp.com>
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

import errno
import os

from cloudinit import log as logging
from cloudinit import sources
from cloudinit import util

LOG = logging.getLogger(__name__)


class DataSourceNoCloud(sources.DataSource):
    def __init__(self, sys_cfg, distro, paths):
        sources.DataSource.__init__(self, sys_cfg, distro, paths)
        self.dsmode = 'local'
        self.seed = None
        self.cmdline_id = "ds=nocloud"
        self.seed_dir = os.path.join(paths.seed_dir, 'nocloud')
        self.supported_seed_starts = ("/", "file://")

    def __str__(self):
        mstr = "%s [seed=%s][dsmode=%s]" % (util.obj_name(self),
                                            self.seed, self.dsmode)
        return mstr

    def get_data(self):
        defaults = {
            "instance-id": "nocloud",
            "dsmode": self.dsmode,
        }

        found = []
        md = {}
        ud = ""

        try:
            # Parse the kernel command line, getting data passed in
            if parse_cmdline_data(self.cmdline_id, md):
                found.append("cmdline")
        except:
            util.logexc(LOG, "Unable to parse command line data")
            return False

        # Check to see if the seed dir has data.
        seedret = {}
        if util.read_optional_seed(seedret, base=self.seed_dir + "/"):
            md = util.mergedict(md, seedret['meta-data'])
            ud = seedret['user-data']
            found.append(self.seed_dir)
            LOG.debug("Using seeded cache data from %s", self.seed_dir)

        # If the datasource config had a 'seedfrom' entry, then that takes
        # precedence over a 'seedfrom' that was found in a filesystem
        # but not over external media
        if 'seedfrom' in self.ds_cfg and self.ds_cfg['seedfrom']:
            found.append("ds_config")
            md["seedfrom"] = self.ds_cfg['seedfrom']

        fslist = util.find_devs_with("TYPE=vfat")
        fslist.extend(util.find_devs_with("TYPE=iso9660"))

        label_list = util.find_devs_with("LABEL=cidata")
        devlist = list(set(fslist) & set(label_list))
        devlist.sort(reverse=True)

        for dev in devlist:
            try:
                LOG.debug("Attempting to use data from %s", dev)

                (newmd, newud) = util.mount_cb(dev, util.read_seeded)
                md = util.mergedict(newmd, md)
                ud = newud

                # For seed from a device, the default mode is 'net'.
                # that is more likely to be what is desired.
                # If they want dsmode of local, then they must
                # specify that.
                if 'dsmode' not in md:
                    md['dsmode'] = "net"

                LOG.debug("Using data from %s", dev)
                found.append(dev)
                break
            except OSError as e:
                if e.errno != errno.ENOENT:
                    raise
            except util.MountFailedError:
                util.logexc(LOG, ("Failed to mount %s"
                                  " when looking for data"), dev)

        # There was no indication on kernel cmdline or data
        # in the seeddir suggesting this handler should be used.
        if len(found) == 0:
            return False

        seeded_interfaces = None

        # The special argument "seedfrom" indicates we should
        # attempt to seed the userdata / metadata from its value
        # its primarily value is in allowing the user to type less
        # on the command line, ie: ds=nocloud;s=http://bit.ly/abcdefg
        if "seedfrom" in md:
            seedfrom = md["seedfrom"]
            seedfound = False
            for proto in self.supported_seed_starts:
                if seedfrom.startswith(proto):
                    seedfound = proto
                    break
            if not seedfound:
                LOG.debug("Seed from %s not supported by %s", seedfrom, self)
                return False

            if 'network-interfaces' in md:
                seeded_interfaces = self.dsmode

            # This could throw errors, but the user told us to do it
            # so if errors are raised, let them raise
            (md_seed, ud) = util.read_seeded(seedfrom, timeout=None)
            LOG.debug("Using seeded cache data from %s", seedfrom)

            # Values in the command line override those from the seed
            md = util.mergedict(md, md_seed)
            found.append(seedfrom)

        # Now that we have exhausted any other places merge in the defaults
        md = util.mergedict(md, defaults)

        # Update the network-interfaces if metadata had 'network-interfaces'
        # entry and this is the local datasource, or 'seedfrom' was used
        # and the source of the seed was self.dsmode
        # ('local' for NoCloud, 'net' for NoCloudNet')
        if ('network-interfaces' in md and
            (self.dsmode in ("local", seeded_interfaces))):
            LOG.debug("Updating network interfaces from %s", self)
            self.distro.apply_network(md['network-interfaces'])

        if md['dsmode'] == self.dsmode:
            self.seed = ",".join(found)
            self.metadata = md
            self.userdata_raw = ud
            return True

        LOG.debug("%s: not claiming datasource, dsmode=%s", self, md['dsmode'])
        return False


# Returns true or false indicating if cmdline indicated
# that this module should be used
# Example cmdline:
#  root=LABEL=uec-rootfs ro ds=nocloud
def parse_cmdline_data(ds_id, fill, cmdline=None):
    if cmdline is None:
        cmdline = util.get_cmdline()
    cmdline = " %s " % cmdline

    if not (" %s " % ds_id in cmdline or " %s;" % ds_id in cmdline):
        return False

    argline = ""
    # cmdline can contain:
    # ds=nocloud[;key=val;key=val]
    for tok in cmdline.split():
        if tok.startswith(ds_id):
            argline = tok.split("=", 1)

    # argline array is now 'nocloud' followed optionally by
    # a ';' and then key=value pairs also terminated with ';'
    tmp = argline[1].split(";")
    if len(tmp) > 1:
        kvpairs = tmp[1:]
    else:
        kvpairs = ()

    # short2long mapping to save cmdline typing
    s2l = {"h": "local-hostname", "i": "instance-id", "s": "seedfrom"}
    for item in kvpairs:
        try:
            (k, v) = item.split("=", 1)
        except:
            k = item
            v = None
        if k in s2l:
            k = s2l[k]
        fill[k] = v

    return True


class DataSourceNoCloudNet(DataSourceNoCloud):
    def __init__(self, sys_cfg, distro, paths):
        DataSourceNoCloud.__init__(self, sys_cfg, distro, paths)
        self.cmdline_id = "ds=nocloud-net"
        self.supported_seed_starts = ("http://", "https://", "ftp://")
        self.seed_dir = os.path.join(paths.seed_dir, 'nocloud-net')
        self.dsmode = "net"


# Used to match classes to dependencies
datasources = [
  (DataSourceNoCloud, (sources.DEP_FILESYSTEM, )),
  (DataSourceNoCloudNet, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
