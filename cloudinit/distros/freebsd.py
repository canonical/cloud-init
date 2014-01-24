# vi: ts=4 expandtab
#
#    Copyright (C) 2014 Harm Weites
#
#    Author: Harm Weites <harm@weites.com>
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
from cloudinit import helpers
from cloudinit import log as logging
from cloudinit import netinfo
from cloudinit import ssh_util
from cloudinit import util

from cloudinit.settings import PER_INSTANCE

LOG = logging.getLogger(__name__)


class Distro(distros.Distro):
    def __init__(self, name, cfg, paths):
        distros.Distro.__init__(self, name, cfg, paths)
        # This will be used to restrict certain
        # calls from repeatly happening (when they
        # should only happen say once per instance...)
        self._runner = helpers.Runners(paths)
        self.osfamily = 'freebsd'

    # Updates a key in /etc/rc.conf.
    def updatercconf(self, key, value):
        LOG.debug("updatercconf: %s => %s" % (key, value))
        conf = self.loadrcconf()
        configchanged = False
        for item in conf:
            if item == key and conf[item] != value:
                conf[item] = value
                LOG.debug("[rc.conf]: Value %s for key %s needs to be changed" % (value, key))
                configchanged = True

        if configchanged:
            LOG.debug("Writing new /etc/rc.conf file")
            with open('/etc/rc.conf', 'w') as file:
                for keyval in conf.items():
                    file.write("%s=%s\n" % keyval)

    # Load the contents of /etc/rc.conf and store all keys in a dict.
    def loadrcconf(self):
        conf = {}
        with open("/etc/rc.conf") as file:
            for line in file:
                tok = line.split('=')
                conf[tok[0]] = tok[1].rstrip()
        return conf

    def readrcconf(self, key):
        conf = self.loadrcconf()
        try:
            val = conf[key]
        except KeyError:
            val = None
        return val

    def _read_system_hostname(self):
        sys_hostname = self._read_hostname()
        return ('rc.conf', sys_hostname)

    def _read_hostname(self, default=None):
        hostname = None
        try:
            hostname = self.readrcconf('hostname')
        except IOError:
            pass
        if not hostname:
            return default
        return hostname

    def _select_hostname(self, hostname, fqdn):
        if not hostname:
            return fqdn
        return hostname

    def _write_hostname(self, your_hostname, out_fn):
        self.updatercconf('hostname', your_hostname)

    def create_group(self, name, members):
        group_add_cmd = ['pw', '-n', name]
        if util.is_group(name):
            LOG.warn("Skipping creation of existing group '%s'" % name)
        else:
            try:
                util.subp(group_add_cmd)
                LOG.info("Created new group %s" % name)
            except Exception:
                util.logexc("Failed to create group %s", name)

        if len(members) > 0:
            for member in members:
                if not util.is_user(member):
                    LOG.warn("Unable to add group member '%s' to group '%s'"
                                     "; user does not exist.", member, name)
                    continue
                util.subp(['pw', 'usermod', '-n', name, '-G', member])
                LOG.info("Added user '%s' to group '%s'" % (member, name))

    def add_user(self, name, **kwargs):
        if util.is_user(name):
            LOG.info("User %s already exists, skipping." % name)
            return False

        adduser_cmd = ['pw', 'useradd', '-n', name]
        log_adduser_cmd = ['pw', 'useradd', '-n', name]

        adduser_opts = {
                "homedir": '-d',
                "gecos": '-c',
                "primary_group": '-g',
                "groups": '-G',
                "passwd": '-h',
                "shell": '-s',
                "inactive": '-E',
        }
        adduser_flags = {
                "no_user_group": '--no-user-group',
                "system": '--system',
                "no_log_init": '--no-log-init',
        }

        redact_opts = ['passwd']

        for key, val in kwargs.iteritems():
            if key in adduser_opts and val and isinstance(val, str):
                adduser_cmd.extend([adduser_opts[key], val])

                # Redact certain fields from the logs
                if key in redact_opts:
                    log_adduser_cmd.extend([adduser_opts[key], 'REDACTED'])
                else:
                    log_adduser_cmd.extend([adduser_opts[key], val])

            elif key in adduser_flags and val:
                adduser_cmd.append(adduser_flags[key])
                log_adduser_cmd.append(adduser_flags[key])

        if 'no_create_home' in kwargs or 'system' in kwargs:
            adduser_cmd.append('-d/nonexistent')
            log_adduser_cmd.append('-d/nonexistent')
        else:
            adduser_cmd.append('-d/usr/home/%s' % name)
            adduser_cmd.append('-m')
            log_adduser_cmd.append('-d/usr/home/%s' % name)
            log_adduser_cmd.append('-m')

        # Run the command
        LOG.info("Adding user %s", name)
        try:
            util.subp(adduser_cmd, logstring=log_adduser_cmd)
        except Exception as e:
            util.logexc(LOG, "Failed to create user %s", name)
            raise e

    # TODO:
    def set_passwd(self, name, **kwargs):
        return False

    def lock_passwd(self, name):
        try:
            util.subp(['pw', 'usermod', name, '-h', '-'])
        except Exception as e:
            util.logexc(LOG, "Failed to lock user %s", name)
            raise e

    # TODO:
    def write_sudo_rules(self, name, rules, sudo_file=None):
        LOG.debug("[write_sudo_rules] Name: %s" % name)

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
        if 'sudo' in kwargs:
            self.write_sudo_rules(name, kwargs['sudo'])

        # Import SSH keys
        if 'ssh_authorized_keys' in kwargs:
            keys = set(kwargs['ssh_authorized_keys']) or []
            ssh_util.setup_user_keys(keys, name, options=None)

    def _write_network(self, settings):
        return

    def apply_locale(self, locale, out_fn=None):
        loginconf = '/etc/login.conf'
        newloginconf = '/tmp/login.conf.new'
        backupconf = '/etc/login.conf.orig'

        newconf = open(newloginconf, 'w')
        origconf = open(loginconf, 'r')

        for line in origconf:
            newconf.write(re.sub('^default:', r'default:lang=%s:' % locale, line))
        newconf.close()
        origconf.close()
        # Make a backup of login.conf.
        copyfile(loginconf, backupconf)
        # And copy the new login.conf.
        copyfile(newloginconf, loginconf)

        try:
            util.logexc("Running cap_mkdb for %s", locale)
            util.subp(['cap_mkdb', '/etc/login.conf'])
        except:
            # cap_mkdb failed, so restore the backup.
            util.logexc("Failed to apply locale %s", locale)
            copyfile(backupconf, loginconf)

    def install_packages():
        return

    def package_command():
        return

    def set_timezone():
        return

    def update_package_sources():
        return
