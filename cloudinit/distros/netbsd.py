# Copyright (C) 2019-2020 Gonéri Le Bouder
#
# This file is part of cloud-init. See LICENSE file for license information.

import crypt
import os
import platform

import cloudinit.distros.bsd
from cloudinit import log as logging
from cloudinit import subp
from cloudinit import util

LOG = logging.getLogger(__name__)


class NetBSD(cloudinit.distros.bsd.BSD):
    """
    Distro subclass for NetBSD.

    (N.B. OpenBSD inherits from this class.)
    """

    ci_sudoers_fn = '/usr/pkg/etc/sudoers.d/90-cloud-init-users'
    group_add_cmd_prefix = ["groupadd"]

    def __init__(self, name, cfg, paths):
        super().__init__(name, cfg, paths)
        if os.path.exists("/usr/pkg/bin/pkgin"):
            self.pkg_cmd_install_prefix = ['pkgin', '-y', 'install']
            self.pkg_cmd_remove_prefix = ['pkgin', '-y', 'remove']
            self.pkg_cmd_update_prefix = ['pkgin', '-y', 'update']
            self.pkg_cmd_upgrade_prefix = ['pkgin', '-y', 'full-upgrade']
        else:
            self.pkg_cmd_install_prefix = ['pkg_add', '-U']
            self.pkg_cmd_remove_prefix = ['pkg_delete']

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
            if key in adduser_opts and val and isinstance(val, str):
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
            subp.subp(adduser_cmd, logstring=log_adduser_cmd)
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
            # crypt.METHOD_BLOWFISH comes with Python 3.7 which is available
            # on NetBSD 7 and 8.
            LOG.error((
                'Cannot set non-encrypted password for user %s. '
                'Python >= 3.7 is required.'), user)
            return
        else:
            method = crypt.METHOD_BLOWFISH  # pylint: disable=E1101
            hashed_pw = crypt.crypt(
                passwd,
                crypt.mksalt(method)
            )

        try:
            subp.subp(['usermod', '-p', hashed_pw, user])
        except Exception:
            util.logexc(LOG, "Failed to set password for %s", user)
            raise
        self.unlock_passwd(user)

    def force_passwd_change(self, user):
        try:
            subp.subp(['usermod', '-F', user])
        except Exception:
            util.logexc(LOG, "Failed to set pw expiration for %s", user)
            raise

    def lock_passwd(self, name):
        try:
            subp.subp(['usermod', '-C', 'yes', name])
        except Exception:
            util.logexc(LOG, "Failed to lock user %s", name)
            raise

    def unlock_passwd(self, name):
        try:
            subp.subp(['usermod', '-C', 'no', name])
        except Exception:
            util.logexc(LOG, "Failed to unlock user %s", name)
            raise

    def apply_locale(self, locale, out_fn=None):
        LOG.debug('Cannot set the locale.')

    def apply_network_config_names(self, netconfig):
        LOG.debug('NetBSD cannot rename network interface.')

    def _get_pkg_cmd_environ(self):
        """Return env vars used in NetBSD package_command operations"""
        os_release = platform.release()
        os_arch = platform.machine()
        e = os.environ.copy()
        e['PKG_PATH'] = (
            'http://cdn.netbsd.org/pub/pkgsrc/'
            'packages/NetBSD/%s/%s/All'
        ) % (os_arch, os_release)
        return e

    def update_package_sources(self):
        pass


class Distro(NetBSD):
    pass

# vi: ts=4 expandtab
