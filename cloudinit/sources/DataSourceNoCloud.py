# vi: ts=4 expandtab
#
#    Copyright (C) 2009-2010 Canonical Ltd.
#    Copyright (C) 2012, 2013 Hewlett-Packard Development Company, L.P.
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
        root = sources.DataSource.__str__(self)
        return "%s [seed=%s][dsmode=%s]" % (root, self.seed, self.dsmode)

    def get_data(self):
        defaults = {
            "instance-id": "nocloud",
            "dsmode": self.dsmode,
        }

        found = []
        mydata = {'meta-data': {}, 'user-data': "", 'vendor-data': ""}

        try:
            # Parse the kernel command line, getting data passed in
            md = {}
            if parse_cmdline_data(self.cmdline_id, md):
                found.append("cmdline")
            mydata['meta-data'].update(md)
        except:
            util.logexc(LOG, "Unable to parse command line data")
            return False

        # Check to see if the seed dir has data.
        pp2d_kwargs = {'required': ['user-data', 'meta-data'],
                       'optional': ['vendor-data']}

        try:
            seeded = util.pathprefix2dict(self.seed_dir, **pp2d_kwargs)
            found.append(self.seed_dir)
            LOG.debug("Using seeded data from %s", self.seed_dir)
        except ValueError as e:
            pass

        if self.seed_dir in found:
            mydata = _merge_new_seed(mydata, seeded)

        # If the datasource config had a 'seedfrom' entry, then that takes
        # precedence over a 'seedfrom' that was found in a filesystem
        # but not over external media
        if self.ds_cfg.get('seedfrom'):
            found.append("ds_config_seedfrom")
            mydata['meta-data']["seedfrom"] = self.ds_cfg['seedfrom']

        # fields appropriately named can also just come from the datasource
        # config (ie, 'user-data', 'meta-data', 'vendor-data' there)
        if 'user-data' in self.ds_cfg and 'meta-data' in self.ds_cfg:
            mydata = _merge_new_seed(mydata, self.ds_cfg)
            found.append("ds_config")

        def _pp2d_callback(mp, data):
            return util.pathprefix2dict(mp, **data)

        label = self.ds_cfg.get('fs_label', "cidata")
        if label is not None:
            # Query optical drive to get it in blkid cache for 2.6 kernels
            util.find_devs_with(path="/dev/sr0")
            util.find_devs_with(path="/dev/sr1")

            fslist = util.find_devs_with("TYPE=vfat")
            fslist.extend(util.find_devs_with("TYPE=iso9660"))

            label_list = util.find_devs_with("LABEL=%s" % label)
            devlist = list(set(fslist) & set(label_list))
            devlist.sort(reverse=True)

            for dev in devlist:
                try:
                    LOG.debug("Attempting to use data from %s", dev)

                    try:
                        seeded = util.mount_cb(dev, _pp2d_callback,
                                               pp2d_kwargs)
                    except ValueError as e:
                        if dev in label_list:
                            LOG.warn("device %s with label=%s not a"
                                     "valid seed.", dev, label)
                        continue

                    mydata = _merge_new_seed(mydata, seeded)

                    # For seed from a device, the default mode is 'net'.
                    # that is more likely to be what is desired.  If they want
                    # dsmode of local, then they must specify that.
                    if 'dsmode' not in mydata['meta-data']:
                        mydata['dsmode'] = "net"

                    LOG.debug("Using data from %s", dev)
                    found.append(dev)
                    break
                except OSError as e:
                    if e.errno != errno.ENOENT:
                        raise
                except util.MountFailedError:
                    util.logexc(LOG, "Failed to mount %s when looking for "
                                "data", dev)

        # There was no indication on kernel cmdline or data
        # in the seeddir suggesting this handler should be used.
        if len(found) == 0:
            return False

        seeded_interfaces = None

        # The special argument "seedfrom" indicates we should
        # attempt to seed the userdata / metadata from its value
        # its primarily value is in allowing the user to type less
        # on the command line, ie: ds=nocloud;s=http://bit.ly/abcdefg
        if "seedfrom" in mydata['meta-data']:
            seedfrom = mydata['meta-data']["seedfrom"]
            seedfound = False
            for proto in self.supported_seed_starts:
                if seedfrom.startswith(proto):
                    seedfound = proto
                    break
            if not seedfound:
                LOG.debug("Seed from %s not supported by %s", seedfrom, self)
                return False

            if 'network-interfaces' in mydata['meta-data']:
                seeded_interfaces = self.dsmode

            # This could throw errors, but the user told us to do it
            # so if errors are raised, let them raise
            (md_seed, ud) = util.read_seeded(seedfrom, timeout=None)
            LOG.debug("Using seeded cache data from %s", seedfrom)

            # Values in the command line override those from the seed
            mydata['meta-data'] = util.mergemanydict([mydata['meta-data'],
                                                      md_seed])
            mydata['user-data'] = ud
            found.append(seedfrom)

        # Now that we have exhausted any other places merge in the defaults
        mydata['meta-data'] = util.mergemanydict([mydata['meta-data'],
                                                  defaults])

        # Update the network-interfaces if metadata had 'network-interfaces'
        # entry and this is the local datasource, or 'seedfrom' was used
        # and the source of the seed was self.dsmode
        # ('local' for NoCloud, 'net' for NoCloudNet')
        if ('network-interfaces' in mydata['meta-data'] and
                (self.dsmode in ("local", seeded_interfaces))):
            LOG.debug("Updating network interfaces from %s", self)
            self.distro.apply_network(
                mydata['meta-data']['network-interfaces'])

        if mydata['meta-data']['dsmode'] == self.dsmode:
            self.seed = ",".join(found)
            self.metadata = mydata['meta-data']
            self.userdata_raw = mydata['user-data']
            self.vendordata = mydata['vendor-data']
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
        if item == "":
            continue
        try:
            (k, v) = item.split("=", 1)
        except:
            k = item
            v = None
        if k in s2l:
            k = s2l[k]
        fill[k] = v

    return True


def _merge_new_seed(cur, seeded):
    ret = cur.copy()
    ret['meta-data'] = util.mergemanydict([cur['meta-data'],
                                          util.load_yaml(seeded['meta-data'])])
    ret['user-data'] = seeded['user-data']
    if 'vendor-data' in seeded:
        ret['vendor-data'] = seeded['vendor-data']
    return ret


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
