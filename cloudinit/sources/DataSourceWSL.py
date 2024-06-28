# Copyright (C) 2024 Canonical Ltd.
#
# Author: Carlos Nihelton <carlos.santanadeoliveira@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
"""Datasource to support the Windows Subsystem for Linux platform."""

import logging
import os
import typing
from pathlib import PurePath
from typing import Any, List, Optional, Tuple, Union, cast

import yaml

from cloudinit import sources, subp, util
from cloudinit.distros import Distro
from cloudinit.helpers import Paths

LOG = logging.getLogger(__name__)

WSLPATH_CMD = "/usr/bin/wslpath"

DEFAULT_INSTANCE_ID = "iid-datasource-wsl"
LANDSCAPE_DATA_FILE = "%s.user-data"
AGENT_DATA_FILE = "agent.yaml"


def instance_name() -> str:
    """
    Returns the name of the current WSL instance as seen from outside.
    """
    # Translates a path inside the current WSL instance's filesystem to a
    # Windows accessible path.
    # Example:
    # Running under an instance named "CoolInstance"
    # WSLPATH_CMD -am "/" == "//wsl.localhost/CoolInstance/"
    root_net_path, _ = subp.subp([WSLPATH_CMD, "-am", "/"])
    return PurePath(root_net_path.rstrip()).name


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


