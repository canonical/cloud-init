# Copyright (C) 2024 Canonical Ltd.
#
# Author: Carlos Nihelton <carlos.santanadeoliveira@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
""" Datasource to support the Windows Subsystem for Linux platform. """

import logging
import os
from pathlib import PurePath
from typing import List, cast

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

    mounted = []
    for mnt in util.mounts().values():
        if mnt["fstype"] == FS_TYPE and OPTIONS_CONTAIN in mnt["opts"]:
            mounted.append(mnt["mountpoint"])

    return mounted


def win_path_2_wsl(path: str) -> PurePath:
    """
    Returns a translation of a Windows path to a Linux path that can be
    accessed inside the current instance filesystem.

    It requires the Windows drive mounting feature to be enabled and the
    disk drive must be muonted for this to succeed.

    Example:
    # Assuming Windows drives are mounted under /mnt/ and "S:" doesn't exist:
    p = winpath2wsl("C:\\ProgramData") # p == "/mnt/c/ProgramData/"
    n = winpath2wsl("S:\\CoolFolder") # Exception! S: is not mounted.

    :param path: string representing a Windows path. The root drive must exist,
    although the path is not required to.
    """
    out, _ = subp.subp([WSLPATH_CMD, "-au", path])
    return PurePath(out.rstrip())


def cmd_executable() -> PurePath:
    """
    Returns the Linux path to the Windows host's cmd.exe.
    """

    mounts = mounted_win_drives()
    if not mounts:
        raise IOError("Windows drives are not mounted.")

    # cmd.exe path is being stable for decades.
    candidate = "%s/Windows/System32/cmd.exe"
    for mnt in mounts:
        cmd = candidate % mnt
        if not os.access(cmd, os.X_OK):
            continue

        LOG.debug("Found cmd.exe at <%s>", cmd)
        return PurePath(cmd)

    raise IOError(
        "Couldn't find cmd.exe in any mount point: %s" % ", ".join(mounts)
    )


def cloud_init_data_dir() -> PurePath:
    """
    Returns the Windows user profile directory translated as a Linux path
    accessible inside the current WSL instance.
    """
    cmd = cmd_executable()

    # cloud-init runs too early to rely on binfmt to execute Windows binaries.
    # But we know that `/init` is the interpreter, so we can run it directly.
    # See /proc/sys/fs/binfmt_misc/WSLInterop[-late]
    # inside any WSL instance for more details.
    home, _ = subp.subp(["/init", cmd.as_posix(), "/C", "echo %USERPROFILE%"])
    home = home.rstrip()
    if not home:
        raise subp.ProcessExecutionError(
            "No output from cmd.exe to show the user profile dir."
        )

    win_profile_dir = win_path_2_wsl(home)
    seed_dir = os.path.join(win_profile_dir, ".cloud-init")
    if not os.path.isdir(seed_dir):
        raise FileNotFoundError("%s directory doesn't exist." % seed_dir)

    return PurePath(seed_dir)


def machine_id():
    """
    Returns the local machine ID value from /etc/machine-id.
    """
    from cloudinit.settings import MACHINE_ID_FILE

    try:
        return util.load_binary_file(MACHINE_ID_FILE)
    except OSError as err:
        LOG.error(err)
        return None


def candidate_user_data_file_names(instance_name) -> List[str]:
    """
    Return a list of candidate file names that may contain user-data
    in some supported format, ordered by precedence.
    """
    distribution_id, version_id, _ = util.get_linux_distro()

    return [
        # WSL instance specific:
        "%s.user-data" % instance_name,
        # release codename specific
        "%s-%s.user-data" % (distribution_id, version_id),
        # distribution specific (Alpine, Arch, Fedora, openSUSE, Ubuntu...)
        "%s-all.user-data" % distribution_id,
        # generic, valid for all WSL distros and instances.
        "default.user-data",
    ]


class DataSourceWSL(sources.DataSource):
    dsname = "WSL"

    def find_user_data_file(self) -> PurePath:
        """
        Finds the most precendent of the candidate files that may contain
        user-data, if any, or None otherwise.
        """
        seed_dir = cloud_init_data_dir()

        # Notice that by default file name casing is irrelevant here. Windows
        # filenames are case insensitive. Even though accessed through Linux,
        # path translation just works with whichever casing we try.
        # But users can change that behavior with configuration
        # (ref https://learn.microsoft.com/en-us/windows/wsl/case-sensitivity),
        # thus  better prevent it by always relying on case insensitive match.
        existing_files = {
            ef.name.casefold(): ef.path for ef in os.scandir(seed_dir)
        }
        if not existing_files:
            raise IOError("%s directory is empty" % seed_dir)

        folded_names = [
            f.casefold()
            for f in candidate_user_data_file_names(self.instance_name)
        ]
        for filename in folded_names:
            if filename in existing_files.keys():
                return PurePath(existing_files[filename])

        raise IOError(
            "%s doesn't contain any of the expected user-data files" % seed_dir
        )

    def _get_data(self) -> bool:
        self.vendordata_raw = None
        self.instance_name = instance_name()

        self.metadata = dict()
        m_id = machine_id()
        if m_id is None:
            LOG.debug("Instance ID will be the WSL instance name only")
            self.metadata["instance-id"] = self.instance_name
        else:
            self.metadata["instance-id"] = "{}-{}".format(
                self.instance_name, m_id
            )

        try:
            file = self.find_user_data_file()
            self.userdata_raw = cast(
                str, util.load_binary_file(file.as_posix())
            )
            return True
        except IOError as err:
            LOG.error("Could not find any user data file: %s", str(err))
            self.userdata_raw = ""
            return False


# Used to match classes to dependencies
datasources = [
    (DataSourceWSL, (sources.DEP_FILESYSTEM,)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
