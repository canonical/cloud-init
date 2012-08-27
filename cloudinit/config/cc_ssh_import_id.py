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
import pwd

# The ssh-import-id only seems to exist on ubuntu (for now)
# https://launchpad.net/ssh-import-id
distros = ['ubuntu']


def handle(name, cfg, cloud, log, args):

    # import for "user: XXXXX"
    if len(args) != 0:
        user = args[0]
        ids = []
        if len(args) > 1:
            ids = args[1:]

        import_ssh_ids(ids, user, log)

    # import for cloudinit created users
    for user in cfg['users'].keys():
        if user == "default":
            distro_user = cloud.distro.get_default_user()
            d_ids = util.get_cfg_option_list(cfg, "ssh_import_id", [])
            import_ssh_ids(d_ids, distro_user, log)

        user_cfg = cfg['users'][user]
        if not isinstance(user_cfg, dict):
            user_cfg = None

        if user_cfg:
            ids = util.get_cfg_option_list(user_cfg, "ssh_import_id", [])
            import_ssh_ids(ids, user, log)


def import_ssh_ids(ids, user):

    if not user:
        log.debug("Skipping ssh-import-ids, no user for ids")
        return

    if len(ids) == 0:
        log.debug("Skipping ssh-import-ids for %s, no ids to import" % user)
        return

    try:
        check = pwd.getpwnam(user)
    except KeyError:
        log.debug("Skipping ssh-import-ids for %s, user not found" % user)

    cmd = ["sudo", "-Hu", user, "ssh-import-id"] + ids
    log.debug("Importing ssh ids for user %s.", user)

    try:
        util.subp(cmd, capture=False)
    except util.ProcessExecutionError as e:
        util.logexc(log, "Failed to run command to import %s ssh ids", user)
        raise e
