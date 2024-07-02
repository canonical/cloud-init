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

import abc
import logging
import os
import re
import stat
import string
import urllib.parse
from collections import defaultdict
from contextlib import suppress
from io import StringIO
from typing import (
    Any,
    Dict,
    List,
    Mapping,
    MutableMapping,
    Optional,
    Set,
    Tuple,
    Type,
    Union,
)

import cloudinit.net.netops.iproute2 as iproute2
from cloudinit import (
    helpers,
    importer,
    net,
    persistence,
    ssh_util,
    subp,
    temp_utils,
    type_utils,
    util,
)
from cloudinit.distros.networking import LinuxNetworking, Networking
from cloudinit.distros.package_management.package_manager import PackageManager
from cloudinit.distros.package_management.utils import known_package_managers
from cloudinit.distros.parsers import hosts
from cloudinit.features import ALLOW_EC2_MIRRORS_ON_NON_AWS_INSTANCE_TYPES
from cloudinit.net import activators, dhcp, renderers
from cloudinit.net.netops import NetOps
from cloudinit.net.network_state import parse_net_config_data
from cloudinit.net.renderer import Renderer

# Used when a cloud-config module can be run on all cloud-init distributions.
# The value 'all' is surfaced in module documentation for distro support.
ALL_DISTROS = "all"

OSFAMILIES = {
    "alpine": ["alpine"],
    "arch": ["arch"],
    "debian": ["debian", "ubuntu"],
    "freebsd": ["freebsd", "dragonfly"],
    "gentoo": ["gentoo", "cos"],
    "netbsd": ["netbsd"],
    "openbsd": ["openbsd"],
    "redhat": [
        "almalinux",
        "amazon",
        "azurelinux",
        "centos",
        "cloudlinux",
        "eurolinux",
        "fedora",
        "mariner",
        "miraclelinux",
        "openmandriva",
        "photon",
        "rhel",
        "rocky",
        "virtuozzo",
    ],
    "suse": [
        "opensuse",
        "opensuse-leap",
        "opensuse-microos",
        "opensuse-tumbleweed",
        "sle_hpc",
        "sle-micro",
        "sles",
        "suse",
    ],
    "openeuler": ["openeuler"],
    "OpenCloudOS": ["OpenCloudOS", "TencentOS"],
}

LOG = logging.getLogger(__name__)

# This is a best guess regex, based on current EC2 AZs on 2017-12-11.
# It could break when Amazon adds new regions and new AZs.
_EC2_AZ_RE = re.compile("^[a-z][a-z]-(?:[a-z]+-)+[0-9][a-z]$")

# Default NTP Client Configurations
PREFERRED_NTP_CLIENTS = ["chrony", "systemd-timesyncd", "ntp", "ntpdate"]

# Letters/Digits/Hyphen characters, for use in domain name validation
LDH_ASCII_CHARS = string.ascii_letters + string.digits + "-"

# Before you try to go rewriting this better using Unions, read
# https://github.com/microsoft/pyright/blob/main/docs/type-concepts.md#generic-types  # noqa: E501
# The Immutable types mentioned there won't work for us because
# we need to distinguish between a str and a Sequence[str]
# This also isn't exhaustive. If you have a unique case that adheres to
# the `packages` schema, you can add it here.
PackageList = Union[
    List[str],
    List[Mapping],
    List[List[str]],
    List[Union[str, List[str]]],
    List[Union[str, List[str], Mapping]],
]


class PackageInstallerError(Exception):
    pass


