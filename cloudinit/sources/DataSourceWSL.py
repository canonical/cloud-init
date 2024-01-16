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
