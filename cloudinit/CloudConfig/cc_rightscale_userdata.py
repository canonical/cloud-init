# vi: ts=4 expandtab
#
#    Copyright (C) 2011 Canonical Ltd.
#    Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
#    Author: Scott Moser <scott.moser@canonical.com>
#    Author: Juerg Haefliger <juerg.haefliger@hp.com>
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

##
## The purpose of this script is to allow cloud-init to consume
## rightscale style userdata.  rightscale user data is key-value pairs
## in a url-query-string like format.
##
## for cloud-init support, there will be a key named
## 'CLOUD_INIT_REMOTE_HOOK'.
##
## This cloud-config module will
## - read the blob of data from raw user data, and parse it as key/value
## - for each key that is found, download the content to
##   the local instance/scripts directory and set them executable.
## - the files in that directory will be run by the user-scripts module
##   Therefore, this must run before that.
##
##

import cloudinit.util as util
from cloudinit.CloudConfig import per_instance
from cloudinit import get_ipath_cur
from urlparse import parse_qs

frequency = per_instance
my_name = "cc_rightscale_userdata"
my_hookname = 'CLOUD_INIT_REMOTE_HOOK'


def handle(_name, _cfg, cloud, log, _args):
    try:
        ud = cloud.get_userdata_raw()
    except:
        log.warn("failed to get raw userdata in %s" % my_name)
        return

    try:
        mdict = parse_qs(ud)
        if not my_hookname in mdict:
            return
    except:
        log.warn("failed to urlparse.parse_qa(userdata_raw())")
        raise

    scripts_d = get_ipath_cur('scripts')
    i = 0
    first_e = None
    for url in mdict[my_hookname]:
        fname = "%s/rightscale-%02i" % (scripts_d, i)
        i = i + 1
        try:
            content = util.readurl(url)
            util.write_file(fname, content, mode=0700)
        except Exception as e:
            if not first_e:
                first_e = None
            log.warn("%s failed to read %s: %s" % (my_name, url, e))

    if first_e:
        raise(e)