class Distro(persistence.CloudInitPickleMixin, metaclass=abc.ABCMeta):
    pip_package_name = "python3-pip"
    usr_lib_exec = "/usr/lib"
    hosts_fn = "/etc/hosts"
    doas_fn = "/etc/doas.conf"
    ci_sudoers_fn = "/etc/sudoers.d/90-cloud-init-users"
    hostname_conf_fn = "/etc/hostname"
    tz_zone_dir = "/usr/share/zoneinfo"
    default_owner = "root:root"
    init_cmd = ["service"]  # systemctl, service etc
    renderer_configs: Mapping[str, MutableMapping[str, Any]] = {}
    _preferred_ntp_clients = None
    networking_cls: Type[Networking] = LinuxNetworking
    # This is used by self.shutdown_command(), and can be overridden in
    # subclasses
    shutdown_options_map = {"halt": "-H", "poweroff": "-P", "reboot": "-r"}
    net_ops: Type[NetOps] = iproute2.Iproute2

    _ci_pkl_version = 1
    prefer_fqdn = False
    resolve_conf_fn = "/etc/resolv.conf"

    osfamily: str
    # Directory where the distro stores their DHCP leases.
    # The children classes should override this with their dhcp leases
    # directory
    dhclient_lease_directory: Optional[str] = None
    # A regex to match DHCP lease file(s)
    # The children classes should override this with a regex matching
    # their lease file name format
    dhclient_lease_file_regex: Optional[str] = None

    def __init__(self, name, cfg, paths):
        self._paths = paths
        self._cfg = cfg
        self.name = name
        self.networking: Networking = self.networking_cls()
        self.dhcp_client_priority = dhcp.ALL_DHCP_CLIENTS
        self.net_ops = iproute2.Iproute2
        self._runner = helpers.Runners(paths)
        self.package_managers: List[PackageManager] = []
        self._dhcp_client = None
        self._fallback_interface = None

    def _unpickle(self, ci_pkl_version: int) -> None:
        """Perform deserialization fixes for Distro."""
        if "networking" not in self.__dict__ or not self.networking.__dict__:
            # This is either a Distro pickle with no networking attribute OR
            # this is a Distro pickle with a networking attribute but from
            # before ``Networking`` had any state (meaning that
            # Networking.__setstate__ will not be called).  In either case, we
            # want to ensure that `self.networking` is freshly-instantiated:
            # either because it isn't present at all, or because it will be
            # missing expected instance state otherwise.
            self.networking = self.networking_cls()
        if not hasattr(self, "_dhcp_client"):
            self._dhcp_client = None
        if not hasattr(self, "_fallback_interface"):
            self._fallback_interface = None

    def _validate_entry(self, entry):
        if isinstance(entry, str):
            return entry
        elif isinstance(entry, (list, tuple)):
            if len(entry) == 2:
                return tuple(entry)
        raise ValueError(
            "Invalid 'packages' yaml specification. "
            "Check schema definition."
        )

    def _extract_package_by_manager(
        self, pkglist: PackageList
    ) -> Tuple[Dict[Type[PackageManager], Set], Set]:
        """Transform the generic package list to package by package manager.

        Additionally, include list of generic packages
        """
        packages_by_manager = defaultdict(set)
        generic_packages: Set = set()
        for entry in pkglist:
            if isinstance(entry, dict):
                for package_manager, package_list in entry.items():
                    for definition in package_list:
                        definition = self._validate_entry(definition)
                        try:
                            packages_by_manager[
                                known_package_managers[package_manager]
                            ].add(definition)
                        except KeyError:
                            LOG.error(
                                "Cannot install packages under '%s' as it is "
                                "not a supported package manager!",
                                package_manager,
                            )
            else:
                generic_packages.add(self._validate_entry(entry))
        return dict(packages_by_manager), generic_packages

    def install_packages(self, pkglist: PackageList):
        error_message = (
            "Failed to install the following packages: %s. "
            "See associated package manager logs for more details."
        )
        # If an entry hasn't been included with an explicit package name,
        # add it to a 'generic' list of packages
        (
            packages_by_manager,
            generic_packages,
        ) = self._extract_package_by_manager(pkglist)

        # First install packages using package manager(s)
        # supported by the distro
        total_failed: Set[str] = set()
        for manager in self.package_managers:

            manager_packages = packages_by_manager.get(
                manager.__class__, set()
            )

            to_try = manager_packages | generic_packages
            # Remove any failed we will try for this package manager
            total_failed.difference_update(to_try)
            if not manager.available():
                LOG.debug("Package manager '%s' not available", manager.name)
                total_failed.update(to_try)
                continue
            if not to_try:
                continue
            failed = manager.install_packages(to_try)
            total_failed.update(failed)
            if failed:
                LOG.info(error_message, failed)
            # Ensure we don't attempt to install packages specific to
            # one particular package manager using another package manager
            generic_packages = set(failed) - manager_packages

        # Now attempt any specified package managers not explicitly supported
        # by distro
        for manager_type, packages in packages_by_manager.items():
            if manager_type.name in [p.name for p in self.package_managers]:
                # We already installed/attempted these; don't try again
                continue
            total_failed.update(
                manager_type.from_config(
                    self._runner, self._cfg
                ).install_packages(pkglist=packages)
            )

        if total_failed:
            raise PackageInstallerError(error_message % total_failed)

    @property
    def dhcp_client(self) -> dhcp.DhcpClient:
        """access the distro's preferred dhcp client

        if no client has been selected yet select one - uses
        self.dhcp_client_priority, which may be overridden in each distro's
        object to eliminate checking for clients which will not be provided
        by the distro
        """
        if self._dhcp_client:
            return self._dhcp_client

        # no client has been selected yet, so pick one
        #
        # set the default priority list to the distro-defined priority list
        dhcp_client_priority = self.dhcp_client_priority

        # if the configuration includes a network.dhcp_client_priority list
        # then attempt to use it
        config_priority = util.get_cfg_by_path(
            self._cfg, ("network", "dhcp_client_priority"), []
        )

        if config_priority:
            # user or image builder configured a custom dhcp client priority
            # list
            found_clients = []
            LOG.debug(
                "Using configured dhcp client priority list: %s",
                config_priority,
            )
            for client_configured in config_priority:
                for client_class in dhcp.ALL_DHCP_CLIENTS:
                    if client_configured == client_class.client_name:
                        found_clients.append(client_class)
                        break
                else:
                    LOG.warning(
                        "Configured dhcp client %s is not supported, skipping",
                        client_configured,
                    )
            # If dhcp_client_priority is defined in the configuration, but none
            # of the defined clients are supported by cloud-init, then we don't
            # override the distro default. If at least one client in the
            # configured list exists, then we use that for our list of clients
            # to check.
            if found_clients:
                dhcp_client_priority = found_clients

        # iterate through our priority list and use the first client that is
        # installed on the system
        for client in dhcp_client_priority:
            try:
                self._dhcp_client = client()
                LOG.debug("DHCP client selected: %s", client.client_name)
                return self._dhcp_client
            except (dhcp.NoDHCPLeaseMissingDhclientError,):
                LOG.debug("DHCP client not found: %s", client.client_name)
        raise dhcp.NoDHCPLeaseMissingDhclientError()

    @property
    def network_activator(self) -> Optional[Type[activators.NetworkActivator]]:
        """Return the configured network activator for this environment."""
        priority = util.get_cfg_by_path(
            self._cfg, ("network", "activators"), None
        )
        try:
            return activators.select_activator(priority=priority)
        except activators.NoActivatorException:
            return None

    @property
    def network_renderer(self) -> Renderer:
        priority = util.get_cfg_by_path(
            self._cfg, ("network", "renderers"), None
        )

        name, render_cls = renderers.select(priority=priority)
        LOG.debug(
            "Selected renderer '%s' from priority list: %s", name, priority
        )
        renderer = render_cls(config=self.renderer_configs.get(name))
        return renderer

    def _write_network_state(self, network_state, renderer: Renderer):
        renderer.render_network_state(network_state)

    def _find_tz_file(self, tz):
        tz_file = os.path.join(self.tz_zone_dir, str(tz))
        if not os.path.isfile(tz_file):
            raise IOError(
                "Invalid timezone %s, no file found at %s" % (tz, tz_file)
            )
        return tz_file

    def get_option(self, opt_name, default=None):
        return self._cfg.get(opt_name, default)

    def set_option(self, opt_name, value=None):
        self._cfg[opt_name] = value

    def set_hostname(self, hostname, fqdn=None):
        writeable_hostname = self._select_hostname(hostname, fqdn)
        self._write_hostname(writeable_hostname, self.hostname_conf_fn)
        self._apply_hostname(writeable_hostname)

    @staticmethod
    def uses_systemd():
        """Wrapper to report whether this distro uses systemd or sysvinit."""
        return uses_systemd()

    @abc.abstractmethod
    def package_command(self, command, args=None, pkgs=None):
        # Long-term, this method should be removed and callers refactored.
        # Very few commands are going to be consistent across all package
        # managers.
        raise NotImplementedError()

    def update_package_sources(self, *, force=False):
        for manager in self.package_managers:
            if not manager.available():
                LOG.debug(
                    "Skipping update for package manager '%s': not available.",
                    manager.name,
                )
                continue
            try:
                manager.update_package_sources(force=force)
            except Exception as e:
                LOG.error(
                    "Failed to update package using %s: %s", manager.name, e
                )

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
        return _get_package_mirror_info(
            data_source=data_source, mirror_info=arch_info
        )

    def generate_fallback_config(self):
        return net.generate_fallback_config()

    def apply_network_config(self, netconfig, bring_up=False) -> bool:
        """Apply the network config.

        If bring_up is True, attempt to bring up the passed in devices. If
        devices is None, attempt to bring up devices returned by
        _write_network_config.

        Returns True if any devices failed to come up, otherwise False.
        """
        renderer = self.network_renderer
        network_state = parse_net_config_data(netconfig, renderer=renderer)
        self._write_network_state(network_state, renderer)

        # Now try to bring them up
        if bring_up:
            LOG.debug("Bringing up newly configured network interfaces")
            network_activator = self.network_activator
            if not network_activator:
                LOG.warning(
                    "No network activator found, not bringing up "
                    "network interfaces"
                )
                return True
            network_activator.bring_up_all_interfaces(network_state)
        else:
            LOG.debug("Not bringing up newly configured network interfaces")
        return False

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
        LOG.debug(
            "Non-persistently setting the system hostname to %s", hostname
        )
        try:
            subp.subp(["hostname", hostname])
        except subp.ProcessExecutionError:
            util.logexc(
                LOG,
                "Failed to non-persistently adjust the system hostname to %s",
                hostname,
            )

    def _select_hostname(self, hostname, fqdn):
        # Prefer the short hostname over the long
        # fully qualified domain name
        if (
            util.get_cfg_option_bool(
                self._cfg, "prefer_fqdn_over_hostname", self.prefer_fqdn
            )
            and fqdn
        ):
            return fqdn
        if not hostname:
            return fqdn
        return hostname

    @staticmethod
    def expand_osfamily(family_list):
        distros = []
        for family in family_list:
            if family not in OSFAMILIES:
                raise ValueError(
                    "No distributions found for osfamily {}".format(family)
                )
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
        if (not sys_hostname) or (
            sys_hostname == prev_hostname and sys_hostname != hostname
        ):
            update_files.append(sys_fn)

        # If something else has changed the hostname after we set it
        # initially, we should not overwrite those changes (we should
        # only be setting the hostname once per instance)
        if sys_hostname and prev_hostname and sys_hostname != prev_hostname:
            LOG.info(
                "%s differs from %s, assuming user maintained hostname.",
                prev_hostname_fn,
                sys_fn,
            )
            return

        # Remove duplicates (incase the previous config filename)
        # is the same as the system config filename, don't bother
        # doing it twice
        update_files = set([f for f in update_files if f])
        LOG.debug(
            "Attempting to update hostname to %s in %s files",
            hostname,
            len(update_files),
        )

        for fn in update_files:
            try:
                self._write_hostname(hostname, fn)
            except IOError:
                util.logexc(
                    LOG, "Failed to write hostname %s to %s", hostname, fn
                )

        # If the system hostname file name was provided set the
        # non-fqdn as the transient hostname.
        if sys_fn in update_files:
            self._apply_hostname(applying_hostname)

    def update_etc_hosts(self, hostname, fqdn):
        header = ""
        if os.path.exists(self.hosts_fn):
            eh = hosts.HostsConf(util.load_text_file(self.hosts_fn))
        else:
            eh = hosts.HostsConf("")
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

    def get_default_user(self):
        return self.get_option("default_user")

    def add_user(self, name, **kwargs):
        """
        Add a user to the system using standard GNU tools

        This should be overridden on distros where useradd is not desirable or
        not available.
        """
        # XXX need to make add_user idempotent somehow as we
        # still want to add groups or modify SSH keys on pre-existing
        # users in the image.
        if util.is_user(name):
            LOG.info("User %s already exists, skipping.", name)
            return

        if "create_groups" in kwargs:
            create_groups = kwargs.pop("create_groups")
        else:
            create_groups = True

        useradd_cmd = ["useradd", name]
        log_useradd_cmd = ["useradd", name]
        if util.system_is_snappy():
            useradd_cmd.append("--extrausers")
            log_useradd_cmd.append("--extrausers")

        # Since we are creating users, we want to carefully validate the
        # inputs. If something goes wrong, we can end up with a system
        # that nobody can login to.
        useradd_opts = {
            "gecos": "--comment",
            "homedir": "--home",
            "primary_group": "--gid",
            "uid": "--uid",
            "groups": "--groups",
            "passwd": "--password",
            "shell": "--shell",
            "expiredate": "--expiredate",
            "inactive": "--inactive",
            "selinux_user": "--selinux-user",
        }

        useradd_flags = {
            "no_user_group": "--no-user-group",
            "system": "--system",
            "no_log_init": "--no-log-init",
        }

        redact_opts = ["passwd"]

        # support kwargs having groups=[list] or groups="g1,g2"
        groups = kwargs.get("groups")
        if groups:
            if isinstance(groups, str):
                groups = groups.split(",")

            if isinstance(groups, dict):
                util.deprecate(
                    deprecated=f"The user {name} has a 'groups' config value "
                    "of type dict",
                    deprecated_version="22.3",
                    extra_message="Use a comma-delimited string or "
                    "array instead: group1,group2.",
                )

            # remove any white spaces in group names, most likely
            # that came in as a string like: groups: group1, group2
            groups = [g.strip() for g in groups]

            # kwargs.items loop below wants a comma delimited string
            # that can go right through to the command.
            kwargs["groups"] = ",".join(groups)

            primary_group = kwargs.get("primary_group")
            if primary_group:
                groups.append(primary_group)

        if create_groups and groups:
            for group in groups:
                if not util.is_group(group):
                    self.create_group(group)
                    LOG.debug("created group '%s' for user '%s'", group, name)
        if "uid" in kwargs.keys():
            kwargs["uid"] = str(kwargs["uid"])

        # Check the values and create the command
        for key, val in sorted(kwargs.items()):
            if key in useradd_opts and val and isinstance(val, str):
                useradd_cmd.extend([useradd_opts[key], val])

                # Redact certain fields from the logs
                if key in redact_opts:
                    log_useradd_cmd.extend([useradd_opts[key], "REDACTED"])
                else:
                    log_useradd_cmd.extend([useradd_opts[key], val])

            elif key in useradd_flags and val:
                useradd_cmd.append(useradd_flags[key])
                log_useradd_cmd.append(useradd_flags[key])

        # Don't create the home directory if directed so or if the user is a
        # system user
        if kwargs.get("no_create_home") or kwargs.get("system"):
            useradd_cmd.append("-M")
            log_useradd_cmd.append("-M")
        else:
            useradd_cmd.append("-m")
            log_useradd_cmd.append("-m")

        # Run the command
        LOG.debug("Adding user %s", name)
        try:
            subp.subp(useradd_cmd, logstring=log_useradd_cmd)
        except Exception as e:
            util.logexc(LOG, "Failed to create user %s", name)
            raise e

    def add_snap_user(self, name, **kwargs):
        """
        Add a snappy user to the system using snappy tools
        """

        snapuser = kwargs.get("snapuser")
        known = kwargs.get("known", False)
        create_user_cmd = ["snap", "create-user", "--sudoer", "--json"]
        if known:
            create_user_cmd.append("--known")
        create_user_cmd.append(snapuser)

        # Run the command
        LOG.debug("Adding snap user %s", name)
        try:
            (out, err) = subp.subp(
                create_user_cmd, logstring=create_user_cmd, capture=True
            )
            LOG.debug("snap create-user returned: %s:%s", out, err)
            jobj = util.load_json(out)
            username = jobj.get("username", None)
        except Exception as e:
            util.logexc(LOG, "Failed to create snap user %s", name)
            raise e

        return username

    def create_user(self, name, **kwargs):
        """
        Creates or partially updates the ``name`` user in the system.

        This defers the actual user creation to ``self.add_user`` or
        ``self.add_snap_user``, and most of the keys in ``kwargs`` will be
        processed there if and only if the user does not already exist.

        Once the existence of the ``name`` user has been ensured, this method
        then processes these keys (for both just-created and pre-existing
        users):

        * ``plain_text_passwd``
        * ``hashed_passwd``
        * ``lock_passwd``
        * ``doas``
        * ``sudo``
        * ``ssh_authorized_keys``
        * ``ssh_redirect_user``
        """

        # Add a snap user, if requested
        if "snapuser" in kwargs:
            return self.add_snap_user(name, **kwargs)

        # Add the user
        self.add_user(name, **kwargs)

        # Set password if plain-text password provided and non-empty
        if "plain_text_passwd" in kwargs and kwargs["plain_text_passwd"]:
            self.set_passwd(name, kwargs["plain_text_passwd"])

        # Set password if hashed password is provided and non-empty
        if "hashed_passwd" in kwargs and kwargs["hashed_passwd"]:
            self.set_passwd(name, kwargs["hashed_passwd"], hashed=True)

        # Default locking down the account.  'lock_passwd' defaults to True.
        # lock account unless lock_password is False.
        if kwargs.get("lock_passwd", True):
            self.lock_passwd(name)

        # Configure doas access
        if "doas" in kwargs:
            if kwargs["doas"]:
                self.write_doas_rules(name, kwargs["doas"])

        # Configure sudo access
        if "sudo" in kwargs:
            if kwargs["sudo"]:
                self.write_sudo_rules(name, kwargs["sudo"])
            elif kwargs["sudo"] is False:
                util.deprecate(
                    deprecated=f"The value of 'false' in user {name}'s "
                    "'sudo' config",
                    deprecated_version="22.3",
                    extra_message="Use 'null' instead.",
                )

        # Import SSH keys
        if "ssh_authorized_keys" in kwargs:
            # Try to handle this in a smart manner.
            keys = kwargs["ssh_authorized_keys"]
            if isinstance(keys, str):
                keys = [keys]
            elif isinstance(keys, dict):
                keys = list(keys.values())
            if keys is not None:
                if not isinstance(keys, (tuple, list, set)):
                    LOG.warning(
                        "Invalid type '%s' detected for"
                        " 'ssh_authorized_keys', expected list,"
                        " string, dict, or set.",
                        type(keys),
                    )
                    keys = []
                else:
                    keys = set(keys) or []
            ssh_util.setup_user_keys(set(keys), name)
        if "ssh_redirect_user" in kwargs:
            cloud_keys = kwargs.get("cloud_public_ssh_keys", [])
            if not cloud_keys:
                LOG.warning(
                    "Unable to disable SSH logins for %s given"
                    " ssh_redirect_user: %s. No cloud public-keys present.",
                    name,
                    kwargs["ssh_redirect_user"],
                )
            else:
                redirect_user = kwargs["ssh_redirect_user"]
                disable_option = ssh_util.DISABLE_USER_OPTS
                disable_option = disable_option.replace("$USER", redirect_user)
                disable_option = disable_option.replace("$DISABLE_USER", name)
                ssh_util.setup_user_keys(
                    set(cloud_keys), name, options=disable_option
                )
        return True

    def lock_passwd(self, name):
        """
        Lock the password of a user, i.e., disable password logins
        """
        # passwd must use short '-l' due to SLES11 lacking long form '--lock'
        lock_tools = (["passwd", "-l", name], ["usermod", "--lock", name])
        try:
            cmd = next(tool for tool in lock_tools if subp.which(tool[0]))
        except StopIteration as e:
            raise RuntimeError(
                "Unable to lock user account '%s'. No tools available. "
                "  Tried: %s." % (name, [c[0] for c in lock_tools])
            ) from e
        try:
            subp.subp(cmd)
        except Exception as e:
            util.logexc(LOG, "Failed to disable password for user %s", name)
            raise e

    def expire_passwd(self, user):
        try:
            subp.subp(["passwd", "--expire", user])
        except Exception as e:
            util.logexc(LOG, "Failed to set 'expire' for %s", user)
            raise e

    def set_passwd(self, user, passwd, hashed=False):
        pass_string = "%s:%s" % (user, passwd)
        cmd = ["chpasswd"]

        if hashed:
            # Need to use the short option name '-e' instead of '--encrypted'
            # (which would be more descriptive) since Busybox and SLES 11
            # chpasswd don't know about long names.
            cmd.append("-e")

        try:
            subp.subp(
                cmd, data=pass_string, logstring="chpasswd for %s" % user
            )
        except Exception as e:
            util.logexc(LOG, "Failed to set password for %s", user)
            raise e

        return True

    def chpasswd(self, plist_in: list, hashed: bool):
        payload = (
            "\n".join(
                (":".join([name, password]) for name, password in plist_in)
            )
            + "\n"
        )
        cmd = ["chpasswd"] + (["-e"] if hashed else [])
        subp.subp(cmd, data=payload)

    def is_doas_rule_valid(self, user, rule):
        rule_pattern = (
            r"^(?:permit|deny)"
            r"(?:\s+(?:nolog|nopass|persist|keepenv|setenv \{[^}]+\})+)*"
            r"\s+([a-zA-Z0-9_]+)+"
            r"(?:\s+as\s+[a-zA-Z0-9_]+)*"
            r"(?:\s+cmd\s+[^\s]+(?:\s+args\s+[^\s]+(?:\s*[^\s]+)*)*)*"
            r"\s*$"
        )

        LOG.debug(
            "Checking if user '%s' is referenced in doas rule %r", user, rule
        )

        valid_match = re.search(rule_pattern, rule)
        if valid_match:
            LOG.debug(
                "User '%s' referenced in doas rule", valid_match.group(1)
            )
            if valid_match.group(1) == user:
                LOG.debug("Correct user is referenced in doas rule")
                return True
            else:
                LOG.debug(
                    "Incorrect user '%s' is referenced in doas rule",
                    valid_match.group(1),
                )
                return False
        else:
            LOG.debug("doas rule does not appear to reference any user")
            return False

    def write_doas_rules(self, user, rules, doas_file=None):
        if not doas_file:
            doas_file = self.doas_fn

        for rule in rules:
            if not self.is_doas_rule_valid(user, rule):
                msg = (
                    "Invalid doas rule %r for user '%s',"
                    " not writing any doas rules for user!" % (rule, user)
                )
                LOG.error(msg)
                return

        lines = ["", "# cloud-init User rules for %s" % user]
        for rule in rules:
            lines.append("%s" % rule)
        content = "\n".join(lines)
        content += "\n"  # trailing newline

        if not os.path.exists(doas_file):
            contents = [util.make_header(), content]
            try:
                util.write_file(doas_file, "\n".join(contents), mode=0o440)
            except IOError as e:
                util.logexc(LOG, "Failed to write doas file %s", doas_file)
                raise e
        else:
            if content not in util.load_text_file(doas_file):
                try:
                    util.append_file(doas_file, content)
                except IOError as e:
                    util.logexc(
                        LOG, "Failed to append to doas file %s", doas_file
                    )
                    raise e

    def ensure_sudo_dir(self, path, sudo_base="/etc/sudoers"):
        # Ensure the dir is included and that
        # it actually exists as a directory
        sudoers_contents = ""
        base_exists = False
        system_sudo_base = "/usr/etc/sudoers"
        if os.path.exists(sudo_base):
            sudoers_contents = util.load_text_file(sudo_base)
            base_exists = True
        elif os.path.exists(system_sudo_base):
            sudoers_contents = util.load_text_file(system_sudo_base)
        found_include = False
        for line in sudoers_contents.splitlines():
            line = line.strip()
            include_match = re.search(r"^[#|@]includedir\s+(.*)$", line)
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
                    lines = [
                        "# See sudoers(5) for more information"
                        ' on "#include" directives:',
                        "",
                        util.make_header(base="added"),
                        "#includedir %s" % (path),
                        "",
                    ]
                    if sudoers_contents:
                        LOG.info("Using content from '%s'", system_sudo_base)
                    sudoers_contents += "\n".join(lines)
                    util.write_file(sudo_base, sudoers_contents, 0o440)
                else:
                    lines = [
                        "",
                        util.make_header(base="added"),
                        "#includedir %s" % (path),
                        "",
                    ]
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
            "",
            "# User rules for %s" % user,
        ]
        if isinstance(rules, (list, tuple)):
            for rule in rules:
                lines.append("%s %s" % (user, rule))
        elif isinstance(rules, str):
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
            if content not in util.load_text_file(sudo_file):
                try:
                    util.append_file(sudo_file, content)
                except IOError as e:
                    util.logexc(
                        LOG, "Failed to append to sudoers file %s", sudo_file
                    )
                    raise e

    def create_group(self, name, members=None):
        group_add_cmd = ["groupadd", name]
        if util.system_is_snappy():
            group_add_cmd.append("--extrausers")
        if not members:
            members = []

        # Check if group exists, and then add it doesn't
        if util.is_group(name):
            LOG.warning("Skipping creation of existing group '%s'", name)
        else:
            try:
                subp.subp(group_add_cmd)
                LOG.info("Created new group %s", name)
            except Exception:
                util.logexc(LOG, "Failed to create group %s", name)

        # Add members to the group, if so defined
        if len(members) > 0:
            for member in members:
                if not util.is_user(member):
                    LOG.warning(
                        "Unable to add group member '%s' to group '%s'"
                        "; user does not exist.",
                        member,
                        name,
                    )
                    continue

                subp.subp(["usermod", "-a", "-G", name, member])
                LOG.info("Added user '%s' to group '%s'", member, name)

    @classmethod
    def shutdown_command(cls, *, mode, delay, message):
        # called from cc_power_state_change.load_power_state
        command = ["shutdown", cls.shutdown_options_map[mode]]
        try:
            if delay != "now":
                delay = "+%d" % int(delay)
        except ValueError as e:
            raise TypeError(
                "power_state[delay] must be 'now' or '+m' (minutes)."
                " found '%s'." % (delay,)
            ) from e
        args = command + [delay]
        if message:
            args.append(message)
        return args

    @classmethod
    def reload_init(cls, rcs=None):
        """
        Reload systemd startup daemon.
        May raise ProcessExecutionError
        """
        init_cmd = cls.init_cmd
        if cls.uses_systemd() or "systemctl" in init_cmd:
            cmd = [init_cmd, "daemon-reload"]
            return subp.subp(cmd, capture=True, rcs=rcs)

    @classmethod
    def manage_service(
        cls, action: str, service: str, *extra_args: str, rcs=None
    ):
        """
        Perform the requested action on a service. This handles the common
        'systemctl' and 'service' cases and may be overridden in subclasses
        as necessary.
        May raise ProcessExecutionError
        """
        init_cmd = cls.init_cmd
        if cls.uses_systemd() or "systemctl" in init_cmd:
            init_cmd = ["systemctl"]
            cmds = {
                "stop": ["stop", service],
                "start": ["start", service],
                "enable": ["enable", service],
                "disable": ["disable", service],
                "restart": ["restart", service],
                "reload": ["reload-or-restart", service],
                "try-reload": ["reload-or-try-restart", service],
                "status": ["status", service],
            }
        else:
            cmds = {
                "stop": [service, "stop"],
                "start": [service, "start"],
                "enable": [service, "start"],
                "disable": [service, "stop"],
                "restart": [service, "restart"],
                "reload": [service, "restart"],
                "try-reload": [service, "restart"],
                "status": [service, "status"],
            }
        cmd = list(init_cmd) + list(cmds[action])
        return subp.subp(cmd, capture=True, rcs=rcs)

    def set_keymap(self, layout: str, model: str, variant: str, options: str):
        if self.uses_systemd():
            subp.subp(
                [
                    "localectl",
                    "set-x11-keymap",
                    layout,
                    model,
                    variant,
                    options,
                ]
            )
        else:
            raise NotImplementedError()

    def get_tmp_exec_path(self) -> str:
        tmp_dir = temp_utils.get_tmp_ancestor(needs_exe=True)
        if not util.has_mount_opt(tmp_dir, "noexec"):
            return tmp_dir
        return os.path.join(self.usr_lib_exec, "cloud-init", "clouddir")

    def do_as(self, command: list, user: str, cwd: str = "", **kwargs):
        """
        Perform a command as the requested user. Behaves like subp()

        Note: We pass `PATH` to the user env by using `env`. This could be
        probably simplified after bionic EOL by using
        `su --whitelist-environment=PATH ...`, more info on:
        https://lore.kernel.org/all/20180815110445.4qefy5zx5gfgbqly@ws.net.home/T/
        """
        directory = f"cd {cwd} && " if cwd else ""
        return subp.subp(
            [
                "su",
                "-",
                user,
                "-c",
                directory + "env PATH=$PATH " + " ".join(command),
            ],
            **kwargs,
        )

    @staticmethod
    def build_dhclient_cmd(
        path: str,
        lease_file: str,
        pid_file: str,
        interface: str,
        config_file: str,
    ) -> list:
        return [
            path,
            "-1",
            "-v",
            "-lf",
            lease_file,
            "-pf",
            pid_file,
            "-sf",
            "/bin/true",
        ] + (["-cf", config_file, interface] if config_file else [interface])

    @property
    def fallback_interface(self):
        """Determine the network interface used during local network config."""
        if self._fallback_interface is None:
            self._fallback_interface = net.find_fallback_nic()
            if not self._fallback_interface:
                LOG.warning(
                    "Did not find a fallback interface on distro: %s.",
                    self.name,
                )
        return self._fallback_interface

    @fallback_interface.setter
    def fallback_interface(self, value):
        self._fallback_interface = value

    @staticmethod
    def get_proc_ppid(pid: int) -> Optional[int]:
        """Return the parent pid of a process by parsing /proc/$pid/stat"""
        match = Distro._get_proc_stat_by_index(pid, 4)
        if match is not None:
            with suppress(ValueError):
                return int(match)
            LOG.warning("/proc/%s/stat has an invalid ppid [%s]", pid, match)
        return None

    @staticmethod
    def get_proc_pgid(pid: int) -> Optional[int]:
        """Return the parent pid of a process by parsing /proc/$pid/stat"""
        match = Distro._get_proc_stat_by_index(pid, 5)
        if match is not None:
            with suppress(ValueError):
                return int(match)
            LOG.warning("/proc/%s/stat has an invalid pgid [%s]", pid, match)
        return None

    @staticmethod
    def _get_proc_stat_by_index(pid: int, field: int) -> Optional[int]:
        """
        parse /proc/$pid/stat for a specific field as numbered in man:proc(5)

        param pid: integer to query /proc/$pid/stat for
        param field: field number within /proc/$pid/stat to return
        """
        try:
            content: str = util.load_text_file(
                "/proc/%s/stat" % pid, quiet=True
            ).strip()  # pyright: ignore
            match = re.search(
                r"^(\d+) (\(.+\)) ([RSDZTtWXxKPI]) (\d+) (\d+)", content
            )
            if not match:
                LOG.warning(
                    "/proc/%s/stat has an invalid contents [%s]", pid, content
                )
                return None
            return int(match.group(field))
        except IOError as e:
            LOG.warning("Failed to load /proc/%s/stat. %s", pid, e)
        except IndexError:
            LOG.warning(
                "Unable to match field %s of process pid=%s (%s) (%s)",
                field,
                pid,
                content,  # pyright: ignore
                match,  # pyright: ignore
            )
        return None

    @staticmethod
    def eject_media(device: str) -> None:
        cmd = None
        if subp.which("eject"):
            cmd = ["eject", device]
        elif subp.which("/lib/udev/cdrom_id"):
            cmd = ["/lib/udev/cdrom_id", "--eject-media", device]
        else:
            raise subp.ProcessExecutionError(
                cmd="eject_media_cmd",
                description="eject command not found",
                reason="neither eject nor /lib/udev/cdrom_id are found",
            )
        subp.subp(cmd)

    @staticmethod
    def get_mapped_device(blockdev: str) -> Optional[str]:
        """Returns underlying block device for a mapped device.

        If it is mapped, blockdev will usually take the form of
        /dev/mapper/some_name

        If blockdev is a symlink pointing to a /dev/dm-* device, return
        the device pointed to. Otherwise, return None.
        """
        realpath = os.path.realpath(blockdev)
        if realpath.startswith("/dev/dm-"):
            LOG.debug(
                "%s is a mapped device pointing to %s", blockdev, realpath
            )
            return realpath
        return None

    @staticmethod
    def device_part_info(devpath: str) -> tuple:
        """convert an entry in /dev/ to parent disk and partition number

        input of /dev/vdb or /dev/disk/by-label/foo
        rpath is hopefully a real-ish path in /dev (vda, sdb..)
        """
        rpath = os.path.realpath(devpath)

        bname = os.path.basename(rpath)
        syspath = "/sys/class/block/%s" % bname

        if not os.path.exists(syspath):
            raise ValueError("%s had no syspath (%s)" % (devpath, syspath))

        ptpath = os.path.join(syspath, "partition")
        if not os.path.exists(ptpath):
            raise TypeError("%s not a partition" % devpath)

        ptnum = util.load_text_file(ptpath).rstrip()

        # for a partition, real syspath is something like:
        # /sys/devices/pci0000:00/0000:00:04.0/virtio1/block/vda/vda1
        rsyspath = os.path.realpath(syspath)
        disksyspath = os.path.dirname(rsyspath)

        diskmajmin = util.load_text_file(
            os.path.join(disksyspath, "dev")
        ).rstrip()
        diskdevpath = os.path.realpath("/dev/block/%s" % diskmajmin)

        # diskdevpath has something like 253:0
        # and udev has put links in /dev/block/253:0 to the device
        # name in /dev/
        return diskdevpath, ptnum


