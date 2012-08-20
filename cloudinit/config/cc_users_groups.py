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
import pwd
import os
import traceback

from cloudinit import templater
from cloudinit import util
from cloudinit import ssh_util
from cloudinit.settings import PER_INSTANCE

frequency = PER_INSTANCE

def handle(name, cfg, cloud, log, _args):

    groups_cfg = None
    users_cfg = None
    user_zero = None

    if 'groups' in cfg:
        groups_cfg = cfg['groups']
        create_groups(groups_cfg, log)

    if 'users' in  cfg:
        users_cfg = cfg['users']
        user_zero = users_cfg.keys()[0]

        for name, user_config in users_cfg.iteritems():
            if name == "default" and user_config:
                log.info("Creating default user")

                # Create the default user if so defined
                try:
                     cloud.distro.add_default_user()

                except NotImplementedError as e:
                     log.warn(("Distro has not implemented default user"
                               "creation. No default user will be created"))

                # Get the distro user
                if user_zero == 'default':
                    try:
                        user_zero = cloud.distro.get_default_username()

                    except NotImplementedError:
                        pass

            else:
                create_user(name, user_config, log, cloud)

    # Override user directive
    if user_zero and check_user(user_zero):
        cfg['user'] = user_zero
        log.info("Override user directive with '%s'" % user_zero)


def check_user(user):
    try:
        user = pwd.getpwnam(user)
        return True

    except KeyError:
        return False

    return False

def create_user(user, user_config, log, cloud):
    # Iterate over the users definition and create the users

    if check_user(user):
        log.warn("User %s already exists, skipping." % user)

    else:
        log.info("Creating user %s" % user)

    adduser_cmd = ['useradd', user]
    x_adduser_cmd = adduser_cmd
    adduser_opts = {
            "gecos": '--comment',
            "homedir": '--home',
            "primary-group": '--gid',
            "groups": '--groups',
            "passwd": '--password',
            "shell": '--shell',
            "expiredate": '--expiredate',
            "inactive": '--inactive',
            }

    adduser_opts_flags = {
            "no-user-group": '--no-user-group',
            "system": '--system',
            "no-log-init": '--no-log-init',
            "no-create-home": "-M",
            }

    # Now check the value and create the command
    for option in user_config:
        value = user_config[option]
        if option in adduser_opts and value \
            and type(value).__name__ == "str":
            adduser_cmd.extend([adduser_opts[option], value])

            # Redact the password field from the logs
            if option != "password":
                x_adduser_cmd.extend([adduser_opts[option], value])
            else:
                x_adduser_cmd.extend([adduser_opts[option], 'REDACTED'])

        if option in adduser_opts_flags and value:
            adduser_cmd.append(adduser_opts_flags[option])
            x_adduser_cmd.append(adduser_opts_flags[option])

    # Default to creating home directory unless otherwise directed
    #  Also, we do not create home directories for system users.
    if "no-create-home" not in user_config and \
	"system" not in user_config:
        adduser_cmd.append('-m')

    print adduser_cmd

    # Create the user
    try:
        util.subp(adduser_cmd, logstring=x_adduser_cmd)

    except Exception as e:
        log.warn("Failed to create user %s due to error.\n%s" % user)


    # Double check to make sure that the user exists
    if not check_user(user):
        log.warn("User creation for %s failed for unknown reasons" % user)
        return False

    # unlock the password if so-user_configured
    if 'lock-passwd' not in user_config or \
        user_config['lock-passwd']:

        try:
            util.subp(['passwd', '-l', user])

        except Exception as e:
            log.warn("Failed to disable password logins for user %s\n%s" \
                   % (user, e))

    # write out sudo options
    if 'sudo' in user_config:
        write_sudo(user, user_config['sudo'], log)

    # import ssh id's from launchpad
    if 'ssh-import-id' in user_config:
        import_ssh_id(user, user_config['ssh-import-id'], log)

    # write ssh-authorized-keys
    if 'ssh-authorized-keys' in user_config:
        keys = set(user_config['ssh-authorized-keys']) or []
        user_home = pwd.getpwnam(user).pw_dir
        ssh_util.setup_user_keys(keys, user, None, cloud.paths)

def import_ssh_id(user, keys, log):

    if not os.path.exists('/usr/bin/ssh-import-id'):
	log.warn("ssh-import-id does not exist on this system, skipping")
	return

    cmd = ["sudo", "-Hu", user, "ssh-import-id"] + keys
    log.debug("Importing ssh ids for user %s.", user)

    try:
        util.subp(cmd, capture=False)

    except util.ProcessExecutionError as e:
        log.warn("Failed to run command to import %s ssh ids", user)
        log.warn(traceback.print_exc(e))


def write_sudo(user, rules, log):
    sudo_file = "/etc/sudoers.d/90-cloud-init-users"

    content = "%s %s" % (user, rules)
    if type(rules).__name__ == "list":
        content = ""
        for rule in rules:
            content += "%s %s\n" % (user, rule)

    if not os.path.exists(sudo_file):
        content = "# Added by cloud-init\n%s\n" % content
        util.write_file(sudo_file, content, 0644)

    else:
        old_content = None
        try:
            with open(sudo_file, 'r') as f:
                old_content = f.read()
            f.close()

        except IOError as e:
            log.warn("Failed to read %s, not adding sudo rules for %s" % \
                    (sudo_file, user))

        content = "%s\n\n%s" % (old_content, content)
        util.write_file(sudo_file, content, 0644)

def create_groups(groups, log):
    existing_groups = [x.gr_name for x in grp.getgrall()]
    existing_users = [x.pw_name for x in pwd.getpwall()]

    for group in groups:

        group_add_cmd = ['groupadd']
        group_name = None
        group_members = []

        if type(group).__name__ == "dict":
            group_name = [ x for x in group ][0]
            for user in group[group_name]:
                if user in existing_users:
                    group_members.append(user)
                else:
                    log.warn("Unable to add non-existant user '%s' to" \
                             " group '%s'" % (user, group_name))
        else:
            group_name = group
            group_add_cmd.append(group)

        group_add_cmd.append(group_name)

        # Check if group exists, and then add it doesn't
        if group_name in existing_groups:
            log.warn("Group '%s' already exists, skipping creation." % \
                    group_name)

        else:
            try:
                util.subp(group_add_cmd)
                log.info("Created new group %s" % group)

            except Exception as e:
                log.warn("Failed to create group %s\n%s" % (group, e))

        # Add members to the group, if so defined
        if len(group_members) > 0:
            for member in group_members:
                util.subp(['usermod', '-a', '-G', group_name, member])
                log.info("Added user '%s' to group '%s'" % (member, group))