def find_home() -> PurePath:
    """
    Finds the user's home directory path as a WSL path.

    raises: IOError when no mountpoint with cmd.exe is found
               ProcessExecutionError when either cmd.exe is unable to retrieve
               the user's home directory
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
    # Returns a translation of a Windows path to a Linux path that can be
    # accessed inside the current instance filesystem.
    # Example:
    # Assuming Windows drives are mounted under /mnt/ and "S:" doesn't exist:
    # WSLPATH_CMD -au "C:\\ProgramData" == "/mnt/c/ProgramData/"
    # WSLPATH_CMD -au "S:\\Something" # raises exception S: is not mounted.
    out, _ = subp.subp([WSLPATH_CMD, "-au", home])
    return PurePath(out.rstrip())


def cloud_init_data_dir(user_home: PurePath) -> Optional[PurePath]:
    """
    Returns the Windows user profile .cloud-init directory translated as a
    Linux path accessible inside the current WSL instance, or None if not
    found.
    """
    seed_dir = os.path.join(user_home, ".cloud-init")
    if not os.path.isdir(seed_dir):
        LOG.debug("cloud-init user data dir %s doesn't exist.", seed_dir)
        return None

    return PurePath(seed_dir)


def candidate_user_data_file_names(instance_name) -> List[str]:
    """
    Return a list of candidate file names that may contain user-data
    in some supported format, ordered by precedence.
    """
    distribution_id, version_id, version_codename = util.get_linux_distro()
    version = version_id if version_id else version_codename

    return [
        # WSL instance specific:
        "%s.user-data" % instance_name,
        # release codename specific
        "%s-%s.user-data" % (distribution_id, version),
        # distribution specific (Alpine, Arch, Fedora, openSUSE, Ubuntu...)
        "%s-all.user-data" % distribution_id,
        # generic, valid for all WSL distros and instances.
        "default.user-data",
    ]


def load_yaml_or_bin(data_path: str) -> Optional[Union[dict, bytes]]:
    """
    Tries to load a YAML file as a dict, otherwise returns the file's raw
    binary contents as `bytes`. Returns `None` if no file is found.
    """
    try:
        bin_data = util.load_binary_file(data_path)
        dict_data = util.load_yaml(bin_data)
        if dict_data is None:
            return bin_data

        return dict_data
    except FileNotFoundError:
        LOG.debug("No data found at %s, ignoring.", data_path)

    return None


def load_instance_metadata(
    cloudinitdir: Optional[PurePath], instance_name: str
) -> dict:
    """
    Returns the relevant metadata loaded from cloudinit dir based on the
    instance name
    """
    metadata = {"instance-id": DEFAULT_INSTANCE_ID}
    if cloudinitdir is None:
        return metadata
    metadata_path = os.path.join(
        cloudinitdir.as_posix(), "%s.meta-data" % instance_name
    )

    try:
        metadata = util.load_yaml(util.load_binary_file(metadata_path))
    except FileNotFoundError:
        LOG.debug(
            "No instance metadata found at %s. Using default instance-id.",
            metadata_path,
        )
    if not metadata or "instance-id" not in metadata:
        # Parsed metadata file invalid
        msg = (
            f" Metadata at {metadata_path} does not contain instance-id key."
            f" Instead received: {metadata}"
        )
        LOG.error(msg)
        raise ValueError(msg)

    return metadata


def load_ubuntu_pro_data(
    user_home: PurePath,
) -> Tuple[Union[dict, bytes, None], Union[dict, bytes, None]]:
    """
    Read .ubuntupro user-data if present and return a tuple of agent and
    landscape user-data.
    """
    pro_dir = os.path.join(user_home, ".ubuntupro/.cloud-init")
    if not os.path.isdir(pro_dir):
        return None, None

    landscape_data = load_yaml_or_bin(
        os.path.join(pro_dir, LANDSCAPE_DATA_FILE % instance_name())
    )
    agent_data = load_yaml_or_bin(os.path.join(pro_dir, AGENT_DATA_FILE))
    return agent_data, landscape_data


class DataSourceWSL(sources.DataSource):
    dsname = "WSL"

    def __init__(self, sys_cfg, distro: Distro, paths: Paths, ud_proc=None):
        super().__init__(sys_cfg, distro, paths, ud_proc)
        self.instance_name = ""

    def find_user_data_file(self, seed_dir: PurePath) -> PurePath:
        """
        Finds the most precendent of the candidate files that may contain
        user-data, if any, or None otherwise.
        """

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

    def check_instance_id(self, sys_cfg) -> bool:
        # quickly (local check only) if self.metadata['instance_id']
        # is still valid.
        current = self.get_instance_id()
        if not current:
            return False

        try:
            data_dir = cloud_init_data_dir(find_home())
            metadata = load_instance_metadata(data_dir, instance_name())
            return current == metadata.get("instance-id")

        except (IOError, ValueError) as err:
            LOG.warning(
                "Unable to check_instance_id from metadata file: %s",
                str(err),
            )
            return False

    def _get_data(self) -> bool:
        if not subp.which(WSLPATH_CMD):
            LOG.debug(
                "No WSL command %s found. Cannot detect WSL datasource",
                WSLPATH_CMD,
            )
            return False
        self.instance_name = instance_name()

        try:
            user_home = find_home()
        except IOError as e:
            LOG.debug("Unable to detect WSL datasource: %s", e)
            return False

        seed_dir = cloud_init_data_dir(user_home)
        agent_data = None
        user_data: Optional[Union[dict, bytes]] = None

        # Load any metadata
        try:
            self.metadata = load_instance_metadata(
                seed_dir, self.instance_name
            )
        except (ValueError, IOError) as err:
            LOG.error("Unable to load metadata: %s", str(err))
            return False

        # # Load Ubuntu Pro configs only on Ubuntu distros
        if self.distro.name == "ubuntu":
            agent_data, user_data = load_ubuntu_pro_data(user_home)

        # Load regular user configs
        try:
            if user_data is None and seed_dir is not None:
                file = self.find_user_data_file(seed_dir)
                user_data = load_yaml_or_bin(file.as_posix())
        except (ValueError, IOError) as err:
            LOG.error(
                "Unable to load any user-data file in %s: %s",
                seed_dir,
                str(err),
            )

        # No configs were found
        if not any([user_data, agent_data]):
            return False

        # If we cannot reliably model data files as dicts, then we cannot merge
        # ourselves, so we can pass the data in ascending order as a list for
        # cloud-init to handle internally
        if isinstance(agent_data, bytes) or isinstance(user_data, bytes):
            self.userdata_raw = cast(Any, [user_data, agent_data])
            return True

        # We only care about overriding modules entirely, so we can just
        # iterate over the top level keys and write over them if the agent
        # provides them instead.
        # That's the reason for not using util.mergemanydict().
        merged: dict = {}
        overridden_keys: typing.List[str] = []
        if user_data:
            merged = user_data
        if agent_data:
            if user_data:
                LOG.debug("Merging both user_data and agent.yaml configs.")
            for key in agent_data:
                if key in merged:
                    overridden_keys.append(key)
                merged[key] = agent_data[key]
            if overridden_keys:
                LOG.debug(
                    (
                        " agent.yaml overrides config keys: "
                        ", ".join(overridden_keys)
                    )
                )

        self.userdata_raw = "#cloud-config\n%s" % yaml.dump(merged)
        return True


# Used to match classes to dependencies
datasources = [
    (DataSourceWSL, (sources.DEP_FILESYSTEM,)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