def _apply_hostname_transformations_to_url(url: str, transformations: list):
    """
    Apply transformations to a URL's hostname, return transformed URL.

    This is a separate function because unwrapping and rewrapping only the
    hostname portion of a URL is complex.

    :param url:
        The URL to operate on.
    :param transformations:
        A list of ``(str) -> Optional[str]`` functions, which will be applied
        in order to the hostname portion of the URL.  If any function
        (regardless of ordering) returns None, ``url`` will be returned without
        any modification.

    :return:
        A string whose value is ``url`` with the hostname ``transformations``
        applied, or ``None`` if ``url`` is unparsable.
    """
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        # If we can't even parse the URL, we shouldn't use it for anything
        return None
    new_hostname = parts.hostname
    if new_hostname is None:
        # The URL given doesn't have a hostname component, so (a) we can't
        # transform it, and (b) it won't work as a mirror; return None.
        return None

    for transformation in transformations:
        new_hostname = transformation(new_hostname)
        if new_hostname is None:
            # If a transformation returns None, that indicates we should abort
            # processing and return `url` unmodified
            return url

    new_netloc = new_hostname
    if parts.port is not None:
        new_netloc = "{}:{}".format(new_netloc, parts.port)
    return urllib.parse.urlunsplit(parts._replace(netloc=new_netloc))


