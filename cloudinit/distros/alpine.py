# Copyright (C) 2016 Matt Dainty
# Copyright (C) 2020 Dermot Bradley
#
# Author: Matt Dainty <matt@bodgit-n-scarper.com>
# Author: Dermot Bradley <dermot_bradley@yahoo.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import logging
import os
import re
import stat
from datetime import datetime
from typing import Any, Dict, Optional

from cloudinit import distros, helpers, subp, util
from cloudinit.distros.parsers.hostname import HostnameConf
from cloudinit.settings import PER_ALWAYS, PER_INSTANCE

LOG = logging.getLogger(__name__)

NETWORK_FILE_HEADER = """\
# This file is generated from information provided by the datasource. Changes
# to it will not persist across an instance reboot. To disable cloud-init's
# network configuration capabilities, write a file
# /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg with the following:
# network: {config: disabled}

"""


class Distro(distros.Distro):
    pip_package_name = "py3-pip"
    keymap_path = "/usr/share/bkeymaps/"
    locale_conf_fn = "/etc/profile.d/50-cloud-init-locale.sh"
    network_conf_fn = "/etc/network/interfaces"
    shadow_fn = "/etc/shadow"
    renderer_configs = {
        "eni": {"eni_path": network_conf_fn, "eni_header": NETWORK_FILE_HEADER}
    }
    # Alpine stores dhclient leases at following location:
    # /var/lib/dhcp/dhclient.leases
    dhclient_lease_directory = "/var/lib/dhcp"
    dhclient_lease_file_regex = r"dhclient\.leases"

    def __init__(self, name, cfg, paths):
        distros.Distro.__init__(self, name, cfg, paths)
        # This will be used to restrict certain
        # calls from repeatedly happening (when they
        # should only happen say once per instance...)
        self._runner = helpers.Runners(paths)
        self.default_locale = "C.UTF-8"
        self.osfamily = "alpine"
        cfg["ssh_svcname"] = "sshd"

    def get_locale(self):
        """The default locale for Alpine Linux is different than
        cloud-init's DataSource default.
        """
        return self.default_locale

    def apply_locale(self, locale, out_fn=None):
        # Alpine has limited locale support due to musl library limitations

        if not locale:
            locale = self.default_locale
        if not out_fn:
            out_fn = self.locale_conf_fn

        lines = [
            "#",
            "# This file is created by cloud-init once per new instance boot",
            "#",
            "export CHARSET=UTF-8",
            "export LANG=%s" % locale,
            "export LC_COLLATE=C",
            "",
        ]
        util.write_file(out_fn, "\n".join(lines), 0o644)

    def install_packages(self, pkglist: distros.PackageList):
        self.update_package_sources()
        self.package_command("add", pkgs=pkglist)

    def _write_hostname(self, hostname, filename):
        conf = None
        try:
            # Try to update the previous one
            # so lets see if we can read it first.
            conf = self._read_hostname_conf(filename)
        except IOError:
            create_hostname_file = util.get_cfg_option_bool(
                self._cfg, "create_hostname_file", True
            )
            if create_hostname_file:
                pass
            else:
                LOG.info(
                    "create_hostname_file is False; hostname file not created"
                )
                return
        if not conf:
            conf = HostnameConf("")
        conf.set_hostname(hostname)
        util.write_file(filename, str(conf), 0o644)

    def _read_system_hostname(self):
        sys_hostname = self._read_hostname(self.hostname_conf_fn)
        return (self.hostname_conf_fn, sys_hostname)

    def _read_hostname_conf(self, filename):
        conf = HostnameConf(util.load_text_file(filename))
        conf.parse()
        return conf

    def _read_hostname(self, filename, default=None):
        hostname = None
        try:
            conf = self._read_hostname_conf(filename)
            hostname = conf.hostname
        except IOError:
            pass
        if not hostname:
            return default
        return hostname

    def _get_localhost_ip(self):
        return "127.0.1.1"

    def set_keymap(self, layout: str, model: str, variant: str, options: str):
        if not layout:
            msg = "Keyboard layout not specified."
            LOG.error(msg)
            raise RuntimeError(msg)
        keymap_layout_path = os.path.join(self.keymap_path, layout)
        if not os.path.isdir(keymap_layout_path):
            msg = (
                "Keyboard layout directory %s does not exist."
                % keymap_layout_path
            )
            LOG.error(msg)
            raise RuntimeError(msg)
        if not variant:
            msg = "Keyboard variant not specified."
            LOG.error(msg)
            raise RuntimeError(msg)
        keymap_variant_path = os.path.join(
            keymap_layout_path, "%s.bmap.gz" % variant
        )
        if not os.path.isfile(keymap_variant_path):
            msg = (
                "Keyboard variant file %s does not exist."
                % keymap_variant_path
            )
            LOG.error(msg)
            raise RuntimeError(msg)
        if model:
            LOG.warning("Keyboard model is ignored for Alpine Linux.")
        if options:
            LOG.warning("Keyboard options are ignored for Alpine Linux.")

        subp.subp(["setup-keymap", layout, variant])

    def set_timezone(self, tz):
        distros.set_etc_timezone(tz=tz, tz_file=self._find_tz_file(tz))

    def package_command(self, command, args=None, pkgs=None):
        if pkgs is None:
            pkgs = []

        cmd = ["apk"]
        # Redirect output
        cmd.append("--quiet")

        if args and isinstance(args, str):
            cmd.append(args)
        elif args and isinstance(args, list):
            cmd.extend(args)

        if command:
            cmd.append(command)

        if command == "upgrade":
            cmd.extend(["--update-cache", "--available"])

        pkglist = util.expand_package_list("%s-%s", pkgs)
        cmd.extend(pkglist)

        # Allow the output of this to flow outwards (ie not be captured)
        subp.subp(cmd, capture=False)

    def update_package_sources(self, *, force=False):
        self._runner.run(
            "update-sources",
            self.package_command,
            ["update"],
            freq=PER_ALWAYS if force else PER_INSTANCE,
        )

    @property
    def preferred_ntp_clients(self):
        """Allow distro to determine the preferred ntp client list"""
        if not self._preferred_ntp_clients:
            self._preferred_ntp_clients = ["chrony", "ntp"]

        return self._preferred_ntp_clients

    def add_user(self, name, **kwargs):
        """
        Add a user to the system using standard tools

        On Alpine this may use either 'useradd' or 'adduser' depending
        on whether the 'shadow' package is installed.
        """
        if util.is_user(name):
            LOG.info("User %s already exists, skipping.", name)
            return

        if "selinux_user" in kwargs:
            LOG.warning("Ignoring selinux_user parameter for Alpine Linux")
            del kwargs["selinux_user"]

        # If 'useradd' is available then use the generic
        # add_user function from __init__.py instead.
        if subp.which("useradd"):
            return super().add_user(name, **kwargs)

        create_groups = kwargs.pop("create_groups", True)

        adduser_cmd = ["adduser", "-D"]

        # Since we are creating users, we want to carefully validate
        # the inputs. If something goes wrong, we can end up with a
        # system that nobody can login to.
        adduser_opts = {
            "gecos": "-g",
            "homedir": "-h",
            "primary_group": "-G",
            "shell": "-s",
            "uid": "-u",
        }

        adduser_flags = {"system": "-S"}

        # support kwargs having groups=[list] or groups="g1,g2"
        groups = kwargs.get("groups")
        if groups:
            if isinstance(groups, str):
                groups = groups.split(",")
            elif isinstance(groups, dict):
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

            if kwargs.get("primary_group"):
                groups.append(kwargs["primary_group"])

        if create_groups and groups:
            for group in groups:
                if not util.is_group(group):
                    self.create_group(group)
                    LOG.debug("created group '%s' for user '%s'", group, name)
        if "uid" in kwargs:
            kwargs["uid"] = str(kwargs["uid"])

        unsupported_busybox_values: Dict[str, Any] = {
            "groups": [],
            "expiredate": None,
            "inactive": None,
            "passwd": None,
        }

        # Check the values and create the command
        for key, val in sorted(kwargs.items()):
            if key in adduser_opts and val and isinstance(val, str):
                adduser_cmd.extend([adduser_opts[key], val])
            elif (
                key in unsupported_busybox_values
                and val
                and isinstance(val, str)
            ):
                # Busybox's 'adduser' does not support specifying these
                # options so store them for use via alternative means.
                if key == "groups":
                    unsupported_busybox_values[key] = val.split(",")
                else:
                    unsupported_busybox_values[key] = val
            elif key in adduser_flags and val:
                adduser_cmd.append(adduser_flags[key])

        # Don't create the home directory if directed so
        # or if the user is a system user
        if kwargs.get("no_create_home") or kwargs.get("system"):
            adduser_cmd.append("-H")

        # Busybox's 'adduser' puts username at end of command
        adduser_cmd.append(name)

        # Run the command
        LOG.debug("Adding user %s", name)
        try:
            subp.subp(adduser_cmd)
        except subp.ProcessExecutionError as e:
            LOG.warning("Failed to create user %s", name)
            raise e

        # Process remaining options that Busybox's 'adduser' does not support

        # Separately add user to each additional group as Busybox's
        # 'adduser' does not support specifying additional groups.
        for addn_group in unsupported_busybox_values[
            "groups"
        ]:  # pylint: disable=E1133
            LOG.debug("Adding user to group %s", addn_group)
            try:
                subp.subp(["addgroup", name, addn_group])
            except subp.ProcessExecutionError as e:
                util.logexc(
                    LOG, "Failed to add user %s to group %s", name, addn_group
                )
                raise e

        if unsupported_busybox_values["passwd"]:
            # Separately set password as Busybox's 'adduser' does
            # not support passing password as CLI option.
            super().set_passwd(
                name, unsupported_busybox_values["passwd"], hashed=True
            )

        # Busybox's 'adduser' is hardcoded to always set the following field
        # values (numbered from "0") in /etc/shadow unlike 'useradd':
        #
        # Field                          Value set
        #
        #   3    minimum password age    0 (no min age)
        #   4    maximum password age    99999 (days)
        #   5    warning period          7 (warn days before max age)
        #
        # so modify these fields to be empty.
        #
        # Also set expiredate (field '7') and/or inactive (field '6')
        # values directly in /etc/shadow file as Busybox's 'adduser'
        # does not support passing these as CLI options.

        expiredate = unsupported_busybox_values["expiredate"]
        inactive = unsupported_busybox_values["inactive"]

        shadow_contents = None
        shadow_file = self.shadow_fn
        try:
            shadow_contents = util.load_text_file(shadow_file)
        except FileNotFoundError as e:
            LOG.warning("Failed to read %s file, file not found", shadow_file)
            raise e

        # Find the line in /etc/shadow for the user
        original_line = None
        for line in shadow_contents.splitlines():
            new_line_parts = line.split(":")
            if new_line_parts[0] == name:
                original_line = line
                break

        if original_line:
            # Modify field(s) in copy of user's shadow file entry
            update_type = ""

            # Minimum password age
            new_line_parts[3] = ""
            # Maximum password age
            new_line_parts[4] = ""
            # Password warning period
            new_line_parts[5] = ""
            update_type = "password aging"

            if expiredate is not None:
                # Convert date into number of days since 1st Jan 1970
                days = (
                    datetime.fromisoformat(expiredate)
                    - datetime.fromisoformat("1970-01-01")
                ).days
                new_line_parts[7] = str(days)
                if update_type != "":
                    update_type = update_type + " & "
                update_type = update_type + "acct expiration date"
            if inactive is not None:
                new_line_parts[6] = inactive
                if update_type != "":
                    update_type = update_type + " & "
                update_type = update_type + "inactivity period"

            # Replace existing line for user with modified line
            shadow_contents = shadow_contents.replace(
                original_line, ":".join(new_line_parts)
            )
            LOG.debug("Updating %s for user %s", update_type, name)
            try:
                util.write_file(
                    shadow_file, shadow_contents, omode="w", preserve_mode=True
                )
            except IOError as e:
                util.logexc(LOG, "Failed to update %s file", shadow_file)
                raise e
        else:
            util.logexc(
                LOG, "Failed to update %s for user %s", shadow_file, name
            )

    def lock_passwd(self, name):
        """
        Lock the password of a user, i.e., disable password logins
        """

        # Check whether Shadow's or Busybox's version of 'passwd'.
        # If Shadow's 'passwd' is available then use the generic
        # lock_passwd function from __init__.py instead.
        if not os.path.islink(
            "/usr/bin/passwd"
        ) or "bbsuid" not in os.readlink("/usr/bin/passwd"):
            return super().lock_passwd(name)

        cmd = ["passwd", "-l", name]
        # Busybox's 'passwd', unlike Shadow's 'passwd', errors
        # if password is already locked:
        #
        #   "passwd: password for user2 is already locked"
        #
        # with exit code 1
        try:
            (_out, err) = subp.subp(cmd, rcs=[0, 1])
            if re.search(r"is already locked", err):
                return True
        except subp.ProcessExecutionError as e:
            util.logexc(LOG, "Failed to disable password for user %s", name)
            raise e

    def expire_passwd(self, user):
        # Check whether Shadow's or Busybox's version of 'passwd'.
        # If Shadow's 'passwd' is available then use the generic
        # expire_passwd function from __init__.py instead.
        if not os.path.islink(
            "/usr/bin/passwd"
        ) or "bbsuid" not in os.readlink("/usr/bin/passwd"):
            return super().expire_passwd(user)

        # Busybox's 'passwd' does not provide an expire option
        # so have to manipulate the shadow file directly.
        shadow_contents = None
        shadow_file = self.shadow_fn
        try:
            shadow_contents = util.load_text_file(shadow_file)
        except FileNotFoundError as e:
            LOG.warning("Failed to read %s file, file not found", shadow_file)
            raise e

        # Find the line in /etc/shadow for the user
        original_line = None
        for line in shadow_contents.splitlines():
            new_line_parts = line.split(":")
            if new_line_parts[0] == user:
                LOG.debug("Found /etc/shadow line matching user %s", user)
                original_line = line
                break

        if original_line:
            # Replace existing line for user with modified line
            #
            # Field '2' (numbered from '0') in /etc/shadow
            # is the "date of last password change".
            if new_line_parts[2] != "0":
                # Busybox's 'adduser' always expires password so only
                # need to expire it now if this is not a new user.
                new_line_parts[2] = "0"
                shadow_contents = shadow_contents.replace(
                    original_line, ":".join(new_line_parts), 1
                )

                LOG.debug("Expiring password for user %s", user)
                try:
                    util.write_file(
                        shadow_file,
                        shadow_contents,
                        omode="w",
                        preserve_mode=True,
                    )
                except IOError as e:
                    util.logexc(LOG, "Failed to update %s file", shadow_file)
                    raise e
            else:
                LOG.debug("Password for user %s is already expired", user)
        else:
            util.logexc(LOG, "Failed to set 'expire' for %s", user)

    def create_group(self, name, members=None):
        # If 'groupadd' is available then use the generic
        # create_group function from __init__.py instead.
        if subp.which("groupadd"):
            return super().create_group(name, members)

        group_add_cmd = ["addgroup", name]
        if not members:
            members = []

        # Check if group exists, and then add if it doesn't
        if util.is_group(name):
            LOG.warning("Skipping creation of existing group '%s'", name)
        else:
            try:
                subp.subp(group_add_cmd)
                LOG.info("Created new group %s", name)
            except subp.ProcessExecutionError:
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

                subp.subp(["addgroup", member, name])
                LOG.info("Added user '%s' to group '%s'", member, name)

    def shutdown_command(self, mode="poweroff", delay="now", message=None):
        # called from cc_power_state_change.load_power_state
        # Alpine has halt/poweroff/reboot, with the following specifics:
        # - we use them rather than the generic "shutdown"
        # - delay is given with "-d [integer]"
        # - the integer is in seconds, cannot be "now", and takes no "+"
        # - no message is supported (argument ignored, here)

        command = [mode, "-d"]

        # Convert delay from minutes to seconds, as Alpine's
        # halt/poweroff/reboot commands take seconds rather than minutes.
        if delay == "now":
            # Alpine's commands do not understand "now".
            command += ["0"]
        else:
            try:
                command.append(str(int(delay) * 60))
            except ValueError as e:
                raise TypeError(
                    "power_state[delay] must be 'now' or '+m' (minutes)."
                    " found '%s'." % (delay,)
                ) from e

        return command

    @staticmethod
    def uses_systemd():
        """
        Alpine uses OpenRC, not systemd
        """
        return False

    @classmethod
    def manage_service(
        self, action: str, service: str, *extra_args: str, rcs=None
    ):
        """
        Perform the requested action on a service. This handles OpenRC
        specific implementation details.

        OpenRC has two distinct commands relating to services,
        'rc-service' and 'rc-update' and the order of their argument
        lists differ.
        May raise ProcessExecutionError
        """
        init_cmd = ["rc-service", "--nocolor"]
        update_cmd = ["rc-update", "--nocolor"]
        cmds = {
            "stop": list(init_cmd) + [service, "stop"],
            "start": list(init_cmd) + [service, "start"],
            "disable": list(update_cmd) + ["del", service],
            "enable": list(update_cmd) + ["add", service],
            "restart": list(init_cmd) + [service, "restart"],
            "reload": list(init_cmd) + [service, "restart"],
            "try-reload": list(init_cmd) + [service, "restart"],
            "status": list(init_cmd) + [service, "status"],
        }
        cmd = list(cmds[action])
        return subp.subp(cmd, capture=True, rcs=rcs)

    @staticmethod
    def get_mapped_device(blockdev: str) -> Optional[str]:
        """Returns underlying block device for a mapped device.

        If it is mapped, blockdev will usually take the form of
        /dev/mapper/some_name

        If blockdev is a symlink pointing to a /dev/dm-* device, return
        the device pointed to. Otherwise, return None.
        """
        realpath = os.path.realpath(blockdev)

        if blockdev.startswith("/dev/mapper"):
            # For Alpine systems a /dev/mapper/ entry is *not* a
            # symlink to the related /dev/dm-X block device,
            # rather it is a  block device itself.

            # Get the major/minor of the /dev/mapper block device
            major = os.major(os.stat(blockdev).st_rdev)
            minor = os.minor(os.stat(blockdev).st_rdev)

            # Find the /dev/dm-X device with the same major/minor
            with os.scandir("/dev/") as it:
                for deventry in it:
                    if deventry.name.startswith("dm-"):
                        res = os.lstat(deventry.path)
                        if stat.S_ISBLK(res.st_mode):
                            if (
                                os.major(os.stat(deventry.path).st_rdev)
                                == major
                                and os.minor(os.stat(deventry.path).st_rdev)
                                == minor
                            ):
                                realpath = os.path.realpath(deventry.path)
                                break

        if realpath.startswith("/dev/dm-"):
            LOG.debug(
                "%s is a mapped device pointing to %s", blockdev, realpath
            )
            return realpath
        return None
