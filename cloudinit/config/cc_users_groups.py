# vi: ts=4 expandtab
#
#    Copyright (C) 2012 Canonical Ltd.
#
#    Author: Ben Howard <ben.howard@canonical.com>
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

from cloudinit import distros
from cloudinit import util

from cloudinit.settings import PER_INSTANCE

frequency = PER_INSTANCE


def handle(name, cfg, cloud, log, _args):
    def_u = None
    def_u_gs = None
    try:
        def_u = cloud.distro.get_default_user()
        def_u_gs = cloud.distro.get_default_user_groups()
    except NotImplementedError:
        log.warn(("Distro has not implemented default user "
                  "creation. No default user will be added."))

    ((users, default_user), groups) = distros.normalize_users_groups(cfg,
                                                                     def_u,
                                                                     def_u_gs)
    for (name, members) in groups.items():
        cloud.distro.create_group(name, members)

    if default_user:
        user = default_user['name']
        config = default_user['config']
        def_base_config = {
            'plain_text_passwd': user,
            'home': "/home/%s" % user,
            'shell': "/bin/bash",
            'lock_passwd': True,
            'gecos': "%s%s" % (user.title()),
            'sudo': "ALL=(ALL) NOPASSWD:ALL",
        }
        u_config = util.mergemanydict([def_base_config, config])
        cloud.distro.create_user(user, **u_config)
        log.info("Added default '%s' user with passwordless sudo", user)

    for (user, config) in users.items():
        cloud.distro.create_user(user, **config)
