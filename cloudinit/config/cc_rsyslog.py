# vi: ts=4 expandtab syntax=python
#
#    Copyright (C) 2009-2010 Canonical Ltd.
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
"""
rsyslog module allows configuration of syslog logging via rsyslog
Configuration is done under the cloud-config top level 'rsyslog'.

Under 'rsyslog' you can define:
  - configs:  [default=[]]
    this is a list.  entries in it are a string or a dictionary.
    each entry has 2 parts:
       * content
       * filename
    if the entry is a string, then it is assigned to 'content'.
    for each entry, content is written to the provided filename.
    if filename is not provided, its default is read from 'config_filename'

    Content here can be any valid rsyslog configuration.  No format
    specific format is enforced.

    For simply logging to an existing remote syslog server, via udp:
      configs: ["*.* @192.168.1.1"]

  - config_filename: [default=20-cloud-config.conf]
    this is the file name to use if none is provided in a config entry.
  - config_dir: [default=/etc/rsyslog.d]
    this directory is used for filenames that are not absolute paths.
  - service_reload_command: [default="auto"]
    this command is executed if files have been written and thus the syslog
    daemon needs to be told.

Note, since cloud-init 0.5 a legacy version of rsyslog config has been
present and is still supported. See below for the mappings between old
value and new value:
   old value           -> new value
   'rsyslog'           -> rsyslog/configs
   'rsyslog_filename'  -> rsyslog/config_filename
   'rsyslog_dir'       -> rsyslog/config_dir

the legacy config does not support 'service_reload_command'.

Example config:
  #cloud-config
  rsyslog:
    configs:
      - "*.* @@192.158.1.1"
      - content: "*.*   @@192.0.2.1:10514"
      - filename: 01-examplecom.conf
      - content: |
        *.*   @@syslogd.example.com
    config_dir: config_dir
    config_filename: config_filename
    service_reload_command: [your, syslog, restart, command]

Example Legacy config:
  #cloud-config
  rsyslog:
    - "*.* @@192.158.1.1"
  rsyslog_dir: /etc/rsyslog-config.d/
  rsyslog_filename: 99-local.conf
"""

import os
import six

from cloudinit import log as logging
from cloudinit import util

DEF_FILENAME = "20-cloud-config.conf"
DEF_DIR = "/etc/rsyslog.d"
DEF_RELOAD = "auto"

KEYNAME_CONFIGS = 'configs'
KEYNAME_FILENAME = 'config_filename'
KEYNAME_DIR = 'config_dir'
KEYNAME_RELOAD = 'service_reload_command'
KEYNAME_LEGACY_FILENAME = 'rsyslog_filename'
KEYNAME_LEGACY_DIR = 'rsyslog_dir'

LOG = logging.getLogger(__name__)


def reload_syslog(command=DEF_RELOAD, systemd=False):
    service = 'rsyslog'
    if command == DEF_RELOAD:
        if systemd:
            cmd = ['systemctl', 'reload-or-try-restart', service]
        else:
            cmd = ['service', service, 'restart']
    else:
        cmd = command
    util.subp(cmd, capture=True)


def load_config(cfg):
    # return an updated config with entries of the correct type
    # support converting the old top level format into new format
    mycfg = cfg.get('rsyslog', {})

    if isinstance(cfg.get('rsyslog'), list):
        mycfg = {KEYNAME_CONFIGS: cfg.get('rsyslog')}
        if KEYNAME_LEGACY_FILENAME in cfg:
            mycfg[KEYNAME_FILENAME] = cfg[KEYNAME_LEGACY_FILENAME]
        if KEYNAME_LEGACY_DIR in cfg:
            mycfg[KEYNAME_DIR] = cfg[KEYNAME_LEGACY_DIR]

    fillup = (
        (KEYNAME_CONFIGS, [], list),
        (KEYNAME_DIR, DEF_DIR, six.string_types),
        (KEYNAME_FILENAME, DEF_FILENAME, six.string_types),
        (KEYNAME_RELOAD, DEF_RELOAD, six.string_types + (list,)))

    for key, default, vtypes in fillup:
        if key not in mycfg or not isinstance(mycfg[key], vtypes):
            mycfg[key] = default

    return mycfg


def apply_rsyslog_changes(configs, def_fname, cfg_dir):
    # apply the changes in 'configs' to the paths in def_fname and cfg_dir
    # return a list of the files changed
    files = []
    for cur_pos, ent in enumerate(configs):
        if isinstance(ent, dict):
            if "content" not in ent:
                LOG.warn("No 'content' entry in config entry %s", cur_pos + 1)
                continue
            content = ent['content']
            filename = ent.get("filename", def_fname)
        else:
            content = ent
            filename = def_fname

        filename = filename.strip()
        if not filename:
            LOG.warn("Entry %s has an empty filename", cur_pos + 1)
            continue

        if not filename.startswith("/"):
            filename = os.path.join(cfg_dir, filename)

        # Truncate filename first time you see it
        omode = "ab"
        if filename not in files:
            omode = "wb"
            files.append(filename)

        try:
            contents = "%s\n" % (content)
            util.write_file(filename, contents, omode=omode)
        except Exception:
            util.logexc(LOG, "Failed to write to %s", filename)

    return files


def handle(name, cfg, cloud, log, _args):
    if 'rsyslog' not in cfg:
        log.debug(("Skipping module named %s,"
                   " no 'rsyslog' key in configuration"), name)
        return

    mycfg = load_config(cfg)
    if not mycfg['configs']:
        log.debug("Empty config rsyslog['configs'], nothing to do")
        return

    changes = apply_rsyslog_changes(
        configs=mycfg[KEYNAME_CONFIGS],
        def_fname=mycfg[KEYNAME_FILENAME],
        cfg_dir=mycfg[KEYNAME_DIR])

    if not changes:
        log.debug("restart of syslog not necessary, no changes made")
        return

    try:
        restarted = reload_syslog(
            service=mycfg[KEYNAME_RELOAD],
            systemd=cloud.distro.uses_systemd()),
    except util.ProcessExecutionError as e:
        restarted = False
        log.warn("Failed to reload syslog", e)

    if restarted:
        # This only needs to run if we *actually* restarted
        # syslog above.
        cloud.cycle_logging()
        # This should now use rsyslog if
        # the logging was setup to use it...
        log.debug("%s configured %s files", name, changes)
