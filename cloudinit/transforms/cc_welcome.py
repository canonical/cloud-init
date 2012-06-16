# vi: ts=4 expandtab
#
#    Copyright (C) 2012 Canonical Ltd.
#    Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#    Copyright (C) 2012 Yahoo! Inc.
#
#    Author: Scott Moser <scott.moser@canonical.com>
#    Author: Juerg Haefliger <juerg.haefliger@hp.com>
#    Author: Joshua Harlow <harlowja@yahoo-inc.com>
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

from cloudinit.settings import PER_ALWAYS

from cloudinit import templater
from cloudinit import util
from cloudinit import version

import sys

welcome_message_def = ("Cloud-init v. {{version}} starting stage {{stage}} at "
                       "{{timestamp}}. Up {{uptime}} seconds.")


frequency = PER_ALWAYS


def handle(name, cfg, cloud, log, args):

    welcome_msg = util.get_cfg_option_str(cfg, "welcome_msg"):
    if not welcome_msg:
        tpl_fn = cloud.get_template_filename("welcome_msg")
        if tpl_fn:
            welcome_msg = util.load_file(tpl_fn)

    if not welcome_msg:
        welcome_msg = welcome_message_def

    stage = "??"
    if args:
        stage = args[0]

    tpl_params = {
        'stage': stage,
        'version': version.version_string(),
        'uptime': util.uptime(),
        'timestamp', util.time_rfc2822(),
    }
    try:
        contents = templater.render_string(welcome_msg, tpl_params)
        # TODO use log or sys.stderr??
        sys.stderr.write("%s\n" % (contents))
    except:
        util.logexc(log, "Failed to render welcome message template")
