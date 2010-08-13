# vi: ts=4 expandtab
#
#    Copyright (C) 2009-2010 Canonical Ltd.
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

class DataSourceNoCloud(DataSource.DataSource):
    metadata = None
    userdata = None
    userdata_raw = None
    supported_seed_starts = ( "/" , "file://" )
    seed = None
    cmdline_id = "ds=nocloud"
    seeddir = cloudinit.cachedir + '/nocloud'

    def __init__(self):
        pass

    def __str__(self):
        mstr="DataSourceNoCloud"
        mstr = mstr + " [seed=%s]" % self.seed
        return(mstr)

    def get_data(self):
        defaults = { 
            "local-hostname" : "ubuntuhost",
            "instance-id" : "nocloud"
        }

        found = [ ]
        md = { }
        ud = ""

        try:
            # parse the kernel command line, getting data passed in
            if parse_cmdline_data(self.cmdline_id, md):
                found.append("cmdline")
        except:
            util.logexc(cloudinit.log,util.WARN)
            return False

        # check to see if the seeddir has data.
        seedret={ }
        if util.read_optional_seed(seedret,base=self.seeddir + "/"):
            md = util.mergedict(md,seedret['meta-data'])
            ud = seedret['user-data']
            found.append(self.seeddir)
            cloudinit.log.debug("using seeded cache data in %s" % self.seeddir)

        # there was no indication on kernel cmdline or data
        # in the seeddir suggesting this handler should be used.
        if len(found) == 0:
            return False

        # the special argument "seedfrom" indicates we should
        # attempt to seed the userdata / metadata from its value
        if "seedfrom" in md:
            seedfrom = md["seedfrom"]
            seedfound = False
            for proto in self.supported_seed_starts:
                if seedfrom.startswith(proto):
                    seedfound=proto
                    break
            if not seedfound:
                cloudinit.log.debug("seed from %s not supported by %s" %
                    (seedfrom, self.__class__))
                return False

            # this could throw errors, but the user told us to do it
            # so if errors are raised, let them raise
            (md_seed,ud) = util.read_seeded(seedfrom)
            cloudinit.log.debug("using seeded cache data from %s" % seedfrom)

            # values in the command line override those from the seed
            md = util.mergedict(md,md_seed)
            found.append(seedfrom)

        md = util.mergedict(md,defaults)
        self.seed = ",".join(found)
        self.metadata = md;
        self.userdata_raw = ud
        return True

# returns true or false indicating if cmdline indicated
# that this module should be used
# example cmdline:
#  root=LABEL=uec-rootfs ro ds=nocloud
def parse_cmdline_data(ds_id,fill,cmdline=None):
    if cmdline is None:
        if 'DEBUG_PROC_CMDLINE' in os.environ:
            cmdline = os.environ["DEBUG_PROC_CMDLINE"]
        else:
            cmdfp = open("/proc/cmdline")
            cmdline = cmdfp.read().strip()
            cmdfp.close()
        cmdline = " %s " % cmdline.lower()

        if not ( " %s " % ds_id in cmdline or " %s;" % ds_id in cmdline ):
            return False

    argline=""
    # cmdline can contain:
    # ds=nocloud[;key=val;key=val]
    for tok in cmdline.split():
        if tok.startswith(ds_id): argline=tok.split("=",1)
    
    # argline array is now 'nocloud' followed optionally by
    # a ';' and then key=value pairs also terminated with ';'
    tmp=argline[1].split(";")
    if len(tmp) > 1:
        kvpairs=tmp[1:]
    else:
        kvpairs=()

    # short2long mapping to save cmdline typing
    s2l = {  "h" : "local-hostname", "i" : "instance-id", "s" : "seedfrom" }
    for item in kvpairs:
        try:
            (k,v) = item.split("=",1)
        except:
            k=item
            v=None
        if k in s2l: k=s2l[k]
        fill[k]=v

    return(True)

class DataSourceNoCloudNet(DataSourceNoCloud):
    cmdline_id = "ds=nocloud-net"
    supported_seed_starts = ( "http://", "https://", "ftp://" )
    seeddir = cloudinit.cachedir + '/nocloud-net'
