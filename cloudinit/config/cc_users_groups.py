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

import grp
import os
import pwd
import traceback

from cloudinit.settings import PER_INSTANCE
from cloudinit import ssh_util
from cloudinit import templater
from cloudinit import util

frequency = PER_INSTANCE


def handle(name, cfg, cloud, log, _args):
    groups_cfg = None
    users_cfg = None
    user_zero = None

    if 'groups' in cfg:
        for group in cfg['groups']:
            if isinstance(group, dict):
                for name, values in group.iteritems():
                    if isinstance(values, list):
                        cloud.distro.create_group(name, values)
                    elif isinstance(values, str):
                        cloud.distro.create_group(name, values.split(','))
            else:
                cloud.distro.create_group(item, [])

    if 'users' in cfg:
        user_zero = None

        for name, user_config in cfg['users'].iteritems():
            if not user_zero:
                user_zero = name

            # Handle the default user creation
            if name == "default" and user_config:
                log.info("Creating default user")

                # Create the default user if so defined
                try:
                    cloud.distro.add_default_user()

                    if user_zero == name:
                        user_zero = cloud.distro.get_default_user()

                except NotImplementedError as e:

                    if user_zero == name:
                        user_zero = None

                    log.warn("Distro has not implemented default user "
                             "creation. No default user will be created")
            else:
                # Make options friendly for distro.create_user
                new_opts = {}
                if isinstance(user_config, dict):
                    for opt in user_config:
                        new_opts[opt.replace('-', '')] = user_config[opt]

                cloud.distro.create_user(name, **new_opts)
