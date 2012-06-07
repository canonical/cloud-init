# vi: ts=4 expandtab
#
#    Copyright (C) 2011 Canonical Ltd.
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
import os.path
import os
from xml.dom import minidom
import base64
import re
import tempfile
import subprocess


class DataSourceOVF(DataSource.DataSource):
    seed = None
    seeddir = base_seeddir + '/ovf'
    environment = None
    cfg = {}
    userdata_raw = None
    metadata = None
    supported_seed_starts = ("/", "file://")

    def __str__(self):
        mstr = "DataSourceOVF"
        mstr = mstr + " [seed=%s]" % self.seed
        return(mstr)

    def get_data(self):
        found = []
        md = {}
        ud = ""

        defaults = {
            "instance-id": "iid-dsovf"
        }

        (seedfile, contents) = get_ovf_env(base_seeddir)
        if seedfile:
            # found a seed dir
            seed = "%s/%s" % (base_seeddir, seedfile)
            (md, ud, cfg) = read_ovf_environment(contents)
            self.environment = contents

            found.append(seed)
        else:
            np = {'iso': transport_iso9660,
                  'vmware-guestd': transport_vmware_guestd, }
            name = None
            for name, transfunc in np.iteritems():
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
                log.debug("seed from %s not supported by %s" %
                    (seedfrom, self.__class__))
                return False

            (md_seed, ud) = util.read_seeded(seedfrom, timeout=None)
            log.debug("using seeded cache data from %s" % seedfrom)

            md = util.mergedict(md, md_seed)
            found.append(seedfrom)

        md = util.mergedict(md, defaults)
        self.seed = ",".join(found)
        self.metadata = md
        self.userdata_raw = ud
        self.cfg = cfg
        return True

    def get_public_ssh_keys(self):
        if not 'public-keys' in self.metadata:
            return([])
        return([self.metadata['public-keys'], ])

    # the data sources' config_obj is a cloud-config formated
    # object that came to it from ways other than cloud-config
    # because cloud-config content would be handled elsewhere
    def get_config_obj(self):
        return(self.cfg)


class DataSourceOVFNet(DataSourceOVF):
    seeddir = base_seeddir + '/ovf-net'
    supported_seed_starts = ("http://", "https://", "ftp://")


# this will return a dict with some content
#  meta-data, user-data
def read_ovf_environment(contents):
    props = getProperties(contents)
    md = {}
    cfg = {}
    ud = ""
    cfg_props = ['password', ]
    md_props = ['seedfrom', 'local-hostname', 'public-keys', 'instance-id']
    for prop, val in props.iteritems():
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
    return(md, ud, cfg)


# returns tuple of filename (in 'dirname', and the contents of the file)
# on "not found", returns 'None' for filename and False for contents
def get_ovf_env(dirname):
    env_names = ("ovf-env.xml", "ovf_env.xml", "OVF_ENV.XML", "OVF-ENV.XML")
    for fname in env_names:
        if os.path.isfile("%s/%s" % (dirname, fname)):
            fp = open("%s/%s" % (dirname, fname))
            contents = fp.read()
            fp.close()
            return(fname, contents)
    return(None, False)


# transport functions take no input and return
# a 3 tuple of content, path, filename
def transport_iso9660(require_iso=True):

    # default_regex matches values in
    # /lib/udev/rules.d/60-cdrom_id.rules
    # KERNEL!="sr[0-9]*|hd[a-z]|xvd*", GOTO="cdrom_end"
    envname = "CLOUD_INIT_CDROM_DEV_REGEX"
    default_regex = "^(sr[0-9]+|hd[a-z]|xvd.*)"

    devname_regex = os.environ.get(envname, default_regex)
    cdmatch = re.compile(devname_regex)

    # go through mounts to see if it was already mounted
    fp = open("/proc/mounts")
    mounts = fp.readlines()
    fp.close()

    mounted = {}
    for mpline in mounts:
        (dev, mp, fstype, _opts, _freq, _passno) = mpline.split()
        mounted[dev] = (dev, fstype, mp, False)
        mp = mp.replace("\\040", " ")
        if fstype != "iso9660" and require_iso:
            continue

        if cdmatch.match(dev[5:]) == None:  # take off '/dev/'
            continue

        (fname, contents) = get_ovf_env(mp)
        if contents is not False:
            return(contents, dev, fname)

    tmpd = None
    dvnull = None

    devs = os.listdir("/dev/")
    devs.sort()

    for dev in devs:
        fullp = "/dev/%s" % dev

        if fullp in mounted or not cdmatch.match(dev) or os.path.isdir(fullp):
            continue

        fp = None
        try:
            fp = open(fullp, "rb")
            fp.read(512)
            fp.close()
        except:
            if fp:
                fp.close()
            continue

        if tmpd is None:
            tmpd = tempfile.mkdtemp()
        if dvnull is None:
            try:
                dvnull = open("/dev/null")
            except:
                pass

        cmd = ["mount", "-o", "ro", fullp, tmpd]
        if require_iso:
            cmd.extend(('-t', 'iso9660'))

        rc = subprocess.call(cmd, stderr=dvnull, stdout=dvnull, stdin=dvnull)
        if rc:
            continue

        (fname, contents) = get_ovf_env(tmpd)

        subprocess.call(["umount", tmpd])

        if contents is not False:
            os.rmdir(tmpd)
            return(contents, fullp, fname)

    if tmpd:
        os.rmdir(tmpd)

    if dvnull:
        dvnull.close()

    return(False, None, None)


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
    return(False, None, None)


def findChild(node, filter_func):
    ret = []
    if not node.hasChildNodes():
        return ret
    for child in node.childNodes:
        if filter_func(child):
            ret.append(child)
    return(ret)


def getProperties(environString):
    dom = minidom.parseString(environString)
    if dom.documentElement.localName != "Environment":
        raise Exception("No Environment Node")

    if not dom.documentElement.hasChildNodes():
        raise Exception("No Child Nodes")

    envNsURI = "http://schemas.dmtf.org/ovf/environment/1"

    # could also check here that elem.namespaceURI ==
    #   "http://schemas.dmtf.org/ovf/environment/1"
    propSections = findChild(dom.documentElement,
        lambda n: n.localName == "PropertySection")

    if len(propSections) == 0:
        raise Exception("No 'PropertySection's")

    props = {}
    propElems = findChild(propSections[0], lambda n: n.localName == "Property")

    for elem in propElems:
        key = elem.attributes.getNamedItemNS(envNsURI, "key").value
        val = elem.attributes.getNamedItemNS(envNsURI, "value").value
        props[key] = val

    return(props)


datasources = (
  (DataSourceOVF, (DataSource.DEP_FILESYSTEM, )),
  (DataSourceOVFNet,
    (DataSource.DEP_FILESYSTEM, DataSource.DEP_NETWORK)),
)


# return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return(DataSource.list_from_depends(depends, datasources))


if __name__ == "__main__":
    def main():
        import sys
        envStr = open(sys.argv[1]).read()
        props = getProperties(envStr)
        import pprint
        pprint.pprint(props)

        md, ud, cfg = read_ovf_environment(envStr)
        print "=== md ==="
        pprint.pprint(md)
        print "=== ud ==="
        pprint.pprint(ud)
        print "=== cfg ==="
        pprint.pprint(cfg)

    main()
