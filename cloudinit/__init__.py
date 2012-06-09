# vi: ts=4 expandtab
#
#    Common code for the EC2 initialisation scripts in Ubuntu
#    Copyright (C) 2008-2009 Canonical Ltd
#    Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
#    Author: Soren Hansen <soren@canonical.com>
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

import os

import sys
import errno
import subprocess
import yaml
import glob

from cloudinit import log as logging
from cloudinit import sources
from cloudinit import url_helper as uhelp
from cloudinit import util

from cloudinit.settings import (VAR_LIB_DIR, CFG_BUILTIN, CLOUD_CONFIG,
                                 BOOT_FINISHED, CUR_INSTANCE_LINK)

LOG = logging.getLogger(__name__)

INIT_SUBDIRS = [
    os.path.join(VAR_LIB_DIR, 'scripts'),
    os.path.join(VAR_LIB_DIR, 'scripts', 'per-instance'),
    os.path.join(VAR_LIB_DIR, 'scripts', 'per-once'),
    os.path.join(VAR_LIB_DIR, 'scripts', 'per-boot'),
    os.path.join(VAR_LIB_DIR, 'seed'),
    os.path.join(VAR_LIB_DIR, 'instances'),
    os.path.join(VAR_LIB_DIR, 'handlers'),
    os.path.join(VAR_LIB_DIR, 'sem'),
    os.path.join(VAR_LIB_DIR, 'data'),
]


def initfs():
    util.ensure_dirs(INIT_SUBDIRS)
    cfg = util.get_base_cfg(CLOUD_CONFIG, get_builtin_cfg())
    log_file = util.get_cfg_option_str(cfg, 'def_log_file', None)
    perms = util.get_cfg_option_str(cfg, 'syslog_fix_perms', None)
    if log_file:
        util.ensure_file(log_file)
        if perms:
            (u, g) = perms.split(':', 1)
            if u == "-1" or u == "None":
                u = None
            if g == "-1" or g == "None":
                g = None
            util.chownbyname(log_file, u, g)


def purge_cache(rmcur=True):
    rmlist = [BOOT_FINISHED]
    if rmcur:
        rmlist.append(CUR_INSTANCE_LINK)
    for f in rmlist:
        util.unlink(f)
    return True


def get_base_cfg(cfg_path=None):
    if cfg_path is None:
        cfg_path = CLOUD_CONFIG
    return util.get_base_cfg(cfg_path, get_builtin_cfg())


def get_builtin_cfg():
    return dict(CFG_BUILTIN)


def list_sources(cfg_list, depends):
    return sources.list_sources(cfg_list, depends, ["cloudinit", ""])


def get_cmdline_url(names=None, starts=None, cmdline=None):
    if cmdline is None:
        cmdline = util.get_cmdline()
    if not names:
        names = ('cloud-config-url', 'url')
    if not starts:
        starts = "#cloud-config"

    data = util.keyval_str_to_dict(cmdline)
    url = None
    key = None
    for key in names:
        if key in data:
            url = data[key]
            break

    if url is None:
        return (None, None, None)

    contents = uhelp.readurl(url)
    if contents.startswith(starts):
        return (key, url, contents)

    return (key, url, None)
