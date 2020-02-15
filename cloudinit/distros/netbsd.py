# Copyright (C) 2019-2020 Gonéri Le Bouder
#
# This file is part of cloud-init. See LICENSE file for license information.

import crypt
import os
import platform
import six

import cloudinit.distros.bsd
from cloudinit import log as logging
from cloudinit import util

LOG = logging.getLogger(__name__)


class Distro(cloudinit.distros.bsd.BSD):
    ci_sudoers_fn = '/usr/pkg/etc/sudoers.d/90-cloud-init-users'

    def create_group(self, name, members=None):
        group_add_cmd = ['groupadd', name]
        if util.is_group(name):
            LOG.warning("Skipping creation of existing group '%s'", name)
        else:
            try:
                util.subp(group_add_cmd)
                LOG.info("Created new group %s", name)
            except Exception:
                util.logexc(LOG, "Failed to create group %s", name)

        if not members:
            members = []
        for member in members:
            if not util.is_user(member):
                LOG.warning("Unable to add group member '%s' to group '%s'"
                            "; user does not exist.", member, name)
                continue
            try:
                util.subp(['usermod', '-G', name, member])
                LOG.info("Added user '%s' to group '%s'", member, name)
            except Exception:
                util.logexc(LOG, "Failed to add user '%s' to group '%s'",
                            member, name)

    def add_user(self, name, **kwargs):
        if util.is_user(name):
            LOG.info("User %s already exists, skipping.", name)
            return False

        adduser_cmd = ['useradd']
        log_adduser_cmd = ['useradd']

        adduser_opts = {
            "homedir": '-d',
            "gecos": '-c',
            "primary_group": '-g',
            "groups": '-G',
            "shell": '-s',
        }
        adduser_flags = {
            "no_user_group": '--no-user-group',
            "system": '--system',
            "no_log_init": '--no-log-init',
        }

        for key, val in kwargs.items():
            if (key in adduser_opts and val and
               isinstance(val, six.string_types)):
                adduser_cmd.extend([adduser_opts[key], val])

            elif key in adduser_flags and val:
                adduser_cmd.append(adduser_flags[key])
                log_adduser_cmd.append(adduser_flags[key])

        if 'no_create_home' not in kwargs or 'system' not in kwargs:
            adduser_cmd += ['-m']
            log_adduser_cmd += ['-m']

        adduser_cmd += [name]
        log_adduser_cmd += [name]

        # Run the command
        LOG.info("Adding user %s", name)
        try:
            util.subp(adduser_cmd, logstring=log_adduser_cmd)
        except Exception:
            util.logexc(LOG, "Failed to create user %s", name)
            raise
        # Set the password if it is provided
        # For security consideration, only hashed passwd is assumed
        passwd_val = kwargs.get('passwd', None)
        if passwd_val is not None:
            self.set_passwd(name, passwd_val, hashed=True)

    def set_passwd(self, user, password, hashed=False):
        if hashed:
            hashed_pw = password
        elif not hasattr(crypt, 'METHOD_BLOWFISH'):
            # crypt.METHOD_BLOWFISH comes with Python 3.7 which is available
            # on NetBSD 7 and 8.
            LOG.error((
                'Cannot set non-encrypted password for user %s. '
                'Python >= 3.7 is required.'), user)
            return
        else:
            method = crypt.METHOD_BLOWFISH  # pylint: disable=E1101
            hashed_pw = crypt.crypt(
                    password,
                    crypt.mksalt(method))

        try:
            util.subp(['usermod', '-C', 'no', '-p', hashed_pw, user])
        except Exception:
            util.logexc(LOG, "Failed to set password for %s", user)
            raise

    def force_passwd_change(self, user):
        try:
            util.subp(['usermod', '-F', user])
        except Exception:
            util.logexc(LOG, "Failed to set pw expiration for %s", user)
            raise

    def lock_passwd(self, name):
        try:
            util.subp(['usermod', '-C', 'yes', name])
        except Exception:
            util.logexc(LOG, "Failed to lock user %s", name)
            raise

    def apply_locale(self, locale, out_fn=None):
        LOG.debug('Cannot set the locale.')

    def apply_network_config_names(self, netconfig):
        LOG.debug('NetBSD cannot rename network interface.')
        return

    def install_packages(self, pkglist):
        self.package_command('install', pkgs=pkglist)

    def package_command(self, command, args=None, pkgs=None):
        if pkgs is None:
            pkgs = []

        os_release = platform.release()
        os_arch = platform.machine()
        e = os.environ.copy()
        e['PKG_PATH'] = (
                'http://cdn.netbsd.org/pub/pkgsrc/'
                'packages/NetBSD/%s/%s/All') % (os_arch, os_release)

        if command == 'install':
            cmd = ['pkg_add', '-U']
        elif command == 'remove':
            cmd = ['pkg_delete']
        if args and isinstance(args, str):
            cmd.append(args)
        elif args and isinstance(args, list):
            cmd.extend(args)

        pkglist = util.expand_package_list('%s-%s', pkgs)
        cmd.extend(pkglist)

        # Allow the output of this to flow outwards (ie not be captured)
        util.subp(cmd, env=e, capture=False)

    def update_package_sources(self):
        pass


# vi: ts=4 expandtab
