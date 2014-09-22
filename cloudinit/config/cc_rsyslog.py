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

import os

from cloudinit import util

DEF_FILENAME = "20-cloud-config.conf"
DEF_DIR = "/etc/rsyslog.d"


def handle(name, cfg, cloud, log, _args):
    # rsyslog:
    #  - "*.* @@192.158.1.1"
    #  - content: "*.*   @@192.0.2.1:10514"
    #  - filename: 01-examplecom.conf
    #    content: |
    #      *.*   @@syslogd.example.com

    # process 'rsyslog'
    if 'rsyslog' not in cfg:
        log.debug(("Skipping module named %s,"
                   " no 'rsyslog' key in configuration"), name)
        return

    def_dir = cfg.get('rsyslog_dir', DEF_DIR)
    def_fname = cfg.get('rsyslog_filename', DEF_FILENAME)

    files = []
    for i, ent in enumerate(cfg['rsyslog']):
        if isinstance(ent, dict):
            if "content" not in ent:
                log.warn("No 'content' entry in config entry %s", i + 1)
                continue
            content = ent['content']
            filename = ent.get("filename", def_fname)
        else:
            content = ent
            filename = def_fname

        filename = filename.strip()
        if not filename:
            log.warn("Entry %s has an empty filename", i + 1)
            continue

        if not filename.startswith("/"):
            filename = os.path.join(def_dir, filename)

        # Truncate filename first time you see it
        omode = "ab"
        if filename not in files:
            omode = "wb"
            files.append(filename)

        try:
            contents = "%s\n" % (content)
            util.write_file(filename, contents, omode=omode)
        except Exception:
            util.logexc(log, "Failed to write to %s", filename)

    # Attempt to restart syslogd
    restarted = False
    try:
        # If this config module is running at cloud-init time
        # (before rsyslog is running) we don't actually have to
        # restart syslog.
        #
        # Upstart actually does what we want here, in that it doesn't
        # start a service that wasn't running already on 'restart'
        # it will also return failure on the attempt, so 'restarted'
        # won't get set.
        log.debug("Restarting rsyslog")
        util.subp(['service', 'rsyslog', 'restart'])
        restarted = True
    except Exception:
        util.logexc(log, "Failed restarting rsyslog")

    if restarted:
        # This only needs to run if we *actually* restarted
        # syslog above.
        cloud.cycle_logging()
        # This should now use rsyslog if
        # the logging was setup to use it...
        log.debug("%s configured %s files", name, files)