def _sanitize_mirror_url(url: str):
    """
    Given a mirror URL, replace or remove any invalid URI characters.

    This performs the following actions on the URL's hostname:
      * Checks if it is an IP address, returning the URL immediately if it is
      * Converts it to its IDN form (see below for details)
      * Replaces any non-Letters/Digits/Hyphen (LDH) characters in it with
        hyphens
      * Removes any leading/trailing hyphens from each domain name label

    Before we replace any invalid domain name characters, we first need to
    ensure that any valid non-ASCII characters in the hostname will not be
    replaced, by ensuring the hostname is in its Internationalized domain name
    (IDN) representation (see RFC 5890).  This conversion has to be applied to
    the whole hostname (rather than just the substitution variables), because
    the Punycode algorithm used by IDNA transcodes each part of the hostname as
    a whole string (rather than encoding individual characters).  It cannot be
    applied to the whole URL, because (a) the Punycode algorithm expects to
    operate on domain names so doesn't output a valid URL, and (b) non-ASCII
    characters in non-hostname parts of the URL aren't encoded via Punycode.

    To put this in RFC 5890's terminology: before we remove or replace any
    characters from our domain name (which we do to ensure that each label is a
    valid LDH Label), we first ensure each label is in its A-label form.

    (Note that Python's builtin idna encoding is actually IDNA2003, not
    IDNA2008.  This changes the specifics of how some characters are encoded to
    ASCII, but doesn't affect the logic here.)

    :param url:
        The URL to operate on.

    :return:
        A sanitized version of the URL, which will have been IDNA encoded if
        necessary, or ``None`` if the generated string is not a parseable URL.
    """
    # Acceptable characters are LDH characters, plus "." to separate each label
    acceptable_chars = LDH_ASCII_CHARS + "."
    transformations = [
        # This is an IP address, not a hostname, so no need to apply the
        # transformations
        lambda hostname: None if net.is_ip_address(hostname) else hostname,
        # Encode with IDNA to get the correct characters (as `bytes`), then
        # decode with ASCII so we return a `str`
        lambda hostname: hostname.encode("idna").decode("ascii"),
        # Replace any unacceptable characters with "-"
        lambda hostname: "".join(
            c if c in acceptable_chars else "-" for c in hostname
        ),
        # Drop leading/trailing hyphens from each part of the hostname
        lambda hostname: ".".join(
            part.strip("-") for part in hostname.split(".")
        ),
    ]

    return _apply_hostname_transformations_to_url(url, transformations)


