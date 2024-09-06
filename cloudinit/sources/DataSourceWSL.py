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
from typing import List, Optional, Tuple

import yaml

from cloudinit import sources, subp, util
from cloudinit.distros import Distro
from cloudinit.handlers import type_from_starts_with
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


class ConfigData:
    """Models a piece of configuration data as a dict if possible, while
    retaining its raw representation alongside its file path"""

    def __init__(self, path: PurePath):
        self.raw: str = util.load_text_file(path)
        self.path: PurePath = path

        self.config_dict: Optional[dict] = None

        if "text/cloud-config" == type_from_starts_with(self.raw):
            self.config_dict = util.load_yaml(self.raw)

    def is_cloud_config(self) -> bool:
        return self.config_dict is not None


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
        metadata = util.load_yaml(util.load_text_file(metadata_path))
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
) -> Tuple[Optional[ConfigData], Optional[ConfigData]]:
    """
    Read .ubuntupro user-data if present and return a tuple of agent and
    landscape user-data.
    """
    pro_dir = os.path.join(user_home, ".ubuntupro/.cloud-init")
    if not os.path.isdir(pro_dir):
        return None, None

    landscape_path = PurePath(
        os.path.join(pro_dir, LANDSCAPE_DATA_FILE % instance_name())
    )
    landscape_data = None
    if os.path.isfile(landscape_path):
        LOG.debug(
            "Landscape configuration found: %s. Organization policy "
            "ignores any local user-data in %s.",
            landscape_path,
            cloud_init_data_dir(user_home),
        )
        landscape_data = ConfigData(landscape_path)

    agent_path = PurePath(os.path.join(pro_dir, AGENT_DATA_FILE))
    agent_data = None
    if os.path.isfile(agent_path):
        agent_data = ConfigData(agent_path)

    return agent_data, landscape_data


def merge_agent_landscape_data(
    agent_data: Optional[ConfigData], user_data: Optional[ConfigData]
) -> Optional[str]:
    """Merge agent.yaml data provided by Ubuntu Pro for WSL
    and user data provided either by Landscape or the local user,
    according to the UP4W specific rules.

    When merging is not possible, provide #include directive to allow
    cloud-init to merge separate parts.
    """
    # Ignore agent_data if None or empty
    if agent_data is None or len(agent_data.raw) == 0:
        if user_data is None or len(user_data.raw) == 0:
            return None
        return user_data.raw

    # Ignore user_data if None or empty
    if user_data is None or len(user_data.raw) == 0:
        if agent_data is None or len(agent_data.raw) == 0:
            return None
        return agent_data.raw

    # If both are found but we cannot reliably model both data files as
    # cloud-config dicts, then we cannot merge them ourselves, so we should
    # pass the data as if the user had written an include file
    # for cloud-init to handle internally. We explicitely prioritize the
    # agent data, to ensure cloud-init would handle it even in the presence
    # of syntax errors in user data (agent data is autogenerated).
    # It's possible that the effects caused by the user data would override
    # the agent data, but that's the user's ultimately responsibility.
    # The alternative of writing the user data first would make it possible
    # for the agent data to be skipped in the presence of syntax errors in
    # user data.

    if not all([agent_data.is_cloud_config(), user_data.is_cloud_config()]):
        LOG.debug(
            "Unable to merge {agent_data.path} and {user_data.path}. "
            "Providing as separate user-data #include."
        )
        return "#include\n%s\n%s\n" % (
            agent_data.path.as_posix(),
            user_data.path.as_posix(),
        )

    # We only care about overriding top-level config keys entirely, so we
    # can just iterate over the top level keys and write over them if the
    # agent provides them instead.
    # That's the reason for not using util.mergemanydict().
    merged: dict = {}
    user_tags: str = ""
    overridden_keys: typing.List[str] = []
    if isinstance(user_data.config_dict, dict):
        merged = user_data.config_dict
        user_tags = (
            merged.get("landscape", {}).get("client", {}).get("tags", "")
        )
    if isinstance(agent_data.config_dict, dict):
        if user_data:
            LOG.debug("Merging both user_data and agent.yaml configs.")
        agent = agent_data.config_dict
        for key in agent:
            if key in merged:
                overridden_keys.append(key)
            merged[key] = agent[key]
        if overridden_keys:
            LOG.debug(
                (
                    " agent.yaml overrides config keys: "
                    ", ".join(overridden_keys)
                )
            )
        if user_tags and merged.get("landscape", {}).get("client"):
            LOG.debug(
                "Landscape client conf updated with user-data"
                " landscape.client.tags: %s",
                user_tags,
            )
            merged["landscape"]["client"]["tags"] = user_tags

    return (
        "#cloud-config\n# WSL datasouce Merged agent.yaml and user_data\n%s"
        % yaml.dump(merged).strip()
    )


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
        agent_data: Optional[ConfigData] = None
        user_data: Optional[ConfigData] = None

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
                user_data = ConfigData(self.find_user_data_file(seed_dir))

        except (ValueError, IOError) as err:
            log = LOG.info if agent_data else LOG.error
            log(
                "Unable to load any user-data file in %s: %s",
                seed_dir,
                str(err),
            )

        # No configs were found
        if not any([user_data, agent_data]):
            return False

        self.userdata_raw = merge_agent_landscape_data(agent_data, user_data)
        return True


# Used to match classes to dependencies
datasources = [
    (DataSourceWSL, (sources.DEP_FILESYSTEM,)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
