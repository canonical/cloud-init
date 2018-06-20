# Copyright (C) 2012 Canonical Ltd.
# Copyright (C) 2012, 2013 Hewlett-Packard Development Company, L.P.
# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
# Author: Ben Howard <ben.howard@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import six
from six import StringIO

import abc
import os
import re
import stat

from cloudinit import importer
from cloudinit import log as logging
from cloudinit import net
from cloudinit.net import eni
from cloudinit.net import network_state
from cloudinit.net import renderers
from cloudinit import ssh_util
from cloudinit import type_utils
from cloudinit import util

from cloudinit.distros.parsers import hosts


# Used when a cloud-config module can be run on all cloud-init distibutions.
# The value 'all' is surfaced in module documentation for distro support.
ALL_DISTROS = 'all'

OSFAMILIES = {
    'debian': ['debian', 'ubuntu'],
    'redhat': ['centos', 'fedora', 'rhel'],
    'gentoo': ['gentoo'],
    'freebsd': ['freebsd'],
    'suse': ['opensuse', 'sles'],
    'arch': ['arch'],
}

LOG = logging.getLogger(__name__)

# This is a best guess regex, based on current EC2 AZs on 2017-12-11.
# It could break when Amazon adds new regions and new AZs.
_EC2_AZ_RE = re.compile('^[a-z][a-z]-(?:[a-z]+-)+[0-9][a-z]$')

# Default NTP Client Configurations
PREFERRED_NTP_CLIENTS = ['chrony', 'systemd-timesyncd', 'ntp', 'ntpdate']


