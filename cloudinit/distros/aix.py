# vi: ts=4 expandtab
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

import time
import subprocess
from cloudinit import distros
from cloudinit import helpers
from cloudinit import log as logging
from cloudinit import util, subp
from cloudinit import ssh_util

from cloudinit.distros import net_util
from cloudinit.distros import rhel_util
from cloudinit.distros import aix_util
from cloudinit.settings import PER_INSTANCE

from cloudinit.distros.parsers.hostname import HostnameConf
from cloudinit.distros.networking import AIXNetworking

LOG = logging.getLogger(__name__)


class Distro(distros.Distro):
    hostname_conf_fn = "/etc/hosts"
    resolve_conf_fn = "/etc/resolv.conf"
    networking_cls = AIXNetworking

    def __init__(self, name, cfg, paths):
        distros.Distro.__init__(self, name, cfg, paths)
        # This will be used to restrict certain
        # calls from repeatly happening (when they
        # should only happen say once per instance...)
        self._runner = helpers.Runners(paths)
        self.osfamily = "aix"

    def install_packages(self, pkglist):
        self.package_command("install", pkgs=pkglist)

    def apply_network(self, settings, bring_up=True):
        # Write it out
        dev_names = self._write_network(settings)
        LOG.debug("AIX: always bring up interfaces %s", dev_names)
        self._bring_down_interfaces(dev_names)
        return self._bring_up_interfaces(dev_names)

    def apply_network_config_names(self, netconfig):
        LOG.debug("AIX does not rename network interface, netconfig=%s", netconfig)

    def _write_network_state(self, settings):
        raise NotImplementedError()

    def _write_network(self, settings):
        print("aix.py _write_network settings=%s" % settings)
        entries = net_util.translate_network(settings)
        aix_util.remove_resolve_conf_file(self.resolve_conf_fn)
        print("Translated ubuntu style network settings %s into %s" % (settings, entries))

        # Make the intermediate format as the rhel format...
        nameservers = []
        searchservers = []
        dev_names = list(entries.keys())
        create_dhcp_file = True
        run_dhcpcd = False
        run_autoconf6 = False
        ipv6_interface = None

        # First, make sure the services starts out uncommented in /etc/rc.tcpip 
        aix_util.disable_dhcpcd()
        aix_util.disable_ndpd_host()
        aix_util.disable_autoconf6()

        # Remove the chdev ipv6 entries present in the /etc/rc.tcpip from earlier runs.
        # Read the content of the file and filter out lines containing both words
        with open('/etc/rc.tcpip', "r") as infile:
            lines = [line for line in infile if "chdev" not in line and "anetaddr6" not in line and "cloud-init" not in line]

        # Write the filtered lines back to the file
        with open('/etc/rc.tcpip', "w") as outfile:
            outfile.writelines(lines)

        for (dev, info) in list(entries.items()):
            print("dev %s info %s" % (dev, info))

        for (dev, info) in list(entries.items()):
            run_cmd = 0
            ipv6_present = 0
            chdev_cmd = ['/usr/sbin/chdev']

            if dev not in 'lo':
                aix_dev = aix_util.translate_devname(dev)
                print("dev %s aix_dev %s" % (dev, aix_dev))
                if info.get('bootproto') == 'dhcp':
                    aix_util.config_dhcp(aix_dev, info, create_dhcp_file)
                    create_dhcp_file = False
                    run_dhcpcd = True
                else:
                    chdev_cmd.extend(['-l', aix_dev])

                    ipv6_info = info.get("ipv6")
                    if ipv6_info is not None and len(ipv6_info) > 0:
                        run_cmd = 1
                        ipv6_present = 1
                        run_autoconf6 = True
                        ipv6_address = ipv6_info.get("address")
                        ipv6_netmask = ipv6_info.get("netmask")
                        if ipv6_address is not None:
                            ipv6_addr = ipv6_address.split('/')
                            chdev_cmd.append('-anetaddr6=' + ipv6_addr[0])
                        if ipv6_netmask is not None:
                            chdev_cmd.append('-aprefixlen=' + ipv6_netmask)

                        if ipv6_interface is None:
                            ipv6_interface = aix_dev
                        else:
                            ipv6_interface = "any"

                    else:
                        run_cmd = 1
                        ipv6_present = 0
                        ipv4_address = info.get("address")
                        ipv4_netmask = info.get("netmask")
                        if ipv4_address is not None:
                            chdev_cmd.append('-anetaddr=' + ipv4_address)
                        if ipv4_netmask is not None:
                            chdev_cmd.append('-anetmask=' + ipv4_netmask)
                            
                    if run_autoconf6:
                         command = "/usr/sbin/autoconf6 -i en0"
                         output = subprocess.check_output(command, shell=True, stderr=subprocess.STDOUT, universal_newlines=True)
                         time.sleep(2)
                         command = "stopsrc -s ndpd-host ; sleep 3 ; startsrc -s ndpd-host ;"
                         output = subprocess.check_output(command, shell=True, stderr=subprocess.STDOUT, universal_newlines=True)

                    if run_cmd:
                        try:
                            print("running ", chdev_cmd)
                            subp.subp(chdev_cmd, logstring=chdev_cmd)
                            time.sleep(2)

                            if ipv6_present:
                                util.append_file("/etc/rc.tcpip", "%s\n" % (" ".join(chdev_cmd)))
                            
                        except Exception as e:
                            raise e

                        if 'mtu' in info:
                            if info['mtu'] > 1500:
                                subp.subp(["/etc/ifconfig", aix_dev, "down", "detach"], capture=False, rcs=[0, 1])
                                time.sleep(2)
                                aix_adapter = aix_util.logical_adpt_name(aix_dev)
                                subp.subp(["/usr/sbin/chdev", "-l", aix_adapter, "-ajumbo_frames=yes"], capture=False, rcs=[0, 1])
                                time.sleep(2)
                            subp.subp(["/usr/sbin/chdev", "-l", aix_dev, "-amtu=" + info['mtu']], capture=False, rcs=[0, 1])
                            time.sleep(2)
                        if aix_dev == "en0":
                            if run_autoconf6 is True:
                                aix_util.add_route("ipv6", ipv6_info.get('gateway'))
                                #aix_util.disable_ndpd_host()
                                #aix_util.enable_ndpd_host()
                                util.append_file("/etc/rc.tcpip", "%s\n" % ("stopsrc -s ndpd-host ; sleep 3 ; startsrc -s ndpd-host ; #To remove default gateway for cloud-init "))
                                util.append_file("/etc/rc.tcpip", "%s\n" % (" ".join(chdev_cmd)))
                            else:
                                aix_util.add_route("ipv4", info.get('gateway'))

            if 'dns-nameservers' in info:
                nameservers.extend(info['dns-nameservers'])
            if 'dns-search' in info:
                searchservers.extend(info['dns-search'])

        if run_dhcpcd:
            aix_util.enable_dhcpcd()
        if run_autoconf6:
            aix_util.enable_ndpd_host()
            aix_util.enable_autoconf6(ipv6_interface)

        if ((nameservers and len(nameservers) > 0) or (
            searchservers and len(searchservers) > 0)):
            aix_util.update_resolve_conf_file(self.resolve_conf_fn, nameservers, searchservers)
        print("returning ", dev_names)
        return dev_names

    def apply_locale(self, locale, out_fn=None):
        subp.subp(["/usr/bin/chlang", "-M", str(locale)])

    def _write_hostname(self, hostname, out_fn):
        # Permanently change the hostname for inet0 device in the ODM
        subp.subp(["/usr/sbin/chdev", "-l", "inet0", "-a", "hostname=" + str(hostname)])

        shortname = hostname.split('.')[0]
        # Change the node for the uname process
        subp.subp(["/usr/bin/uname", "-S", str(shortname)[0:32]])

    def _read_system_hostname(self):
        host_fn = self.hostname_conf_fn
        return (host_fn, self._read_hostname(host_fn))

    def _read_hostname(self, filename, default=None):
        (out, _err) = subp.subp(["/usr/bin/hostname"])
        if len(out):
            return out
        else:
            return default

    def _bring_up_interface(self, device_name):
        if device_name in 'lo':
            return True

        cmd = ["/usr/sbin/chdev", "-l", aix_util.translate_devname(device_name), "-a", "state=up"]
        LOG.debug("Attempting to run bring up interface %s using command %s", device_name, cmd)
        try:
            (_out, err) = subp.subp(cmd)
            time.sleep(1)
            if len(err):
                LOG.warn("Running %s resulted in stderr output: %s", cmd, err)
            return True
        except subp.ProcessExecutionError:
            util.logexc(LOG, "Running interface command %s failed", cmd)
            return False

    def _bring_up_interfaces(self, device_names):
        if device_names and 'all' in device_names:
            raise RuntimeError(('Distro %s can not translate the device name "all"') % (self.name))
        for d in device_names:
            if not self._bring_up_interface(d):
                return False
        return True

    def _bring_down_interface(self, device_name):
        if device_name in 'lo':
            return True

        interface = aix_util.translate_devname(device_name)
        LOG.debug("Attempting to run bring down interface %s device_name %s", interface, device_name)
        if aix_util.get_if_attr(interface, "state") == "down":
            time.sleep(1)
            return True
        else:
            cmd = ["/usr/sbin/chdev", "-l", interface, "-a", "state=down"]
            LOG.debug("Attempting to run bring down interface %s using command %s", device_name, cmd)
            try:
                (_out, err) = subp.subp(cmd, rcs=[0, 1])
                time.sleep(1)
                if len(err):
                    LOG.warn("Running %s resulted in stderr output: %s", cmd, err)
                return True
            except subp.ProcessExecutionError:
                util.logexc(LOG, "Running interface command %s failed", cmd)
                return False

    def _bring_down_interfaces(self, device_names):
        if device_names and 'all' in device_names:
            raise RuntimeError(('Distro %s can not translate the device name "all"') % (self.name))
        am_failed = 0
        for d in device_names:
            if not self._bring_down_interface(d):
                am_failed += 1
        if am_failed == 0:
            return True
        return False

    def set_timezone(self, tz):
        cmd = ["/usr/bin/chtz", tz]
        subp.subp(cmd)

    def package_command(self, command, args=None, pkgs=None):
        if pkgs is None:
            pkgs = []
      
        if subp.which("dnf"):
            LOG.debug("Using DNF for package management") 
            cmd = ["dnf"]
        else:
            LOG.debug("Using YUM for package management")
            cmd = ["yum", "-t"]
        # Determines whether or not yum prompts for confirmation
        # of critical actions. We don't want to prompt...
        cmd.append("-y")

        if args and isinstance(args, str):
            cmd.append(args)
        elif args and isinstance(args, list):
            cmd.extend(args)

        cmd.append(command)

        pkglist = util.expand_package_list("%s-%s", pkgs)
        cmd.extend(pkglist)

        # Allow the output of this to flow outwards (ie not be captured)
        subp.subp(cmd, capture=False)

    def update_package_sources(self):
        self._runner.run("update-sources", self.package_command,
                         ["makecache"], freq=PER_INSTANCE)

    def add_user(self, name, **kwargs):
        if util.is_user(name):
            LOG.info("User %s already exists, skipping.", name)
            return False

        adduser_cmd = ["/usr/sbin/useradd"]
        log_adduser_cmd = ["/usr/sbin/useradd"]

        adduser_opts = {
                "homedir": '-d',
                "gecos": '-c',
                "primary_group": '-g',
                "groups": '-G',
                "shell": '-s',
                "expiredate" : '-e',
        }

        redact_opts = ["passwd"]

        for key, val in list(kwargs.items()):
            if key in adduser_opts and val and isinstance(val, str):
                adduser_cmd.extend([adduser_opts[key], val])

                # Redact certain fields from the logs
                if key in redact_opts:
                    log_adduser_cmd.extend([adduser_opts[key], 'REDACTED'])
                else:
                    log_adduser_cmd.extend([adduser_opts[key], val])

        if 'no_create_home' in kwargs or 'system' in kwargs:
            adduser_cmd.append('-d/nonexistent')
            log_adduser_cmd.append('-d/nonexistent')
        else:
            adduser_cmd.append('-m')
            log_adduser_cmd.append('-m')

        adduser_cmd.append(name)
        log_adduser_cmd.append(name)

        # Run the command
        LOG.debug("Adding user %s", name)
        try:
            subp.subp(adduser_cmd, logstring=log_adduser_cmd)
        except Exception as e:
            util.logexc(LOG, "Failed to create user %s", name)
            raise e

    def create_user(self, name, **kwargs):
        """
        Creates users for the system using the GNU passwd tools. This
        will work on an GNU system. This should be overriden on
        distros where useradd is not desirable or not available.
        """
        # Add the user
        self.add_user(name, **kwargs)

        # Set password if plain-text password provided and non-empty
        if 'plain_text_passwd' in kwargs and kwargs['plain_text_passwd']:
            self.set_passwd(name, kwargs['plain_text_passwd'])

        # Default locking down the account.  'lock_passwd' defaults to True.
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
        return True

    def lock_passwd(self, name):
        """
        Lock the password of a user, i.e., disable password logins
        """
        try:
            # Need to use the short option name '-l' instead of '--lock'
            # (which would be more descriptive) since SLES 11 doesn't know
            # about long names.
            subp.subp(["/usr/bin/chuser", "account_locked=true", name])
        except Exception as e:
            util.logexc(LOG, 'Failed to disable password for user %s', name)
            raise e

    def create_group(self, name, members):
        group_add_cmd = ['/usr/bin/mkgroup', name]

        # Check if group exists, and then add it doesn't
        if util.is_group(name):
            LOG.warn("Skipping creation of existing group '%s'" % name)
        else:
            try:
                subp.subp(group_add_cmd)
                LOG.info("Created new group %s" % name)
            except Exception:
                util.logexc("Failed to create group %s", name)

        # Add members to the group, if so defined
        if len(members) > 0:
            for member in members:
                if not util.is_user(member):
                    LOG.warn("Unable to add group member '%s' to group '%s'; user does not exist.", member, name)
                    continue

                subp.subp(["/usr/sbin/usermod", "-G", name, member])
                LOG.info("Added user '%s' to group '%s'" % (member, name))
