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

import cloudinit
import logging
import cloudinit.util as util
import traceback

DEF_FILENAME = "20-cloud-config.conf"
DEF_DIR = "/etc/rsyslog.d"


def handle(_name, cfg, _cloud, log, _args):
    # rsyslog:
    #  - "*.* @@192.158.1.1"
    #  - content: "*.*   @@192.0.2.1:10514"
    #  - filename: 01-examplecom.conf
    #    content: |
    #      *.*   @@syslogd.example.com

    # process 'rsyslog'
    if not 'rsyslog' in cfg:
        return

    def_dir = cfg.get('rsyslog_dir', DEF_DIR)
    def_fname = cfg.get('rsyslog_filename', DEF_FILENAME)

    files = []
    elst = []
    for ent in cfg['rsyslog']:
        if isinstance(ent, dict):
            if not "content" in ent:
                elst.append((ent, "no 'content' entry"))
                continue
            content = ent['content']
            filename = ent.get("filename", def_fname)
        else:
            content = ent
            filename = def_fname

        if not filename.startswith("/"):
            filename = "%s/%s" % (def_dir, filename)

        omode = "ab"
        # truncate filename first time you see it
        if filename not in files:
            omode = "wb"
            files.append(filename)

        try:
            util.write_file(filename, content + "\n", omode=omode)
        except Exception as e:
            log.debug(traceback.format_exc(e))
            elst.append((content, "failed to write to %s" % filename))

    # need to restart syslogd
    restarted = False
    try:
        # if this config module is running at cloud-init time
        # (before rsyslog is running) we don't actually have to
        # restart syslog.
        #
        # upstart actually does what we want here, in that it doesn't
        # start a service that wasn't running already on 'restart'
        # it will also return failure on the attempt, so 'restarted'
        # won't get set
        log.debug("restarting rsyslog")
        util.subp(['service', 'rsyslog', 'restart'])
        restarted = True

    except Exception as e:
        elst.append(("restart", str(e)))

    if restarted:
        # this only needs to run if we *actually* restarted
        # syslog above.
        cloudinit.logging_set_from_cfg_file()
        log = logging.getLogger()
        log.debug("rsyslog configured %s" % files)

    for e in elst:
        log.warn("rsyslog error: %s\n" % ':'.join(e))

    return
