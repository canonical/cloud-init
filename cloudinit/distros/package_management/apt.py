# This file is part of cloud-init. See LICENSE file for license information.
import fcntl
import functools
import logging
import os
import re
import time
from typing import Any, Iterable, List, Mapping, Optional, Sequence, cast

from cloudinit import helpers, subp, util
from cloudinit.distros.package_management.package_manager import (
    PackageManager,
    UninstalledPackages,
)
from cloudinit.settings import PER_ALWAYS, PER_INSTANCE

LOG = logging.getLogger(__name__)

APT_GET_COMMAND = (
    "apt-get",
    "--option=Dpkg::Options::=--force-confold",
    "--option=Dpkg::options::=--force-unsafe-io",
    "--assume-yes",
    "--quiet",
)
# The frontend lock needs to be acquired first followed by the order that
# apt uses. /var/lib/apt/lists is locked independently of that install chain,
# and only locked during update, so you can acquire it either order.
# Also update does not acquire the dpkg frontend lock.
# More context:
#   https://github.com/canonical/cloud-init/pull/1034#issuecomment-986971376
APT_LOCK_FILES = [
    "/var/lib/dpkg/lock-frontend",
    "/var/lib/dpkg/lock",
    "/var/cache/apt/archives/lock",
    "/var/lib/apt/lists/lock",
]
APT_LOCK_WAIT_TIMEOUT = 30


def get_apt_wrapper(cfg: Optional[dict]) -> List[str]:
    """Parse the 'apt_get_wrapper' section of cloud-config.

    apt_get_wrapper may be defined in cloud-config:
      apt_get_wrapper:
        enabled: true
        command: ["eatmydata"]

    The function takes the value of "apt_get_wrapper" and returns the list
    of arguments to prefix to the apt-get command.
    """
    enabled: Optional[str]
    command: Optional[Any]
    if not cfg:
        enabled = "auto"
        command = ["eatmydata"]
    else:
        enabled = cfg.get("enabled")
        command = cfg.get("command")

        if isinstance(command, str):
            command = [command]
        elif not isinstance(command, list):
            raise TypeError("apt_wrapper command must be a string or list")

    if util.is_true(enabled) or (
        str(enabled).lower() == "auto" and command and subp.which(command[0])
    ):
        return cast(List[str], command)
    else:
        return []


