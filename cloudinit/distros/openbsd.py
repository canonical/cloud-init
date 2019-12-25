# Copyright (C) 2019-2020 Gonéri Le Bouder
#
# This file is part of cloud-init. See LICENSE file for license information.

import crypt
import os
import platform

import cloudinit.distros.bsd
from cloudinit import log as logging
from cloudinit import util

LOG = logging.getLogger(__name__)


class Distro(cloudinit.distros.bsd.BSD):
    hostname_conf_fn = '/etc/myname'
    ci_sudoers_fn = '/usr/pkg/etc/sudoers.d/90-cloud-init-users'
    group_add_cmd_prefix = ["groupadd"]
    pkg_cmd_install_prefix = ["pkg_add", "-U"]
    pkg_cmd_remove_prefix = ['pkg_delete']

    def _read_hostname(self, filename, default=None):
        with open(self.hostname_conf_fn, 'r') as fd:
            return fd.read()

    def _write_hostname(self, hostname, filename):
        content = hostname + '\n'
        util.write_file(self.hostname_conf_fn, content)

    def _get_add_member_to_group_cmd(self, member_name, group_name):
        return ['usermod', '-G', group_name, member_name]

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
               isinstance(val, str)):
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

    def set_passwd(self, user, passwd, hashed=False):
        if hashed:
            hashed_pw = passwd
        elif not hasattr(crypt, 'METHOD_BLOWFISH'):
            # crypt.METHOD_BLOWFISH comes with Python 3.7
            LOG.error((
                'Cannot set non-encrypted password for user %s. '
                'Python >= 3.7 is required.'), user)
            return
        else:
            method = crypt.METHOD_BLOWFISH  # pylint: disable=E1101
            hashed_pw = crypt.crypt(
                    passwd,
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
            util.subp(['usermod', '-p', '*', name])
        except Exception:
            util.logexc(LOG, "Failed to lock user %s", name)
            raise

    def package_command(self, command, args=None, pkgs=None):
        if pkgs is None:
            pkgs = []

        os_release = platform.release()
        os_arch = platform.machine()
        e = os.environ.copy()
        e['PKG_PATH'] = (
                'ftp://ftp.openbsd.org/pub/OpenBSD/{os_release}/'
                'packages/{os_arch}/').format(
                        os_arch=os_arch, os_release=os_release)

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
