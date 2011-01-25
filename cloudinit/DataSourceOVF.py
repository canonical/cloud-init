# vi: ts=4 expandtab
#
#    Copyright (C) 2011 Canonical Ltd.
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

import DataSource

import cloudinit
import cloudinit.util as util
import sys
import os.path
import os
import errno
from xml.dom import minidom
from xml.dom import Node

class DataSourceOVF(DataSource.DataSource):
    seed = None
    seeddir = cloudinit.seeddir + '/ovf'

    def __init__(self):
        pass

    def __str__(self):
        mstr="DataSourceOVF"
        mstr = mstr + " [seed=%s]" % self.seed
        return(mstr)

    def get_data(self):
        (seedfile, contents) = get_ovf_env(seeddir)
        if seedfile:
            # found a seed dir
            self.seed = "%s/%s" % (dirname,seedfile)
            ret = read_ovf_environment(contents)
            # self.user_data=ret['user-data']
            # self.meta_data=ret['meta-data']
            return(True)

        (dev, fname, contents) = find_ovf_env()
        if not dev:
            return(False)

        ret = read_ovf_environment(contents)
        # self.user_data=ret['user-data']
        # self.meta_data=ret['meta-data']
        return(True)


# this will return a dict with some content
#  meta-data, user-data
def read_ovf_environment(contents):
    # this should basically shove into python objects
    # the values we read from ovf environment
    self.metadata = md;
    self.userdata_raw = ud
        

# returns tuple of filename (in 'dirname', and the contents of the file)
# on "not found", returns 'None' for filename and False for contents
def get_ovf_env(dirname):
    env_names = ("ovf-env.xml", "ovf_env.xml", "OVF_ENV.XML", "OVF-ENV.XML" )
    for fname in env_names:
        if os.path.isfile("%s/%s" % (dirname,fname)):
            fp = open("%s/%s" % (dirname,fname))
            contents = fp.read()
            fp.close()
            return(fname,contents)
    return(None,False)

def find_ovf_env(require_iso=False):

    # default_regex matches values in 
    # /lib/udev/rules.d/60-cdrom_id.rules
    # KERNEL!="sr[0-9]*|hd[a-z]|xvd*", GOTO="cdrom_end"
    envname = "CLOUD_INIT_CDROM_DEV_REGEX"
    default_regex = "^(sr[0-9]+|hd[a-z]|xvd.*)"

    devname_regex = os.environ.get(envname,default_regex)
    cdmatch = re.compile(devname_regex)

    # go through mounts to see if it was already mounted
    fp = open("/proc/mounts")
    mounts = fp.readlines()
    fp.close()

    mounted = { }
    for mpline in mounts:
        (dev,mp,fstype,opts,freq,passno) = mpline.split()
        mounted[dev]=(dev,fstype,mp,False)
        mp = mp.replace("\\040"," ")
        if fstype != "iso9660" and require_iso: continue

        if cdmatch.match(dev[5:]) == None: # take off '/dev/'
            continue
        
        (fname,contents) = get_ovf_env(mp)
        if contents is not False:
            return (dev,fname,contents)

    tmpd = None
    dvnull = None

    devs = os.listdir("/dev/")
    devs.sort()

    for dev in devs:
        fullp = "/dev/%s" % dev

        if fullp in mounted or not cdmatch.match(dev) or os.path.isdir(fullp):
            continue

        if tmpd is None:
            tmpd = tempfile.mkdtemp()
        if dvnull is None:
            try:
                dvnull = open("/dev/null")
            except:
                pass

        cmd = [ "mount", "-o", "ro", fullp, tmpd ]
        if require_iso: cmd.extend(('-t','iso9660'))

        rc = subprocess.call(cmd, stderr=dvnull, stdout=dvnull, stdin=dvnull)
        if rc:
            continue

        (fname,contents) = get_ovf_env(tmpd)

        subprocess.call(["umount", tmpd])

        if contents is not False:
            os.rmdir(tmpd)
            return (fullp,fname,contents)

    if tmpd:
        os.rmdir(tmpd)

    if dvnull:
        dvnull.close()

    return (None,None,False)

def findChild(node,filter_func):
    ret = []
    if not node.hasChildNodes(): return ret
    for child in node.childNodes:
        if filter_func(child): ret.append(child)
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

    props = { }
    propElems = findChild(propSections[0], lambda n: n.localName == "Property")

    for elem in propElems:
        key = elem.attributes.getNamedItemNS(envNsURI,"key").value
        val = elem.attributes.getNamedItemNS(envNsURI,"value").value
        props[key] = val

    return(props)

if __name__ == "__main__":
    import sys
    envStr = open(sys.argv[1]).read()
    props = getProperties(envStr)
    import pprint
    pprint.pprint(props)
    
    read_ovf_environment
