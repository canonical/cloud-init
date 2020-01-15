# Copyright (C) 2014 Harm Weites
#
# Author: Harm Weites <harm@weites.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import os
import six
from six import StringIO

import re

from cloudinit import distros
from cloudinit import helpers
from cloudinit import log as logging
from cloudinit import net
from cloudinit import ssh_util
from cloudinit import util
from cloudinit.distros import rhel_util
from cloudinit.settings import PER_INSTANCE

LOG = logging.getLogger(__name__)


class Distro(distros.Distro):
    usr_lib_exec = '/usr/local/lib'
    rc_conf_fn = "/etc/rc.conf"
    login_conf_fn = '/etc/login.conf'
    login_conf_fn_bak = '/etc/login.conf.orig'
    ci_sudoers_fn = '/usr/local/etc/sudoers.d/90-cloud-init-users'
    hostname_conf_fn = '/etc/rc.conf'

    def __init__(self, name, cfg, paths):
        distros.Distro.__init__(self, name, cfg, paths)
        # This will be used to restrict certain
        # calls from repeatly happening (when they
        # should only happen say once per instance...)
        self._runner = helpers.Runners(paths)
        self.osfamily = 'freebsd'
        cfg['ssh_svcname'] = 'sshd'

    def _select_hostname(self, hostname, fqdn):
        # Should be FQDN if available. See rc.conf(5) in FreeBSD
        if fqdn:
            return fqdn
        return hostname

    def _read_system_hostname(self):
        sys_hostname = self._read_hostname(self.hostname_conf_fn)
        return (self.hostname_conf_fn, sys_hostname)

    def _read_hostname(self, filename, default=None):
        (_exists, contents) = rhel_util.read_sysconfig_file(filename)
        if contents.get('hostname'):
            return contents['hostname']
        else:
            return default

    def _write_hostname(self, hostname, filename):
        rhel_util.update_sysconfig_file(filename, {'hostname': hostname})

    def create_group(self, name, members):
        group_add_cmd = ['pw', 'group', 'add', name]
        if util.is_group(name):
            LOG.warning("Skipping creation of existing group '%s'", name)
        else:
            try:
                util.subp(group_add_cmd)
                LOG.info("Created new group %s", name)
            except Exception:
                util.logexc(LOG, "Failed to create group %s", name)
                raise
        if not members:
            members = []

        for member in members:
            if not util.is_user(member):
                LOG.warning("Unable to add group member '%s' to group '%s'"
                            "; user does not exist.", member, name)
                continue
            try:
                util.subp(['pw', 'usermod', '-n', name, '-G', member])
                LOG.info("Added user '%s' to group '%s'", member, name)
            except Exception:
                util.logexc(LOG, "Failed to add user '%s' to group '%s'",
                            member, name)

    def add_user(self, name, **kwargs):
        if util.is_user(name):
            LOG.info("User %s already exists, skipping.", name)
            return False

        pw_useradd_cmd = ['pw', 'useradd', '-n', name]
        log_pw_useradd_cmd = ['pw', 'useradd', '-n', name]

        pw_useradd_opts = {
            "homedir": '-d',
            "gecos": '-c',
            "primary_group": '-g',
            "groups": '-G',
            "shell": '-s',
            "inactive": '-E',
        }
        pw_useradd_flags = {
            "no_user_group": '--no-user-group',
            "system": '--system',
            "no_log_init": '--no-log-init',
        }

        for key, val in kwargs.items():
            if (key in pw_useradd_opts and val and
               isinstance(val, six.string_types)):
                pw_useradd_cmd.extend([pw_useradd_opts[key], val])

            elif key in pw_useradd_flags and val:
                pw_useradd_cmd.append(pw_useradd_flags[key])
                log_pw_useradd_cmd.append(pw_useradd_flags[key])

        if 'no_create_home' in kwargs or 'system' in kwargs:
            pw_useradd_cmd.append('-d/nonexistent')
            log_pw_useradd_cmd.append('-d/nonexistent')
        else:
            pw_useradd_cmd.append('-d/usr/home/%s' % name)
            pw_useradd_cmd.append('-m')
            log_pw_useradd_cmd.append('-d/usr/home/%s' % name)
            log_pw_useradd_cmd.append('-m')

        # Run the command
        LOG.info("Adding user %s", name)
        try:
            util.subp(pw_useradd_cmd, logstring=log_pw_useradd_cmd)
        except Exception:
            util.logexc(LOG, "Failed to create user %s", name)
            raise
        # Set the password if it is provided
        # For security consideration, only hashed passwd is assumed
        passwd_val = kwargs.get('passwd', None)
        if passwd_val is not None:
            self.set_passwd(name, passwd_val, hashed=True)

    def expire_passwd(self, user):
        try:
            util.subp(['pw', 'usermod', user, '-p', '01-Jan-1970'])
        except Exception:
            util.logexc(LOG, "Failed to set pw expiration for %s", user)
            raise

    def set_passwd(self, user, passwd, hashed=False):
        if hashed:
            hash_opt = "-H"
        else:
            hash_opt = "-h"

        try:
            util.subp(['pw', 'usermod', user, hash_opt, '0'],
                      data=passwd, logstring="chpasswd for %s" % user)
        except Exception:
            util.logexc(LOG, "Failed to set password for %s", user)
            raise

    def lock_passwd(self, name):
        try:
            util.subp(['pw', 'usermod', name, '-h', '-'])
        except Exception:
            util.logexc(LOG, "Failed to lock user %s", name)
            raise

    def create_user(self, name, **kwargs):
        self.add_user(name, **kwargs)

        # Set password if plain-text password provided and non-empty
        if 'plain_text_passwd' in kwargs and kwargs['plain_text_passwd']:
            self.set_passwd(name, kwargs['plain_text_passwd'])

        # Default locking down the account. 'lock_passwd' defaults to True.
        # lock account unless lock_password is False.
        if kwargs.get('lock_passwd', True):
            self.lock_passwd(name)

        # Configure sudo access
        if 'sudo' in kwargs and kwargs['sudo'] is not False:
            self.write_sudo_rules(name, kwargs['sudo'])

        # Import SSH keys
        if 'ssh_authorized_keys' in kwargs:
            keys = set(kwargs['ssh_authorized_keys']) or []
            ssh_util.setup_user_keys(keys, name, options=None)

    def generate_fallback_config(self):
        nconf = {'config': [], 'version': 1}
        for mac, name in net.get_interfaces_by_mac().items():
            nconf['config'].append(
                {'type': 'physical', 'name': name,
                 'mac_address': mac, 'subnets': [{'type': 'dhcp'}]})
        return nconf

    def _write_network_config(self, netconfig):
        return self._supported_write_network_config(netconfig)

    def apply_locale(self, locale, out_fn=None):
        # Adjust the locals value to the new value
        newconf = StringIO()
        for line in util.load_file(self.login_conf_fn).splitlines():
            newconf.write(re.sub(r'^default:',
                                 r'default:lang=%s:' % locale, line))
            newconf.write("\n")

        # Make a backup of login.conf.
        util.copy(self.login_conf_fn, self.login_conf_fn_bak)

        # And write the new login.conf.
        util.write_file(self.login_conf_fn, newconf.getvalue())

        try:
            LOG.debug("Running cap_mkdb for %s", locale)
            util.subp(['cap_mkdb', self.login_conf_fn])
        except util.ProcessExecutionError:
            # cap_mkdb failed, so restore the backup.
            util.logexc(LOG, "Failed to apply locale %s", locale)
            try:
                util.copy(self.login_conf_fn_bak, self.login_conf_fn)
            except IOError:
                util.logexc(LOG, "Failed to restore %s backup",
                            self.login_conf_fn)

    def apply_network_config_names(self, netconfig):
        # This is handled by the freebsd network renderer. It writes in
        # /etc/rc.conf a line with the following format:
        #    ifconfig_OLDNAME_name=NEWNAME
        # FreeBSD network script will rename the interface automatically.
        return

    def install_packages(self, pkglist):
        self.update_package_sources()
        self.package_command('install', pkgs=pkglist)

    def package_command(self, command, args=None, pkgs=None):
        if pkgs is None:
            pkgs = []

        e = os.environ.copy()
        e['ASSUME_ALWAYS_YES'] = 'YES'

        cmd = ['pkg']
        if args and isinstance(args, str):
            cmd.append(args)
        elif args and isinstance(args, list):
            cmd.extend(args)

        if command:
            cmd.append(command)

        pkglist = util.expand_package_list('%s-%s', pkgs)
        cmd.extend(pkglist)

        # Allow the output of this to flow outwards (ie not be captured)
        util.subp(cmd, env=e, capture=False)

    def set_timezone(self, tz):
        distros.set_etc_timezone(tz=tz, tz_file=self._find_tz_file(tz))

    def update_package_sources(self):
        self._runner.run("update-sources", self.package_command,
                         ["update"], freq=PER_INSTANCE)

# vi: ts=4 expandtab