class Apt(PackageManager):
    name = "apt"

    def __init__(
        self,
        runner: helpers.Runners,
        *,
        apt_get_wrapper_command: Sequence[str] = (),
        apt_get_command: Optional[Sequence[str]] = None,
        apt_get_upgrade_subcommand: Optional[str] = None,
    ):
        super().__init__(runner)
        if apt_get_command is None:
            self.apt_get_command = APT_GET_COMMAND
        if apt_get_upgrade_subcommand is None:
            apt_get_upgrade_subcommand = "dist-upgrade"
        self.apt_command = tuple(apt_get_wrapper_command) + tuple(
            self.apt_get_command
        )

        self.apt_get_upgrade_subcommand = apt_get_upgrade_subcommand
        self.environment = {"DEBIAN_FRONTEND": "noninteractive"}

    @classmethod
    def from_config(cls, runner: helpers.Runners, cfg: Mapping) -> "Apt":
        return Apt(
            runner,
            apt_get_wrapper_command=get_apt_wrapper(
                cfg.get("apt_get_wrapper")
            ),
            apt_get_command=cfg.get("apt_get_command"),
            apt_get_upgrade_subcommand=cfg.get("apt_get_upgrade_subcommand"),
        )

    def available(self) -> bool:
        return bool(subp.which(self.apt_get_command[0]))

    def update_package_sources(self, *, force=False):
        self.runner.run(
            "update-sources",
            self.run_package_command,
            ["update"],
            freq=PER_ALWAYS if force else PER_INSTANCE,
        )

    @functools.lru_cache(maxsize=1)
    def get_all_packages(self):
        resp: str = subp.subp(["apt-cache", "pkgnames"]).stdout

        # Searching the string directly and searching a list are both
        # linear searches. Converting to a set takes some extra up front
        # time, but resulting searches become binary searches and are much
        # faster
        return set(resp.splitlines())

    def get_unavailable_packages(self, pkglist: Iterable[str]):
        # Packages ending with `-` signify to apt to not install a transitive
        # dependency.
        # Packages ending with '^' signify to apt to install a Task.
        # Anything after "/" refers to a target release
        # "=" allows specifying a specific version
        # Strip all off when checking for availability
        return [
            pkg
            for pkg in pkglist
            if re.split("/|=", pkg)[0].rstrip("-^")
            not in self.get_all_packages()
        ]

    def install_packages(self, pkglist: Iterable) -> UninstalledPackages:
        self.update_package_sources()
        pkglist = util.expand_package_list("%s=%s", list(pkglist))
        unavailable = self.get_unavailable_packages(
            [x.split("=")[0] for x in pkglist]
        )
        if unavailable:
            LOG.debug(
                "The following packages were not found by APT so APT will "
                "not attempt to install them: %s",
                unavailable,
            )
        to_install = [p for p in pkglist if p not in unavailable]
        if to_install:
            self.run_package_command("install", pkgs=to_install)
        return unavailable

    def run_package_command(self, command, args=None, pkgs=None):
        if pkgs is None:
            pkgs = []
        full_command = list(self.apt_command)

        if args and isinstance(args, str):
            full_command.append(args)
        elif args and isinstance(args, list):
            full_command.extend(args)

        if command == "upgrade":
            command = self.apt_get_upgrade_subcommand
        full_command.append(command)
        pkglist = util.expand_package_list("%s=%s", pkgs)
        full_command.extend(pkglist)

        self._wait_for_apt_command(
            short_cmd=command,
            subp_kwargs={
                "args": full_command,
                "update_env": self.environment,
                "capture": False,
            },
        )

    def _apt_lock_available(self):
        """Determines if another process holds any apt locks.

        If all locks are clear, return True else False.
        """
        for lock in APT_LOCK_FILES:
            if not os.path.exists(lock):
                # Only wait for lock files that already exist
                continue
            with open(lock, "w") as handle:
                try:
                    fcntl.lockf(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError:
                    return False
        return True

    def _wait_for_apt_command(
        self, short_cmd, subp_kwargs, timeout=APT_LOCK_WAIT_TIMEOUT
    ):
        """Wait for apt install to complete.

        short_cmd: Name of command like "upgrade" or "install"
        subp_kwargs: kwargs to pass to subp
        """
        start_time = time.monotonic()
        LOG.debug("Waiting for APT lock")
        while time.monotonic() - start_time < timeout:
            if not self._apt_lock_available():
                time.sleep(1)
                continue
            LOG.debug("APT lock available")
            try:
                # Allow the output of this to flow outwards (not be captured)
                log_msg = f'apt-{short_cmd} [{" ".join(subp_kwargs["args"])}]'
                return util.log_time(
                    logfunc=LOG.debug,
                    msg=log_msg,
                    func=subp.subp,
                    kwargs=subp_kwargs,
                )
            except subp.ProcessExecutionError:
                # Even though we have already waited for the apt lock to be
                # available, it is possible that the lock was acquired by
                # another process since the check. Since apt doesn't provide
                # a meaningful error code to check and checking the error
                # text is fragile and subject to internationalization, we
                # can instead check the apt lock again. If the apt lock is
                # still available, given the length of an average apt
                # transaction, it is extremely unlikely that another process
                # raced us when we tried to acquire it, so raise the apt
                # error received. If the lock is unavailable, just keep waiting
                if self._apt_lock_available():
                    raise
                LOG.debug("Another process holds APT lock. Waiting...")
                time.sleep(1)
        raise TimeoutError("Could not get APT lock")
