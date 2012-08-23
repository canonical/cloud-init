# vi: ts=4 expandtab
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

from cloudinit import util

# The ssh-import-id only seems to exist on ubuntu (for now)
# https://launchpad.net/ssh-import-id
distros = ['ubuntu']


def handle(name, cfg, cloud, log, args):
    if len(args) != 0:
        user = args[0]
        ids = []
        if len(args) > 1:
            ids = args[1:]
    else:
        user = cloud.distro.get_default_user()

        if 'users' in cfg:
            user_zero = cfg['users'].keys()[0]

            if user_zero != "default":
                user = user_zero

        ids = util.get_cfg_option_list(cfg, "ssh_import_id", [])

    if len(ids) == 0:
        log.debug("Skipping module named %s, no ids found to import", name)
        return

    if not user:
        log.debug("Skipping module named %s, no user found to import", name)
        return

    cmd = ["sudo", "-Hu", user, "ssh-import-id"] + ids
    log.debug("Importing ssh ids for user %s.", user)

    try:
        util.subp(cmd, capture=False)
    except util.ProcessExecutionError as e:
        util.logexc(log, "Failed to run command to import %s ssh ids", user)
        raise e