def _get_package_mirror_info(
    mirror_info, data_source=None, mirror_filter=util.search_for_mirror
):
    # given a arch specific 'mirror_info' entry (from package_mirrors)
    # search through the 'search' entries, and fallback appropriately
    # return a dict with only {name: mirror} entries.
    if not mirror_info:
        mirror_info = {}

    subst = {}
    if data_source and data_source.availability_zone:
        subst["availability_zone"] = data_source.availability_zone

        # ec2 availability zones are named cc-direction-[0-9][a-d] (us-east-1b)
        # the region is us-east-1. so region = az[0:-1]
        if _EC2_AZ_RE.match(data_source.availability_zone):
            ec2_region = data_source.availability_zone[0:-1]

            if ALLOW_EC2_MIRRORS_ON_NON_AWS_INSTANCE_TYPES:
                subst["ec2_region"] = "%s" % ec2_region
            elif data_source.platform_type == "ec2":
                subst["ec2_region"] = "%s" % ec2_region

    if data_source and data_source.region:
        subst["region"] = data_source.region

    results = {}
    for name, mirror in mirror_info.get("failsafe", {}).items():
        results[name] = mirror

    for name, searchlist in mirror_info.get("search", {}).items():
        mirrors = []
        for tmpl in searchlist:
            try:
                mirror = tmpl % subst
            except KeyError:
                continue

            mirror = _sanitize_mirror_url(mirror)
            if mirror is not None:
                mirrors.append(mirror)

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


def fetch(name: str) -> Type[Distro]:
    locs, looked_locs = importer.find_module(name, ["", __name__], ["Distro"])
    if not locs:
        raise ImportError(
            "No distribution found for distro %s (searched %s)"
            % (name, looked_locs)
        )
    mod = importer.import_module(locs[0])
    cls = getattr(mod, "Distro")
    return cls


def set_etc_timezone(
    tz, tz_file=None, tz_conf="/etc/timezone", tz_local="/etc/localtime"
):
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
        res = os.lstat("/run/systemd/system")
        return stat.S_ISDIR(res.st_mode)
    except Exception:
        return False
