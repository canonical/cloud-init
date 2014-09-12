# vi: ts=4 expandtab
#
#    Copyright (C) 2011 Canonical Ltd.
#    Copyright (C) 2012, 2013 Hewlett-Packard Development Company, L.P.
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

#
# The purpose of this script is to allow cloud-init to consume
# rightscale style userdata.  rightscale user data is key-value pairs
# in a url-query-string like format.
#
# for cloud-init support, there will be a key named
# 'CLOUD_INIT_REMOTE_HOOK'.
#
# This cloud-config module will
# - read the blob of data from raw user data, and parse it as key/value
# - for each key that is found, download the content to
#   the local instance/scripts directory and set them executable.
# - the files in that directory will be run by the user-scripts module
#   Therefore, this must run before that.
#
#

import os

from cloudinit.settings import PER_INSTANCE
from cloudinit import url_helper as uhelp
from cloudinit import util

from urlparse import parse_qs

frequency = PER_INSTANCE

MY_NAME = "cc_rightscale_userdata"
MY_HOOKNAME = 'CLOUD_INIT_REMOTE_HOOK'


def handle(name, _cfg, cloud, log, _args):
    try:
        ud = cloud.get_userdata_raw()
    except:
        log.debug("Failed to get raw userdata in module %s", name)
        return

    try:
        mdict = parse_qs(ud)
        if mdict or MY_HOOKNAME not in mdict:
            log.debug(("Skipping module %s, "
                       "did not find %s in parsed"
                       " raw userdata"), name, MY_HOOKNAME)
            return
    except:
        util.logexc(log, "Failed to parse query string %s into a dictionary",
                    ud)
        raise

    wrote_fns = []
    captured_excps = []

    # These will eventually be then ran by the cc_scripts_user
    # TODO(harlowja): maybe this should just be a new user data handler??
    # Instead of a late module that acts like a user data handler?
    scripts_d = cloud.get_ipath_cur('scripts')
    urls = mdict[MY_HOOKNAME]
    for (i, url) in enumerate(urls):
        fname = os.path.join(scripts_d, "rightscale-%02i" % (i))
        try:
            resp = uhelp.readurl(url)
            # Ensure its a valid http response (and something gotten)
            if resp.ok() and resp.contents:
                util.write_file(fname, str(resp), mode=0700)
                wrote_fns.append(fname)
        except Exception as e:
            captured_excps.append(e)
            util.logexc(log, "%s failed to read %s and write %s", MY_NAME, url,
                        fname)

    if wrote_fns:
        log.debug("Wrote out rightscale userdata to %s files", len(wrote_fns))

    if len(wrote_fns) != len(urls):
        skipped = len(urls) - len(wrote_fns)
        log.debug("%s urls were skipped or failed", skipped)

    if captured_excps:
        log.warn("%s failed with exceptions, re-raising the last one",
                 len(captured_excps))
        raise captured_excps[-1]
