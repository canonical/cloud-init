# vi: ts=4 expandtab
#
#    Copyright (C) 2009-2010 Canonical Ltd.
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

# Ensure this is aliased to a name not 'distros'
# since the module attribute 'distros'
# is a list of distros that are supported, not a sub-module
from cloudinit import distros as ds

from cloudinit import util
import pwd

# https://launchpad.net/ssh-import-id
distros = ['ubuntu', 'debian']


def handle(_name, cfg, cloud, log, args):

    # import for "user: XXXXX"
    if len(args) != 0:
        user = args[0]
        ids = []
        if len(args) > 1:
            ids = args[1:]

        import_ssh_ids(ids, user, log)
        return

    # import for cloudinit created users
    (users, _groups) = ds.normalize_users_groups(cfg, cloud.distro)
    elist = []
    for (user, user_cfg) in users.items():
        import_ids = []
        if user_cfg['default']:
            import_ids = util.get_cfg_option_list(cfg, "ssh_import_id", [])
        else:
            try:
                import_ids = user_cfg['ssh_import_id']
            except:
                log.debug("User %s is not configured for ssh_import_id", user)
                continue

        try:
            import_ids = util.uniq_merge(import_ids)
            import_ids = [str(i) for i in import_ids]
        except:
            log.debug("User %s is not correctly configured for ssh_import_id",
                      user)
            continue

        if not len(import_ids):
            continue

        try:
            import_ssh_ids(import_ids, user, log)
        except Exception as exc:
            util.logexc(log, "ssh-import-id failed for: %s %s", user,
                        import_ids)
            elist.append(exc)

    if len(elist):
        raise elist[0]


def import_ssh_ids(ids, user, log):

    if not (user and ids):
        log.debug("empty user(%s) or ids(%s). not importing", user, ids)
        return

    try:
        pwd.getpwnam(user)
    except KeyError as exc:
        raise exc

    cmd = ["sudo", "-Hu", user, "ssh-import-id"] + ids
    log.debug("Importing ssh ids for user %s.", user)

    try:
        util.subp(cmd, capture=False)
    except util.ProcessExecutionError as exc:
        util.logexc(log, "Failed to run command to import %s ssh ids", user)
        raise exc
