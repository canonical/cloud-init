# vi: ts=4 expandtab
#
#    Copyright (C) 2011 Canonical Ltd.
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

from xml.dom import minidom

import base64
import os
import re

from cloudinit import log as logging
from cloudinit import sources
from cloudinit import util

LOG = logging.getLogger(__name__)


class DataSourceOVF(sources.DataSource):
    def __init__(self, sys_cfg, distro, paths):
        sources.DataSource.__init__(self, sys_cfg, distro, paths)
        self.seed = None
        self.seed_dir = os.path.join(paths.seed_dir, 'ovf')
        self.environment = None
        self.cfg = {}
        self.supported_seed_starts = ("/", "file://")

    def __str__(self):
        root = sources.DataSource.__str__(self)
        return "%s [seed=%s]" % (root, self.seed)

    def get_data(self):
        found = []
        md = {}
        ud = ""

        defaults = {
            "instance-id": "iid-dsovf",
        }

        (seedfile, contents) = get_ovf_env(self.paths.seed_dir)
        if seedfile:
            # Found a seed dir
            seed = os.path.join(self.paths.seed_dir, seedfile)
            (md, ud, cfg) = read_ovf_environment(contents)
            self.environment = contents
            found.append(seed)
        else:
            np = {'iso': transport_iso9660,
                  'vmware-guestd': transport_vmware_guestd, }
            name = None
            for (name, transfunc) in np.iteritems():
                (contents, _dev, _fname) = transfunc()
                if contents:
                    break
            if contents:
                (md, ud, cfg) = read_ovf_environment(contents)
                self.environment = contents
                found.append(name)

        # There was no OVF transports found
        if len(found) == 0:
            return False

        if 'seedfrom' in md and md['seedfrom']:
            seedfrom = md['seedfrom']
            seedfound = False
            for proto in self.supported_seed_starts:
                if seedfrom.startswith(proto):
                    seedfound = proto
                    break
            if not seedfound:
                LOG.debug("Seed from %s not supported by %s",
                          seedfrom, self)
                return False

            (md_seed, ud) = util.read_seeded(seedfrom, timeout=None)
            LOG.debug("Using seeded cache data from %s", seedfrom)

            md = util.mergemanydict([md, md_seed])
            found.append(seedfrom)

        # Now that we have exhausted any other places merge in the defaults
        md = util.mergemanydict([md, defaults])

        self.seed = ",".join(found)
        self.metadata = md
        self.userdata_raw = ud
        self.cfg = cfg
        return True

    def get_public_ssh_keys(self):
        if 'public-keys' not in self.metadata:
            return []
        pks = self.metadata['public-keys']
        if isinstance(pks, (list)):
            return pks
        else:
            return [pks]

    # The data sources' config_obj is a cloud-config formatted
    # object that came to it from ways other than cloud-config
    # because cloud-config content would be handled elsewhere
    def get_config_obj(self):
        return self.cfg


class DataSourceOVFNet(DataSourceOVF):
    def __init__(self, sys_cfg, distro, paths):
        DataSourceOVF.__init__(self, sys_cfg, distro, paths)
        self.seed_dir = os.path.join(paths.seed_dir, 'ovf-net')
        self.supported_seed_starts = ("http://", "https://", "ftp://")


# This will return a dict with some content
#  meta-data, user-data, some config
def read_ovf_environment(contents):
    props = get_properties(contents)
    md = {}
    cfg = {}
    ud = ""
    cfg_props = ['password']
    md_props = ['seedfrom', 'local-hostname', 'public-keys', 'instance-id']
    for (prop, val) in props.iteritems():
        if prop == 'hostname':
            prop = "local-hostname"
        if prop in md_props:
            md[prop] = val
        elif prop in cfg_props:
            cfg[prop] = val
        elif prop == "user-data":
            try:
                ud = base64.decodestring(val)
            except:
                ud = val
    return (md, ud, cfg)


