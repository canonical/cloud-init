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
from cloudinit import ssh_util
from cloudinit import util

from cloudinit.distros import net_util
from cloudinit.distros.parsers.resolv_conf import ResolvConf

from cloudinit.settings import PER_INSTANCE

LOG = logging.getLogger(__name__)


class Distro(distros.Distro):
    rc_conf_fn = "/etc/rc.conf"
    login_conf_fn = '/etc/login.conf'
    login_conf_fn_bak = '/etc/login.conf.orig'
    resolv_conf_fn = '/etc/resolv.conf'
    ci_sudoers_fn = '/usr/local/etc/sudoers.d/90-cloud-init-users'
    default_primary_nic = 'hn0'

    def __init__(self, name, cfg, paths):
        distros.Distro.__init__(self, name, cfg, paths)
        # This will be used to restrict certain
        # calls from repeatly happening (when they
        # should only happen say once per instance...)
        self._runner = helpers.Runners(paths)
        self.osfamily = 'freebsd'
        self.ipv4_pat = re.compile(r"\s+inet\s+\d+[.]\d+[.]\d+[.]\d+")
        cfg['ssh_svcname'] = 'sshd'

    # Updates a key in /etc/rc.conf.
    def updatercconf(self, key, value):
        LOG.debug("Checking %s for: %s = %s", self.rc_conf_fn, key, value)
        conf = self.loadrcconf()
        config_changed = False
        if key not in conf:
            LOG.debug("Adding key in %s: %s = %s", self.rc_conf_fn, key,
                      value)
            conf[key] = value
            config_changed = True
        else:
            for item in conf.keys():
                if item == key and conf[item] != value:
                    conf[item] = value
                    LOG.debug("Changing key in %s: %s = %s", self.rc_conf_fn,
                              key, value)
                    config_changed = True

        if config_changed:
            LOG.info("Writing %s", self.rc_conf_fn)
            buf = StringIO()
            for keyval in conf.items():
                buf.write('%s="%s"\n' % keyval)
            util.write_file(self.rc_conf_fn, buf.getvalue())

    # Load the contents of /etc/rc.conf and store all keys in a dict. Make sure
    # quotes are ignored:
    #  hostname="bla"
    def loadrcconf(self):
        RE_MATCH = re.compile(r'^(\w+)\s*=\s*(.*)\s*')
        conf = {}
        lines = util.load_file(self.rc_conf_fn).splitlines()
        for line in lines:
            m = RE_MATCH.match(line)
            if not m:
                LOG.debug("Skipping line from /etc/rc.conf: %s", line)
                continue
            key = m.group(1).rstrip()
            val = m.group(2).rstrip()
            # Kill them quotes (not completely correct, aka won't handle
            # quoted values, but should be ok ...)
            if val[0] in ('"', "'"):
                val = val[1:]
            if val[-1] in ('"', "'"):
                val = val[0:-1]
            if len(val) == 0:
                LOG.debug("Skipping empty value from /etc/rc.conf: %s", line)
                continue
            conf[key] = val
        return conf

    def readrcconf(self, key):
        conf = self.loadrcconf()
        try:
            val = conf[key]
        except KeyError:
            val = None
        return val

    # NOVA will inject something like eth0, rewrite that to use the FreeBSD
    # adapter. Since this adapter is based on the used driver, we need to
    # figure out which interfaces are available. On KVM platforms this is
    # vtnet0, where Xen would use xn0.
    def getnetifname(self, dev):
        LOG.debug("Translating network interface %s", dev)
        if dev.startswith('lo'):
            return dev

        n = re.search(r'\d+$', dev)
        index = n.group(0)

        (out, _err) = util.subp(['ifconfig', '-a'])
        ifconfigoutput = [x for x in (out.strip()).splitlines()
                          if len(x.split()) > 0]
        bsddev = 'NOT_FOUND'
        for line in ifconfigoutput:
            m = re.match(r'^\w+', line)
            if m:
                if m.group(0).startswith('lo'):
                    continue
                # Just settle with the first non-lo adapter we find, since it's
                # rather unlikely there will be multiple nicdrivers involved.
                bsddev = m.group(0)
                break

        # Replace the index with the one we're after.
        bsddev = re.sub(r'\d+$', index, bsddev)
        LOG.debug("Using network interface %s", bsddev)
        return bsddev

    def _select_hostname(self, hostname, fqdn):
        # Should be FQDN if available. See rc.conf(5) in FreeBSD
        if fqdn:
            return fqdn
        return hostname

    def _read_system_hostname(self):
        sys_hostname = self._read_hostname(filename=None)
        return ('rc.conf', sys_hostname)

    def _read_hostname(self, filename, default=None):
        hostname = None
        try:
            hostname = self.readrcconf('hostname')
        except IOError:
            pass
        if not hostname:
            return default
        return hostname

    def _write_hostname(self, hostname, filename):
        self.updatercconf('hostname', hostname)

    def create_group(self, name, members):
        group_add_cmd = ['pw', '-n', name]
        if util.is_group(name):
            LOG.warning("Skipping creation of existing group '%s'", name)
        else:
            try:
                util.subp(group_add_cmd)
                LOG.info("Created new group %s", name)
            except Exception as e:
                util.logexc(LOG, "Failed to create group %s", name)
                raise e

        if len(members) > 0:
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

        adduser_cmd = ['pw', 'useradd', '-n', name]
        log_adduser_cmd = ['pw', 'useradd', '-n', name]

        adduser_opts = {
            "homedir": '-d',
            "gecos": '-c',
            "primary_group": '-g',
            "groups": '-G',
            "shell": '-s',
            "inactive": '-E',
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
        # Set the password if it is provided
        # For security consideration, only hashed passwd is assumed
        passwd_val = kwargs.get('passwd', None)
        if passwd_val is not None:
            self.set_passwd(name, passwd_val, hashed=True)

    def set_passwd(self, user, passwd, hashed=False):
        if hashed:
            hash_opt = "-H"
        else:
            hash_opt = "-h"

        try:
            util.subp(['pw', 'usermod', user, hash_opt, '0'],
                      data=passwd, logstring="chpasswd for %s" % user)
        except Exception as e:
            util.logexc(LOG, "Failed to set password for %s", user)
            raise e

    def lock_passwd(self, name):
        try:
            util.subp(['pw', 'usermod', name, '-h', '-'])
        except Exception as e:
            util.logexc(LOG, "Failed to lock user %s", name)
            raise e

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

    @staticmethod
    def get_ifconfig_list():
        cmd = ['ifconfig', '-l']
        (nics, err) = util.subp(cmd, rcs=[0, 1])
        if len(err):
            LOG.warning("Error running %s: %s", cmd, err)
            return None
        return nics

    @staticmethod
    def get_ifconfig_ifname_out(ifname):
        cmd = ['ifconfig', ifname]
        (if_result, err) = util.subp(cmd, rcs=[0, 1])
        if len(err):
            LOG.warning("Error running %s: %s", cmd, err)
            return None
        return if_result

    @staticmethod
    def get_ifconfig_ether():
        cmd = ['ifconfig', '-l', 'ether']
        (nics, err) = util.subp(cmd, rcs=[0, 1])
        if len(err):
            LOG.warning("Error running %s: %s", cmd, err)
            return None
        return nics

    @staticmethod
    def get_interface_mac(ifname):
        if_result = Distro.get_ifconfig_ifname_out(ifname)
        for item in if_result.splitlines():
            if item.find('ether ') != -1:
                mac = str(item.split()[1])
                if mac:
                    return mac

    @staticmethod
    def get_devicelist():
        nics = Distro.get_ifconfig_list()
        return nics.split()

    @staticmethod
    def get_ipv6():
        ipv6 = []
        nics = Distro.get_devicelist()
        for nic in nics:
            if_result = Distro.get_ifconfig_ifname_out(nic)
            for item in if_result.splitlines():
                if item.find("inet6 ") != -1 and item.find("scopeid") == -1:
                    ipv6.append(nic)
        return ipv6

    def get_ipv4(self):
        ipv4 = []
        nics = Distro.get_devicelist()
        for nic in nics:
            if_result = Distro.get_ifconfig_ifname_out(nic)
            for item in if_result.splitlines():
                print(item)
                if self.ipv4_pat.match(item):
                    ipv4.append(nic)
        return ipv4

    def is_up(self, ifname):
        if_result = Distro.get_ifconfig_ifname_out(ifname)
        pat = "^" + ifname
        for item in if_result.splitlines():
            if re.match(pat, item):
                flags = item.split('<')[1].split('>')[0]
                if flags.find("UP") != -1:
                    return True

    def _get_current_rename_info(self, check_downable=True):
        """Collect information necessary for rename_interfaces."""
        names = Distro.get_devicelist()
        bymac = {}
        for n in names:
            bymac[Distro.get_interface_mac(n)] = {
                'name': n, 'up': self.is_up(n), 'downable': None}

        nics_with_addresses = set()
        if check_downable:
            nics_with_addresses = set(self.get_ipv4() + self.get_ipv6())

        for d in bymac.values():
            d['downable'] = (d['up'] is False or
                             d['name'] not in nics_with_addresses)

        return bymac

    def _rename_interfaces(self, renames):
        if not len(renames):
            LOG.debug("no interfaces to rename")
            return

        current_info = self._get_current_rename_info()

        cur_bymac = {}
        for mac, data in current_info.items():
            cur = data.copy()
            cur['mac'] = mac
            cur_bymac[mac] = cur

        def update_byname(bymac):
            return dict((data['name'], data)
                        for data in bymac.values())

        def rename(cur, new):
            util.subp(["ifconfig", cur, "name", new], capture=True)

        def down(name):
            util.subp(["ifconfig", name, "down"], capture=True)

        def up(name):
            util.subp(["ifconfig", name, "up"], capture=True)

        ops = []
        errors = []
        ups = []
        cur_byname = update_byname(cur_bymac)
        tmpname_fmt = "cirename%d"
        tmpi = -1

        for mac, new_name in renames:
            cur = cur_bymac.get(mac, {})
            cur_name = cur.get('name')
            cur_ops = []
            if cur_name == new_name:
                # nothing to do
                continue

            if not cur_name:
                errors.append("[nic not present] Cannot rename mac=%s to %s"
                              ", not available." % (mac, new_name))
                continue

            if cur['up']:
                msg = "[busy] Error renaming mac=%s from %s to %s"
                if not cur['downable']:
                    errors.append(msg % (mac, cur_name, new_name))
                    continue
                cur['up'] = False
                cur_ops.append(("down", mac, new_name, (cur_name,)))
                ups.append(("up", mac, new_name, (new_name,)))

            if new_name in cur_byname:
                target = cur_byname[new_name]
                if target['up']:
                    msg = "[busy-target] Error renaming mac=%s from %s to %s."
                    if not target['downable']:
                        errors.append(msg % (mac, cur_name, new_name))
                        continue
                    else:
                        cur_ops.append(("down", mac, new_name, (new_name,)))

                tmp_name = None
                while tmp_name is None or tmp_name in cur_byname:
                    tmpi += 1
                    tmp_name = tmpname_fmt % tmpi

                cur_ops.append(("rename", mac, new_name, (new_name, tmp_name)))
                target['name'] = tmp_name
                cur_byname = update_byname(cur_bymac)
                if target['up']:
                    ups.append(("up", mac, new_name, (tmp_name,)))

            cur_ops.append(("rename", mac, new_name, (cur['name'], new_name)))
            cur['name'] = new_name
            cur_byname = update_byname(cur_bymac)
            ops += cur_ops

        opmap = {'rename': rename, 'down': down, 'up': up}
        if len(ops) + len(ups) == 0:
            if len(errors):
                LOG.debug("unable to do any work for renaming of %s", renames)
            else:
                LOG.debug("no work necessary for renaming of %s", renames)
        else:
            LOG.debug("achieving renaming of %s with ops %s",
                      renames, ops + ups)

            for op, mac, new_name, params in ops + ups:
                try:
                    opmap.get(op)(*params)
                except Exception as e:
                    errors.append(
                        "[unknown] Error performing %s%s for %s, %s: %s" %
                        (op, params, mac, new_name, e))
        if len(errors):
            raise Exception('\n'.join(errors))

    def apply_network_config_names(self, netcfg):
        renames = []
        for ent in netcfg.get('config', {}):
            if ent.get('type') != 'physical':
                continue
            mac = ent.get('mac_address')
            name = ent.get('name')
            if not mac:
                continue
            renames.append([mac, name])
        return self._rename_interfaces(renames)

    @classmethod
    def generate_fallback_config(self):
        nics = Distro.get_ifconfig_ether()
        if nics is None:
            LOG.debug("Fail to get network interfaces")
            return None
        potential_interfaces = nics.split()
        connected = []
        for nic in potential_interfaces:
            pat = "^" + nic
            if_result = Distro.get_ifconfig_ifname_out(nic)
            for item in if_result.split("\n"):
                if re.match(pat, item):
                    flags = item.split('<')[1].split('>')[0]
                    if flags.find("RUNNING") != -1:
                        connected.append(nic)
        if connected:
            potential_interfaces = connected
        names = list(sorted(potential_interfaces))
        default_pri_nic = Distro.default_primary_nic
        if default_pri_nic in names:
            names.remove(default_pri_nic)
            names.insert(0, default_pri_nic)
        target_name = None
        target_mac = None
        for name in names:
            mac = Distro.get_interface_mac(name)
            if mac:
                target_name = name
                target_mac = mac
                break
        if target_mac and target_name:
            nconf = {'config': [], 'version': 1}
            nconf['config'].append(
                {'type': 'physical', 'name': target_name,
                 'mac_address': target_mac, 'subnets': [{'type': 'dhcp'}]})
            return nconf
        else:
            return None

    def _write_network(self, settings):
        entries = net_util.translate_network(settings)
        nameservers = []
        searchdomains = []
        dev_names = entries.keys()
        for (device, info) in entries.items():
            # Skip the loopback interface.
            if device.startswith('lo'):
                continue

            dev = self.getnetifname(device)

            LOG.info('Configuring interface %s', dev)

            if info.get('bootproto') == 'static':
                LOG.debug('Configuring dev %s with %s / %s', dev,
                          info.get('address'), info.get('netmask'))
                # Configure an ipv4 address.
                ifconfig = (info.get('address') + ' netmask ' +
                            info.get('netmask'))

                # Configure the gateway.
                self.updatercconf('defaultrouter', info.get('gateway'))

                if 'dns-nameservers' in info:
                    nameservers.extend(info['dns-nameservers'])
                if 'dns-search' in info:
                    searchdomains.extend(info['dns-search'])
            else:
                ifconfig = 'DHCP'

            self.updatercconf('ifconfig_' + dev, ifconfig)

        # Try to read the /etc/resolv.conf or just start from scratch if that
        # fails.
        try:
            resolvconf = ResolvConf(util.load_file(self.resolv_conf_fn))
            resolvconf.parse()
        except IOError:
            util.logexc(LOG, "Failed to parse %s, use new empty file",
                        self.resolv_conf_fn)
            resolvconf = ResolvConf('')
            resolvconf.parse()

        # Add some nameservers
        for server in nameservers:
            try:
                resolvconf.add_nameserver(server)
            except ValueError:
                util.logexc(LOG, "Failed to add nameserver %s", server)

        # And add any searchdomains.
        for domain in searchdomains:
            try:
                resolvconf.add_search_domain(domain)
            except ValueError:
                util.logexc(LOG, "Failed to add search domain %s", domain)
        util.write_file(self.resolv_conf_fn, str(resolvconf), 0o644)

        return dev_names

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

    def _bring_up_interface(self, device_name):
        if device_name.startswith('lo'):
            return
        dev = self.getnetifname(device_name)
        cmd = ['/etc/rc.d/netif', 'start', dev]
        LOG.debug("Attempting to bring up interface %s using command %s",
                  dev, cmd)
        # This could return 1 when the interface has already been put UP by the
        # OS. This is just fine.
        (_out, err) = util.subp(cmd, rcs=[0, 1])
        if len(err):
            LOG.warning("Error running %s: %s", cmd, err)

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
