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

from cloudinit import util

from cloudinit.settings import PER_INSTANCE

frequency = PER_INSTANCE


def handle(name, cfg, cloud, log, _args):

    distro = cloud.distro
    ((users, default_user), groups) = distro.normalize_users_groups(cfg)
    for (name, members) in groups.items():
        distro.create_group(name, members)

    if default_user:
        user = default_user['name']
        config = default_user['config']
        def_base_config = {
            'name': user,
            'plain_text_passwd': user,
            'home': "/home/%s" % user,
            'shell': "/bin/bash",
            'lock_passwd': True,
            'gecos': "%s%s" % (user.title()),
            'sudo': "ALL=(ALL) NOPASSWD:ALL",
        }
        u_config = util.mergemanydict([def_base_config, config])
        distro.create_user(**u_config)

    for (user, config) in users.items():
        distro.create_user(user, **config)
