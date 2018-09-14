# Copyright (C) 2012 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import os
import re

from cloudinit import handlers
from cloudinit import log as logging
from cloudinit import util

from cloudinit.settings import (PER_INSTANCE)

LOG = logging.getLogger(__name__)


class UpstartJobPartHandler(handlers.Handler):

    prefixes = ['#upstart-job']

    def __init__(self, paths, **_kwargs):
        handlers.Handler.__init__(self, PER_INSTANCE)
        self.upstart_dir = paths.upstart_conf_d

    def handle_part(self, data, ctype, filename, payload, frequency):
        if ctype in handlers.CONTENT_SIGNALS:
            return

        # See: https://bugs.launchpad.net/bugs/819507
        if frequency != PER_INSTANCE:
            return

        if not self.upstart_dir:
            return

        filename = util.clean_filename(filename)
        (_name, ext) = os.path.splitext(filename)
        if not ext:
            ext = ''
        ext = ext.lower()
        if ext != ".conf":
            filename = filename + ".conf"

        payload = util.dos2unix(payload)
        path = os.path.join(self.upstart_dir, filename)
        util.write_file(path, payload, 0o644)

        if SUITABLE_UPSTART:
            util.subp(["initctl", "reload-configuration"], capture=False)


def _has_suitable_upstart():
    # (LP: #1124384)
    # a bug in upstart means that invoking reload-configuration
    # at this stage in boot causes havoc.  So, try to determine if upstart
    # is installed, and reloading configuration is OK.
    if not os.path.exists("/sbin/initctl"):
        return False
    try:
        (version_out, _err) = util.subp(["initctl", "version"])
    except Exception:
        util.logexc(LOG, "initctl version failed")
        return False

    # expecting 'initctl version' to output something like: init (upstart X.Y)
    if re.match("upstart 1.[0-7][)]", version_out):
        return False
    if "upstart 0." in version_out:
        return False
    elif "upstart 1.8" in version_out:
        if not os.path.exists("/usr/bin/dpkg-query"):
            return False
        try:
            (dpkg_ver, _err) = util.subp(["dpkg-query",
                                          "--showformat=${Version}",
                                          "--show", "upstart"], rcs=[0, 1])
        except Exception:
            util.logexc(LOG, "dpkg-query failed")
            return False

        try:
            good = "1.8-0ubuntu1.2"
            util.subp(["dpkg", "--compare-versions", dpkg_ver, "ge", good])
            return True
        except util.ProcessExecutionError as e:
            if e.exit_code is 1:
                pass
            else:
                util.logexc(LOG, "dpkg --compare-versions failed [%s]",
                            e.exit_code)
        except Exception:
            util.logexc(LOG, "dpkg --compare-versions failed")
        return False
    else:
        return True


SUITABLE_UPSTART = _has_suitable_upstart()

# vi: ts=4 expandtab
