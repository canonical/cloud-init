# Copyright (C) 2009-2010 Canonical Ltd.
# Copyright (C) 2012, 2013 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""
SSH Import Id
-------------
**Summary:** import ssh id

This module imports ssh keys from either a public keyserver, usually launchpad
or github using ``ssh-import-id``. Keys are referenced by the username they are
associated with on the keyserver. The keyserver can be specified by prepending
either ``lp:`` for launchpad or ``gh:`` for github to the username.

**Internal name:** ``cc_ssh_import_id``

**Module frequency:** per instance

**Supported distros:** ubuntu, debian

**Config keys**::

    ssh_import_id:
        - user
        - gh:user
        - lp:user
"""

from cloudinit.distros import ug_util
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
    (users, _groups) = ug_util.normalize_users_groups(cfg, cloud.distro)
    elist = []
    for (user, user_cfg) in users.items():
        import_ids = []
        if user_cfg['default']:
            import_ids = util.get_cfg_option_list(cfg, "ssh_import_id", [])
        else:
            try:
                import_ids = user_cfg['ssh_import_id']
            except Exception:
                log.debug("User %s is not configured for ssh_import_id", user)
                continue

        try:
            import_ids = util.uniq_merge(import_ids)
            import_ids = [str(i) for i in import_ids]
        except Exception:
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

# vi: ts=4 expandtab
