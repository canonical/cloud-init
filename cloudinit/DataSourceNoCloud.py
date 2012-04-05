# vi: ts=4 expandtab
#
#    Copyright (C) 2009-2010 Canonical Ltd.
#    Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
#    Author: Scott Moser <scott.moser@canonical.com>
#    Author: Juerg Hafliger <juerg.haefliger@hp.com>
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
import errno
import subprocess


class DataSourceNoCloud(DataSource.DataSource):
    metadata = None
    userdata = None
    userdata_raw = None
    supported_seed_starts = ("/", "file://")
    dsmode = "local"
    seed = None
    cmdline_id = "ds=nocloud"
    seeddir = base_seeddir + '/nocloud'

    def __str__(self):
        mstr = "DataSourceNoCloud"
        mstr = mstr + " [seed=%s]" % self.seed
        return(mstr)

    def get_data(self):
        defaults = {
            "instance-id": "nocloud", "dsmode": self.dsmode
        }

        found = []
        md = {}
        ud = ""

        try:
            # parse the kernel command line, getting data passed in
            if parse_cmdline_data(self.cmdline_id, md):
                found.append("cmdline")
        except:
            util.logexc(log)
            return False

        # check to see if the seeddir has data.
        seedret = {}
        if util.read_optional_seed(seedret, base=self.seeddir + "/"):
            md = util.mergedict(md, seedret['meta-data'])
            ud = seedret['user-data']
            found.append(self.seeddir)
            log.debug("using seeded cache data in %s" % self.seeddir)

        # if the datasource config had a 'seedfrom' entry, then that takes
        # precedence over a 'seedfrom' that was found in a filesystem
        # but not over external medi
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
                (newmd, newud) = util.mount_callback_umount(dev,
                    util.read_seeded)
                md = util.mergedict(newmd, md)
                ud = newud

                # for seed from a device, the default mode is 'net'.
                # that is more likely to be what is desired.
                # If they want dsmode of local, then they must
                # specify that.
                if 'dsmode' not in md:
                    md['dsmode'] = "net"

                log.debug("using data from %s" % dev)
                found.append(dev)
                break
            except OSError, e:
                if e.errno != errno.ENOENT:
                    raise
            except util.mountFailedError:
                log.warn("Failed to mount %s when looking for seed" % dev)

        # there was no indication on kernel cmdline or data
        # in the seeddir suggesting this handler should be used.
        if len(found) == 0:
            return False

        seeded_interfaces = None

        # the special argument "seedfrom" indicates we should
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
                log.debug("seed from %s not supported by %s" %
                    (seedfrom, self.__class__))
                return False

            if 'network-interfaces' in md:
                seeded_interfaces = self.dsmode

            # this could throw errors, but the user told us to do it
            # so if errors are raised, let them raise
            (md_seed, ud) = util.read_seeded(seedfrom, timeout=None)
            log.debug("using seeded cache data from %s" % seedfrom)

            # values in the command line override those from the seed
            md = util.mergedict(md, md_seed)
            found.append(seedfrom)

        md = util.mergedict(md, defaults)

        # update the network-interfaces if metadata had 'network-interfaces'
        # entry and this is the local datasource, or 'seedfrom' was used
        # and the source of the seed was self.dsmode
        # ('local' for NoCloud, 'net' for NoCloudNet')
        if ('network-interfaces' in md and
            (self.dsmode in ("local", seeded_interfaces))):
            log.info("updating network interfaces from nocloud")

            util.write_file("/etc/network/interfaces",
                md['network-interfaces'])
            try:
                (out, err) = util.subp(['ifup', '--all'])
                if len(out) or len(err):
                    log.warn("ifup --all had stderr: %s" % err)

            except subprocess.CalledProcessError as exc:
                log.warn("ifup --all failed: %s" % (exc.output[1]))

        self.seed = ",".join(found)
        self.metadata = md
        self.userdata_raw = ud

        if md['dsmode'] == self.dsmode:
            return True

        log.debug("%s: not claiming datasource, dsmode=%s" %
            (self, md['dsmode']))
        return False


# returns true or false indicating if cmdline indicated
# that this module should be used
# example cmdline:
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

    return(True)


class DataSourceNoCloudNet(DataSourceNoCloud):
    cmdline_id = "ds=nocloud-net"
    supported_seed_starts = ("http://", "https://", "ftp://")
    seeddir = base_seeddir + '/nocloud-net'
    dsmode = "net"


datasources = (
  (DataSourceNoCloud, (DataSource.DEP_FILESYSTEM, )),
  (DataSourceNoCloudNet,
    (DataSource.DEP_FILESYSTEM, DataSource.DEP_NETWORK)),
)


# return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return(DataSource.list_from_depends(depends, datasources))
