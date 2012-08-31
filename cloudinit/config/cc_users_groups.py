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

from cloudinit.settings import PER_INSTANCE

frequency = PER_INSTANCE


def handle(name, cfg, cloud, log, _args):
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
                cloud.distro.create_group(group, [])

    if 'users' in cfg:
        user_zero = None

        for user_config in cfg['users']:

            # Handle the default user creation
            if 'default' in user_config:
                log.info("Creating default user")

                # Create the default user if so defined
                try:
                    cloud.distro.add_default_user()

                    if not user_zero:
                        user_zero = cloud.distro.get_default_user()

                except NotImplementedError:

                    if user_zero == name:
                        user_zero = None

                    log.warn("Distro has not implemented default user "
                             "creation. No default user will be created")

            elif isinstance(user_config, dict) and 'name' in user_config:

                name = user_config['name']
                if not user_zero:
                    user_zero = name

                # Make options friendly for distro.create_user
                new_opts = {}
                if isinstance(user_config, dict):
                    for opt in user_config:
                        new_opts[opt.replace('-', '_')] = user_config[opt]

                cloud.distro.create_user(**new_opts)

            else:
                # create user with no configuration
                cloud.distro.create_user(user_config)