# Returns tuple of filename (in 'dirname', and the contents of the file)
# on "not found", returns 'None' for filename and False for contents
def get_ovf_env(dirname):
    env_names = ("ovf-env.xml", "ovf_env.xml", "OVF_ENV.XML", "OVF-ENV.XML")
    for fname in env_names:
        full_fn = os.path.join(dirname, fname)
        if os.path.isfile(full_fn):
            try:
                contents = util.load_file(full_fn)
                return (fname, contents)
            except:
                util.logexc(LOG, "Failed loading ovf file %s", full_fn)
    return (None, False)


# Transport functions take no input and return
# a 3 tuple of content, path, filename
def transport_iso9660(require_iso=True):

    # default_regex matches values in
    # /lib/udev/rules.d/60-cdrom_id.rules
    # KERNEL!="sr[0-9]*|hd[a-z]|xvd*", GOTO="cdrom_end"
    envname = "CLOUD_INIT_CDROM_DEV_REGEX"
    default_regex = "^(sr[0-9]+|hd[a-z]|xvd.*)"

    devname_regex = os.environ.get(envname, default_regex)
    cdmatch = re.compile(devname_regex)

    # Go through mounts to see if it was already mounted
    mounts = util.mounts()
    for (dev, info) in mounts.iteritems():
        fstype = info['fstype']
        if fstype != "iso9660" and require_iso:
            continue
        if cdmatch.match(dev[5:]) is None:  # take off '/dev/'
            continue
        mp = info['mountpoint']
        (fname, contents) = get_ovf_env(mp)
        if contents is not False:
            return (contents, dev, fname)

    if require_iso:
        mtype = "iso9660"
    else:
        mtype = None

    devs = os.listdir("/dev/")
    devs.sort()
    for dev in devs:
        fullp = os.path.join("/dev/", dev)

        if (fullp in mounts or
                not cdmatch.match(dev) or os.path.isdir(fullp)):
            continue

        try:
            # See if we can read anything at all...??
            util.peek_file(fullp, 512)
        except IOError:
            continue

        try:
            (fname, contents) = util.mount_cb(fullp, get_ovf_env, mtype=mtype)
        except util.MountFailedError:
            LOG.debug("%s not mountable as iso9660" % fullp)
            continue

        if contents is not False:
            return (contents, fullp, fname)

    return (False, None, None)


def transport_vmware_guestd():
    # http://blogs.vmware.com/vapp/2009/07/ \
    #    selfconfiguration-and-the-ovf-environment.html
    # try:
    #     cmd = ['vmware-guestd', '--cmd', 'info-get guestinfo.ovfEnv']
    #     (out, err) = subp(cmd)
    #     return(out, 'guestinfo.ovfEnv', 'vmware-guestd')
    # except:
    #     # would need to error check here and see why this failed
    #     # to know if log/error should be raised
    #     return(False, None, None)
    return (False, None, None)


def find_child(node, filter_func):
    ret = []
    if not node.hasChildNodes():
        return ret
    for child in node.childNodes:
        if filter_func(child):
            ret.append(child)
    return ret


def get_properties(contents):

    dom = minidom.parseString(contents)
    if dom.documentElement.localName != "Environment":
        raise XmlError("No Environment Node")

    if not dom.documentElement.hasChildNodes():
        raise XmlError("No Child Nodes")

    envNsURI = "http://schemas.dmtf.org/ovf/environment/1"

    # could also check here that elem.namespaceURI ==
    #   "http://schemas.dmtf.org/ovf/environment/1"
    propSections = find_child(dom.documentElement,
        lambda n: n.localName == "PropertySection")

    if len(propSections) == 0:
        raise XmlError("No 'PropertySection's")

    props = {}
    propElems = find_child(propSections[0],
                            (lambda n: n.localName == "Property"))

    for elem in propElems:
        key = elem.attributes.getNamedItemNS(envNsURI, "key").value
        val = elem.attributes.getNamedItemNS(envNsURI, "value").value
        props[key] = val

    return props


class XmlError(Exception):
    pass


# Used to match classes to dependencies
datasources = (
  (DataSourceOVF, (sources.DEP_FILESYSTEM, )),
  (DataSourceOVFNet, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
)


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
