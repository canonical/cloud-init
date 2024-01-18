# Copyright (C) 2024 Canonical Ltd.
#
# Author: Carlos Nihelton <carlos.santanadeoliveira@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
""" Datasource to support the Windows Subsystem for Linux platform. """

import logging
import os
from pathlib import PurePath
from typing import List, Optional, cast

from cloudinit import sources, subp, util

LOG = logging.getLogger(__name__)

WSLPATH_CMD = "/usr/bin/wslpath"


def wsl_path_2_win(path: str) -> PurePath:
    """
    Translates a path inside the current WSL instance's filesystem to a
    Windows accessible path.

    Example:
    # Running under an instance named "CoolInstance"
    root = wslpath2win("/") # root == "//wsl.localhost/CoolInstance/"

    :param path: string representing a Linux path, whether existing or not.
    """
    out, _ = subp.subp([WSLPATH_CMD, "-am", path])
    return PurePath(out.rstrip())


def instance_name() -> str:
    """
    Returns the name of the current WSL instance as seen from outside.
    """
    root_net_path = wsl_path_2_win("/")
    return root_net_path.name


def mounted_win_drives() -> List[str]:
    """
    Return a list of mount points of the Windows drives inside the current
    WSL instance, if drives are mounted, or an empty list otherwise
    """
    FS_TYPE = "9p"
    OPTIONS_CONTAIN = "aname=drvfs"

    mounts = util.mounts()
    mounted = []
    for mnt in mounts.values():
        if mnt["fstype"] == FS_TYPE and OPTIONS_CONTAIN in mnt["opts"]:
            mounted.append(mnt["mountpoint"])

    return mounted


def win_path_2_wsl(path: str) -> Optional[PurePath]:
    """
    Returns a translation of a Windows path to a Linux path that can be
    accessed inside the current instance filesystem, or None if failed.

    It requires the Windows drive mounting feature to be enabled and the
    disk drive must exist for this to succeed.

    Example:
    # Assuming Windows drives are mounted under /mnt/ and "S:" doesn't exist:
    p = winpath2wsl("C:\\ProgramData") # p == "/mnt/c/ProgramData/"
    n = winpath2wsl("S:\\CoolFolder") # n is None (S doesn't exist)

    :param path: string representing a Windows path. The root drive must exist,
    although the path is not required to.
    """
    out, err = subp.subp([WSLPATH_CMD, "-au", path], rcs=[0, 1])
    if err:
        LOG.debug(err)
        return None

    return PurePath(out.rstrip())


def cmd_executable() -> Optional[PurePath]:
    """
    Returns the Linux path to the Windows host's cmd.exe.
    """

    mounts = mounted_win_drives()
    if not mounts:
        LOG.error("Windows drives are not mounted.")
        return None

    # cmd.exe path is being stable for decades.
    candidate = "%s/Windows/System32/cmd.exe"
    for mnt in mounts:
        cmd = candidate % mnt
        if not os.access(cmd, os.X_OK):
            continue

        LOG.debug("Found cmd.exe at <%s>", cmd)
        return PurePath(cmd)

    LOG.error("Couldn't find cmd.exe in any mount point.")
    return None


def win_user_profile_dir() -> Optional[PurePath]:
    """
    Returns the Windows user profile directory translated as a Linux path
    accessible inside the current WSL instance.
    """
    cmd = cmd_executable()
    if cmd is None:
        return None

    home, _ = subp.subp([cmd.as_posix(), "/C", "echo %USERPROFILE%"])
    home = home.rstrip()
    if not home:
        LOG.error("No output from cmd to show the user profile dir.")
        return None

    return win_path_2_wsl(home.rstrip())


def machine_id():
    """
    Returns the local machine ID value from /etc/machine-id.
    """
    MACHINE_ID_FILE = "/etc/machine-id"

    if util.wait_for_files([MACHINE_ID_FILE], 2.0):
        LOG.debug("%s file not found", MACHINE_ID_FILE)
        return None

    return util.load_file(MACHINE_ID_FILE, decode=True)


def candidate_user_data_file_names(instance_name) -> List[str]:
    """
    Return a list of candidate file names that may contain user-data
    in some supported format, ordered by precedence.
    """
    lsb_rel = util.lsb_release()
    distribution_id = lsb_rel["id"]
    release_codename = lsb_rel["codename"]

    return [
        # WSL instance specific:
        "%s.user-data" % instance_name,
        # release codename specific
        "%s-%s.user-data" % (distribution_id, release_codename),
        # distribution specific (Alpine, Arch, Fedora, openSUSE, Ubuntu...)
        "%s-all.user-data" % distribution_id,
        # generic, valid for all WSL distros and instances.
        "config.user-data",
    ]


class DataSourceWSL(sources.DataSource):
    dsname = "WSL"

    def __init__(self, sys_cfg, distro, paths):
        sources.DataSource.__init__(self, sys_cfg, distro, paths)
        self._network_config = sources.UNSET
        self.dsmode = sources.DSMODE_LOCAL
        self.distro = distro
        self.instance_name = instance_name()

    def find_user_data_file(self) -> Optional[PurePath]:
        """
        Finds the most precendent of the candidate files that may contain
        user-data, if any, or None otherwise.
        """
        profile_dir = win_user_profile_dir()
        if profile_dir is None:
            LOG.warning(
                "Cannot proceed without finding the Windows %USERPROFILE% dir."
            )
            return None

        seed_dir = os.path.join(profile_dir, ".cloud-init")
        if not os.path.isdir(seed_dir):
            LOG.warning("%s directory doesn't exist.", seed_dir)
            return None

        for filename in candidate_user_data_file_names(self.instance_name):
            file = os.path.join(seed_dir, filename)
            if os.path.isfile(file):
                return PurePath(file)

        LOG.warning(
            "%s doesn't contain any of the expected user-data files", seed_dir
        )
        return None

    def _get_data(self) -> bool:
        self.vendordata_raw = None

        self.metadata = dict()
        m_id = machine_id()
        if m_id is None:
            LOG.debug("Instance ID will be the WSL instance name only")
            self.metadata["instance-id"] = self.instance_name
        else:
            self.metadata["instance-id"] = "{}-{}".format(
                self.instance_name, m_id
            )

        file = self.find_user_data_file()
        if file is None:
            self.userdata_raw = None
        else:
            self.userdata_raw = cast(str, util.load_file(file, decode=True))

        return True


# Used to match classes to dependencies
datasources = [
    (DataSourceWSL, (sources.DEP_FILESYSTEM,)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