@six.add_metaclass(abc.ABCMeta)
class Distro(object):

    usr_lib_exec = "/usr/lib"
    hosts_fn = "/etc/hosts"
    ci_sudoers_fn = "/etc/sudoers.d/90-cloud-init-users"
    hostname_conf_fn = "/etc/hostname"
    tz_zone_dir = "/usr/share/zoneinfo"
    init_cmd = ['service']  # systemctl, service etc
    renderer_configs = {}
    _preferred_ntp_clients = None

    def __init__(self, name, cfg, paths):
        self._paths = paths
        self._cfg = cfg
        self.name = name

    @abc.abstractmethod
    def install_packages(self, pkglist):
        raise NotImplementedError()

    @abc.abstractmethod
    def _write_network(self, settings):
        # In the future use the http://fedorahosted.org/netcf/
        # to write this blob out in a distro format
        raise NotImplementedError()

    def _write_network_config(self, settings):
        raise NotImplementedError()

    def _supported_write_network_config(self, network_config):
        priority = util.get_cfg_by_path(
            self._cfg, ('network', 'renderers'), None)

        name, render_cls = renderers.select(priority=priority)
        LOG.debug("Selected renderer '%s' from priority list: %s",
                  name, priority)
        renderer = render_cls(config=self.renderer_configs.get(name))
        renderer.render_network_config(network_config=network_config)
        return []

    def _find_tz_file(self, tz):
        tz_file = os.path.join(self.tz_zone_dir, str(tz))
        if not os.path.isfile(tz_file):
            raise IOError(("Invalid timezone %s,"
                           " no file found at %s") % (tz, tz_file))
        return tz_file

    def get_option(self, opt_name, default=None):
        return self._cfg.get(opt_name, default)

    def set_hostname(self, hostname, fqdn=None):
        writeable_hostname = self._select_hostname(hostname, fqdn)
        self._write_hostname(writeable_hostname, self.hostname_conf_fn)
        self._apply_hostname(writeable_hostname)

    def uses_systemd(self):
        """Wrapper to report whether this distro uses systemd or sysvinit."""
        return uses_systemd()

    @abc.abstractmethod
    def package_command(self, cmd, args=None, pkgs=None):
        raise NotImplementedError()

    @abc.abstractmethod
    def update_package_sources(self):
        raise NotImplementedError()

    def get_primary_arch(self):
        arch = os.uname()[4]
        if arch in ("i386", "i486", "i586", "i686"):
            return "i386"
        return arch

    def _get_arch_package_mirror_info(self, arch=None):
        mirror_info = self.get_option("package_mirrors", [])
        if not arch:
            arch = self.get_primary_arch()
        return _get_arch_package_mirror_info(mirror_info, arch)

    def get_package_mirror_info(self, arch=None, data_source=None):
        # This resolves the package_mirrors config option
        # down to a single dict of {mirror_name: mirror_url}
        arch_info = self._get_arch_package_mirror_info(arch)
        return _get_package_mirror_info(data_source=data_source,
                                        mirror_info=arch_info)

    def apply_network(self, settings, bring_up=True):
        # this applies network where 'settings' is interfaces(5) style
        # it is obsolete compared to apply_network_config
        # Write it out
        dev_names = self._write_network(settings)
        # Now try to bring them up
        if bring_up:
            return self._bring_up_interfaces(dev_names)
        return False

    def _apply_network_from_network_config(self, netconfig, bring_up=True):
        distro = self.__class__
        LOG.warning("apply_network_config is not currently implemented "
                    "for distribution '%s'.  Attempting to use apply_network",
                    distro)
        header = '\n'.join([
            "# Converted from network_config for distro %s" % distro,
            "# Implmentation of _write_network_config is needed."
        ])
        ns = network_state.parse_net_config_data(netconfig)
        contents = eni.network_state_to_eni(
            ns, header=header, render_hwaddress=True)
        return self.apply_network(contents, bring_up=bring_up)

    def generate_fallback_config(self):
        return net.generate_fallback_config()

    def apply_network_config(self, netconfig, bring_up=False):
        # apply network config netconfig
        # This method is preferred to apply_network which only takes
        # a much less complete network config format (interfaces(5)).
        try:
            dev_names = self._write_network_config(netconfig)
        except NotImplementedError:
            # backwards compat until all distros have apply_network_config
            return self._apply_network_from_network_config(
                netconfig, bring_up=bring_up)

        # Now try to bring them up
        if bring_up:
            return self._bring_up_interfaces(dev_names)
        return False

    def apply_network_config_names(self, netconfig):
        net.apply_network_config_names(netconfig)

    @abc.abstractmethod
    def apply_locale(self, locale, out_fn=None):
        raise NotImplementedError()

    @abc.abstractmethod
    def set_timezone(self, tz):
        raise NotImplementedError()

    def _get_localhost_ip(self):
        return "127.0.0.1"

    def get_locale(self):
        raise NotImplementedError()

    @abc.abstractmethod
    def _read_hostname(self, filename, default=None):
        raise NotImplementedError()

    @abc.abstractmethod
    def _write_hostname(self, hostname, filename):
        raise NotImplementedError()

    @abc.abstractmethod
    def _read_system_hostname(self):
        raise NotImplementedError()

    def _apply_hostname(self, hostname):
        # This really only sets the hostname
        # temporarily (until reboot so it should
        # not be depended on). Use the write
        # hostname functions for 'permanent' adjustments.
        LOG.debug("Non-persistently setting the system hostname to %s",
                  hostname)
        try:
            util.subp(['hostname', hostname])
        except util.ProcessExecutionError:
            util.logexc(LOG, "Failed to non-persistently adjust the system "
                        "hostname to %s", hostname)

    def _select_hostname(self, hostname, fqdn):
        # Prefer the short hostname over the long
        # fully qualified domain name
        if not hostname:
            return fqdn
        return hostname

    @staticmethod
    def expand_osfamily(family_list):
        distros = []
        for family in family_list:
            if family not in OSFAMILIES:
                raise ValueError("No distibutions found for osfamily %s"
                                 % (family))
            distros.extend(OSFAMILIES[family])
        return distros

    def update_hostname(self, hostname, fqdn, prev_hostname_fn):
        applying_hostname = hostname

        # Determine what the actual written hostname should be
        hostname = self._select_hostname(hostname, fqdn)

        # If the previous hostname file exists lets see if we
        # can get a hostname from it
        if prev_hostname_fn and os.path.exists(prev_hostname_fn):
            prev_hostname = self._read_hostname(prev_hostname_fn)
        else:
            prev_hostname = None

        # Lets get where we should write the system hostname
        # and what the system hostname is
        (sys_fn, sys_hostname) = self._read_system_hostname()
        update_files = []

        # If there is no previous hostname or it differs
        # from what we want, lets update it or create the
        # file in the first place
        if not prev_hostname or prev_hostname != hostname:
            update_files.append(prev_hostname_fn)

        # If the system hostname is different than the previous
        # one or the desired one lets update it as well
        if ((not sys_hostname) or (sys_hostname == prev_hostname and
           sys_hostname != hostname)):
            update_files.append(sys_fn)

        # If something else has changed the hostname after we set it
        # initially, we should not overwrite those changes (we should
        # only be setting the hostname once per instance)
        if (sys_hostname and prev_hostname and
                sys_hostname != prev_hostname):
            LOG.info("%s differs from %s, assuming user maintained hostname.",
                     prev_hostname_fn, sys_fn)
            return

        # Remove duplicates (incase the previous config filename)
        # is the same as the system config filename, don't bother
        # doing it twice
        update_files = set([f for f in update_files if f])
        LOG.debug("Attempting to update hostname to %s in %s files",
                  hostname, len(update_files))

        for fn in update_files:
            try:
                self._write_hostname(hostname, fn)
            except IOError:
                util.logexc(LOG, "Failed to write hostname %s to %s", hostname,
                            fn)

        # If the system hostname file name was provided set the
        # non-fqdn as the transient hostname.
        if sys_fn in update_files:
            self._apply_hostname(applying_hostname)

    def update_etc_hosts(self, hostname, fqdn):
        header = ''
        if os.path.exists(self.hosts_fn):
            eh = hosts.HostsConf(util.load_file(self.hosts_fn))
        else:
            eh = hosts.HostsConf('')
            header = util.make_header(base="added")
        local_ip = self._get_localhost_ip()
        prev_info = eh.get_entry(local_ip)
        need_change = False
        if not prev_info:
            eh.add_entry(local_ip, fqdn, hostname)
            need_change = True
        else:
            need_change = True
            for entry in prev_info:
                entry_fqdn = None
                entry_aliases = []
                if len(entry) >= 1:
                    entry_fqdn = entry[0]
                if len(entry) >= 2:
                    entry_aliases = entry[1:]
                if entry_fqdn is not None and entry_fqdn == fqdn:
                    if hostname in entry_aliases:
                        # Exists already, leave it be
                        need_change = False
            if need_change:
                # Doesn't exist, add that entry in...
                new_entries = list(prev_info)
                new_entries.append([fqdn, hostname])
                eh.del_entries(local_ip)
                for entry in new_entries:
                    if len(entry) == 1:
                        eh.add_entry(local_ip, entry[0])
                    elif len(entry) >= 2:
                        eh.add_entry(local_ip, *entry)
        if need_change:
            contents = StringIO()
            if header:
                contents.write("%s\n" % (header))
            contents.write("%s\n" % (eh))
            util.write_file(self.hosts_fn, contents.getvalue(), mode=0o644)

    @property
    def preferred_ntp_clients(self):
        """Allow distro to determine the preferred ntp client list"""
        if not self._preferred_ntp_clients:
            self._preferred_ntp_clients = list(PREFERRED_NTP_CLIENTS)

        return self._preferred_ntp_clients

    def _bring_up_interface(self, device_name):
        cmd = ['ifup', device_name]
        LOG.debug("Attempting to run bring up interface %s using command %s",
                  device_name, cmd)
        try:
            (_out, err) = util.subp(cmd)
            if len(err):
                LOG.warning("Running %s resulted in stderr output: %s",
                            cmd, err)
            return True
        except util.ProcessExecutionError:
            util.logexc(LOG, "Running interface command %s failed", cmd)
            return False

    def _bring_up_interfaces(self, device_names):
        am_failed = 0
        for d in device_names:
            if not self._bring_up_interface(d):
                am_failed += 1
        if am_failed == 0:
            return True
        return False

    def get_default_user(self):
        return self.get_option('default_user')

    def add_user(self, name, **kwargs):
        """
        Add a user to the system using standard GNU tools
        """
        if util.is_user(name):
            LOG.info("User %s already exists, skipping.", name)
            return

        if 'create_groups' in kwargs:
            create_groups = kwargs.pop('create_groups')
        else:
            create_groups = True

        adduser_cmd = ['useradd', name]
        log_adduser_cmd = ['useradd', name]
        if util.system_is_snappy():
            adduser_cmd.append('--extrausers')
            log_adduser_cmd.append('--extrausers')

        # Since we are creating users, we want to carefully validate the
        # inputs. If something goes wrong, we can end up with a system
        # that nobody can login to.
        adduser_opts = {
            "gecos": '--comment',
            "homedir": '--home',
            "primary_group": '--gid',
            "uid": '--uid',
            "groups": '--groups',
            "passwd": '--password',
            "shell": '--shell',
            "expiredate": '--expiredate',
            "inactive": '--inactive',
            "selinux_user": '--selinux-user',
        }

        adduser_flags = {
            "no_user_group": '--no-user-group',
            "system": '--system',
            "no_log_init": '--no-log-init',
        }

        redact_opts = ['passwd']

        # support kwargs having groups=[list] or groups="g1,g2"
        groups = kwargs.get('groups')
        if groups:
            if isinstance(groups, six.string_types):
                groups = groups.split(",")

            # remove any white spaces in group names, most likely
            # that came in as a string like: groups: group1, group2
            groups = [g.strip() for g in groups]

            # kwargs.items loop below wants a comma delimeted string
            # that can go right through to the command.
            kwargs['groups'] = ",".join(groups)

            primary_group = kwargs.get('primary_group')
            if primary_group:
                groups.append(primary_group)

        if create_groups and groups:
            for group in groups:
                if not util.is_group(group):
                    self.create_group(group)
                    LOG.debug("created group '%s' for user '%s'", group, name)

        # Check the values and create the command
        for key, val in sorted(kwargs.items()):

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

        # Don't create the home directory if directed so or if the user is a
        # system user
        if kwargs.get('no_create_home') or kwargs.get('system'):
            adduser_cmd.append('-M')
            log_adduser_cmd.append('-M')
        else:
            adduser_cmd.append('-m')
            log_adduser_cmd.append('-m')

        # Run the command
        LOG.debug("Adding user %s", name)
        try:
            util.subp(adduser_cmd, logstring=log_adduser_cmd)
        except Exception as e:
            util.logexc(LOG, "Failed to create user %s", name)
            raise e

    def add_snap_user(self, name, **kwargs):
        """
        Add a snappy user to the system using snappy tools
        """

        snapuser = kwargs.get('snapuser')
        known = kwargs.get('known', False)
        adduser_cmd = ["snap", "create-user", "--sudoer", "--json"]
        if known:
            adduser_cmd.append("--known")
        adduser_cmd.append(snapuser)

        # Run the command
        LOG.debug("Adding snap user %s", name)
        try:
            (out, err) = util.subp(adduser_cmd, logstring=adduser_cmd,
                                   capture=True)
            LOG.debug("snap create-user returned: %s:%s", out, err)
            jobj = util.load_json(out)
            username = jobj.get('username', None)
        except Exception as e:
            util.logexc(LOG, "Failed to create snap user %s", name)
            raise e

        return username

    def create_user(self, name, **kwargs):
        """
        Creates users for the system using the GNU passwd tools. This
        will work on an GNU system. This should be overriden on
        distros where useradd is not desirable or not available.
        """

        # Add a snap user, if requested
        if 'snapuser' in kwargs:
            return self.add_snap_user(name, **kwargs)

        # Add the user
        self.add_user(name, **kwargs)

        # Set password if plain-text password provided and non-empty
        if 'plain_text_passwd' in kwargs and kwargs['plain_text_passwd']:
            self.set_passwd(name, kwargs['plain_text_passwd'])

        # Set password if hashed password is provided and non-empty
        if 'hashed_passwd' in kwargs and kwargs['hashed_passwd']:
            self.set_passwd(name, kwargs['hashed_passwd'], hashed=True)

        # Default locking down the account.  'lock_passwd' defaults to True.
        # lock account unless lock_password is False.
        if kwargs.get('lock_passwd', True):
            self.lock_passwd(name)

        # Configure sudo access
        if 'sudo' in kwargs and kwargs['sudo'] is not False:
            self.write_sudo_rules(name, kwargs['sudo'])

        # Import SSH keys
        if 'ssh_authorized_keys' in kwargs:
            # Try to handle this in a smart manner.
            keys = kwargs['ssh_authorized_keys']
            if isinstance(keys, six.string_types):
                keys = [keys]
            elif isinstance(keys, dict):
                keys = list(keys.values())
            if keys is not None:
                if not isinstance(keys, (tuple, list, set)):
                    LOG.warning("Invalid type '%s' detected for"
                                " 'ssh_authorized_keys', expected list,"
                                " string, dict, or set.", type(keys))
                else:
                    keys = set(keys) or []
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
            util.subp(['passwd', '-l', name])
        except Exception as e:
            util.logexc(LOG, 'Failed to disable password for user %s', name)
            raise e

    def set_passwd(self, user, passwd, hashed=False):
        pass_string = '%s:%s' % (user, passwd)
        cmd = ['chpasswd']

        if hashed:
            # Need to use the short option name '-e' instead of '--encrypted'
            # (which would be more descriptive) since SLES 11 doesn't know
            # about long names.
            cmd.append('-e')

        try:
            util.subp(cmd, pass_string, logstring="chpasswd for %s" % user)
        except Exception as e:
            util.logexc(LOG, "Failed to set password for %s", user)
            raise e

        return True

    def ensure_sudo_dir(self, path, sudo_base='/etc/sudoers'):
        # Ensure the dir is included and that
        # it actually exists as a directory
        sudoers_contents = ''
        base_exists = False
        if os.path.exists(sudo_base):
            sudoers_contents = util.load_file(sudo_base)
            base_exists = True
        found_include = False
        for line in sudoers_contents.splitlines():
            line = line.strip()
            include_match = re.search(r"^#includedir\s+(.*)$", line)
            if not include_match:
                continue
            included_dir = include_match.group(1).strip()
            if not included_dir:
                continue
            included_dir = os.path.abspath(included_dir)
            if included_dir == path:
                found_include = True
                break
        if not found_include:
            try:
                if not base_exists:
                    lines = [('# See sudoers(5) for more information'
                              ' on "#include" directives:'), '',
                             util.make_header(base="added"),
                             "#includedir %s" % (path), '']
                    sudoers_contents = "\n".join(lines)
                    util.write_file(sudo_base, sudoers_contents, 0o440)
                else:
                    lines = ['', util.make_header(base="added"),
                             "#includedir %s" % (path), '']
                    sudoers_contents = "\n".join(lines)
                    util.append_file(sudo_base, sudoers_contents)
                LOG.debug("Added '#includedir %s' to %s", path, sudo_base)
            except IOError as e:
                util.logexc(LOG, "Failed to write %s", sudo_base)
                raise e
        util.ensure_dir(path, 0o750)

    def write_sudo_rules(self, user, rules, sudo_file=None):
        if not sudo_file:
            sudo_file = self.ci_sudoers_fn

        lines = [
            '',
            "# User rules for %s" % user,
        ]
        if isinstance(rules, (list, tuple)):
            for rule in rules:
                lines.append("%s %s" % (user, rule))
        elif isinstance(rules, six.string_types):
            lines.append("%s %s" % (user, rules))
        else:
            msg = "Can not create sudoers rule addition with type %r"
            raise TypeError(msg % (type_utils.obj_name(rules)))
        content = "\n".join(lines)
        content += "\n"  # trailing newline

        self.ensure_sudo_dir(os.path.dirname(sudo_file))
        if not os.path.exists(sudo_file):
            contents = [
                util.make_header(),
                content,
            ]
            try:
                util.write_file(sudo_file, "\n".join(contents), 0o440)
            except IOError as e:
                util.logexc(LOG, "Failed to write sudoers file %s", sudo_file)
                raise e
        else:
            try:
                util.append_file(sudo_file, content)
            except IOError as e:
                util.logexc(LOG, "Failed to append sudoers file %s", sudo_file)
                raise e

    def create_group(self, name, members=None):
        group_add_cmd = ['groupadd', name]
        if util.system_is_snappy():
            group_add_cmd.append('--extrausers')
        if not members:
            members = []

        # Check if group exists, and then add it doesn't
        if util.is_group(name):
            LOG.warning("Skipping creation of existing group '%s'", name)
        else:
            try:
                util.subp(group_add_cmd)
                LOG.info("Created new group %s", name)
            except Exception:
                util.logexc(LOG, "Failed to create group %s", name)

        # Add members to the group, if so defined
        if len(members) > 0:
            for member in members:
                if not util.is_user(member):
                    LOG.warning("Unable to add group member '%s' to group '%s'"
                                "; user does not exist.", member, name)
                    continue

                util.subp(['usermod', '-a', '-G', name, member])
                LOG.info("Added user '%s' to group '%s'", member, name)


