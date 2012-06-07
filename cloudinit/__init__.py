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
import os.path
import errno
import subprocess
import yaml
import glob
import traceback

import cloudinit.log as logging
import cloudinit.shell as sh
import cloudinit.util as util

from cloudinit.constants import (VAR_LIB_DIR, CFG_BUILTIN, CLOUD_CONFIG,
                                 BOOT_FINISHED, CUR_INSTANCE_LINK, PATH_MAP)

LOG = logging.getLogger(__name__)

INIT_SUBDIRS = [
    'scripts',
    os.path.join('scripts', 'per-instance'),
    os.path.join('scripts', 'per-once'),
    os.path.join('scripts', 'per-boot'),
    'seed',
    'instances',
    'handlers',
    'sem',
    'data'
]


# TODO: get rid of this global
parsed_cfgs = {}


def initfs():

    # TODO don't do this every time this function is called?
    dlist = []
    for subd in INIT_SUBDIRS:
        dlist.append(os.path.join(VAR_LIB_DIR, subd))
    sh.ensure_dirs(dlist)

    cfg = util.get_base_cfg(CLOUD_CONFIG, get_builtin_cfg(), parsed_cfgs)
    log_file = util.get_cfg_option_str(cfg, 'def_log_file', None)
    perms = util.get_cfg_option_str(cfg, 'syslog_fix_perms', None)
    if log_file:
        sh.ensure_file(log_file)
    if log_file and perms:
        (u, g) = perms.split(':', 1)
        if u == "-1" or u == "None":
            u = None
        if g == "-1" or g == "None":
            g = None
        sh.chownbyname(log_file, u, g)


def purge_cache(rmcur=True):
    rmlist = [BOOT_FINISHED]
    if rmcur:
        rmlist.append(CUR_INSTANCE_LINK)
    for f in rmlist:
        try:
            sh.unlink(f)
        except OSError as e:
            if e.errno == errno.ENOENT:
                continue
            return False
        except:
            return False
    return True


# get_ipath_cur: get the current instance path for an item
def get_ipath_cur(name=None):
    add_on = PATH_MAP.get(name)
    ipath = os.path.join(VAR_LIB_DIR, 'instance')
    if add_on:
        ipath = os.path.join(ipath, add_on)
    return ipath


# get_cpath : get the "clouddir" (/var/lib/cloud/<name>)
# for a name in dirmap
def get_cpath(name=None):
    cpath = VAR_LIB_DIR
    add_on = PATH_MAP.get(name)
    if add_on:
        cpath = os.path.join(cpath, add_on)
    return cpath


def get_base_cfg(cfg_path=None):
    if cfg_path is None:
        cfg_path = CLOUD_CONFIG
    return util.get_base_cfg(cfg_path, get_builtin_cfg(), parsed_cfgs)


def get_builtin_cfg():
    return dict(CFG_BUILTIN)


def list_sources(cfg_list, depends):
    return (DataSource.list_sources(cfg_list, depends, ["cloudinit", ""]))


def get_cmdline_url(names=('cloud-config-url', 'url'),
                    starts="#cloud-config", cmdline=None):

    if cmdline == None:
        cmdline = util.get_cmdline()

    data = util.keyval_str_to_dict(cmdline)
    url = None
    key = None
    for key in names:
        if key in data:
            url = data[key]
            break
    if url == None:
        return (None, None, None)

    contents = util.readurl(url)

    if contents.startswith(starts):
        return (key, url, contents)

    return (key, url, None)