def _get_package_mirror_info(mirror_info, data_source=None,
                             mirror_filter=util.search_for_mirror):
    # given a arch specific 'mirror_info' entry (from package_mirrors)
    # search through the 'search' entries, and fallback appropriately
    # return a dict with only {name: mirror} entries.
    if not mirror_info:
        mirror_info = {}

    subst = {}
    if data_source and data_source.availability_zone:
        subst['availability_zone'] = data_source.availability_zone

        # ec2 availability zones are named cc-direction-[0-9][a-d] (us-east-1b)
        # the region is us-east-1. so region = az[0:-1]
        if _EC2_AZ_RE.match(data_source.availability_zone):
            subst['ec2_region'] = "%s" % data_source.availability_zone[0:-1]

    if data_source and data_source.region:
        subst['region'] = data_source.region

    results = {}
    for (name, mirror) in mirror_info.get('failsafe', {}).items():
        results[name] = mirror

    for (name, searchlist) in mirror_info.get('search', {}).items():
        mirrors = []
        for tmpl in searchlist:
            try:
                mirrors.append(tmpl % subst)
            except KeyError:
                pass

        found = mirror_filter(mirrors)
        if found:
            results[name] = found

    LOG.debug("filtered distro mirror info: %s", results)

    return results


def _get_arch_package_mirror_info(package_mirrors, arch):
    # pull out the specific arch from a 'package_mirrors' config option
    default = None
    for item in package_mirrors:
        arches = item.get("arches")
        if arch in arches:
            return item
        if "default" in arches:
            default = item
    return default


def fetch(name):
    locs, looked_locs = importer.find_module(name, ['', __name__], ['Distro'])
    if not locs:
        raise ImportError("No distribution found for distro %s (searched %s)"
                          % (name, looked_locs))
    mod = importer.import_module(locs[0])
    cls = getattr(mod, 'Distro')
    return cls


def set_etc_timezone(tz, tz_file=None, tz_conf="/etc/timezone",
                     tz_local="/etc/localtime"):
    util.write_file(tz_conf, str(tz).rstrip() + "\n")
    # This ensures that the correct tz will be used for the system
    if tz_local and tz_file:
        # use a symlink if there exists a symlink or tz_local is not present
        islink = os.path.islink(tz_local)
        if islink or not os.path.exists(tz_local):
            if islink:
                util.del_file(tz_local)
            os.symlink(tz_file, tz_local)
        else:
            util.copy(tz_file, tz_local)
    return


def uses_systemd():
    try:
        res = os.lstat('/run/systemd/system')
        return stat.S_ISDIR(res.st_mode)
    except Exception:
        return False


# vi: ts=4 expandtab
