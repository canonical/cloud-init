"""ansible enables running on first boot either ansible-pull"""

import enum
import re
import sys
from copy import deepcopy
from logging import Logger
from textwrap import dedent
from typing import NamedTuple, Optional, Tuple

from cloudinit.cloud import Cloud
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.distros import ALL_DISTROS, Distro
from cloudinit.package_manager.pip import Pip
from cloudinit.settings import PER_INSTANCE
from cloudinit.subp import subp, which

meta: MetaSchema = {
    "id": "cc_ansible",
    "name": "Ansible",
    "title": "Configure ansible for instance",
    "description": dedent(
        """\
        This module provides ``ansible`` integration.

        Ansible is often used agentless and in parallel
        across multiple hosts simultaneously. This
        doesn't fit the model of cloud-init: a single
        host configuring itself during boot. Instead,
        this module installs ansible during boot and
        then uses ``ansible-pull`` to run the playbook
        repository at the remote URL.
        """
    ),
    "distros": [ALL_DISTROS],
    "examples": [
        dedent(
            """\
            #cloud-config
            ansible:
              install: true
              pull:
                url: "https://github.com/holmanb/vmboot.git"
                playbook-name: ubuntu.yml
            """
        ),
    ],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": ["ansible"],
}

__doc__ = get_meta_doc(meta)


class InstallMethod(enum.Enum):
    none = enum.auto()
    pip = enum.auto()
    distro = enum.auto()


class Version(NamedTuple):
    major: int
    minor: int
    patch: int


def get_version() -> Optional[Version]:
    stdout, _ = subp(["ansible", "--version"])
    matches = re.search(r"^ansible (\d+)\.(\d+).(\d+)", stdout)
    if matches and matches.lastindex == 3:
        return Version(
            int(matches.group(1)), int(matches.group(2)), int(matches.group(3))
        )
    return None


def compare_version(v1: Version, v2: Version) -> int:
    """
    return values:
        1: v1 > v2
        -1: v1 < v2
        0: v1 == v2
    """
    if v1 == v2:
        return 0
    if v1.major > v2.major:
        return 1
    if v1.minor > v2.minor:
        return 1
    if v1.patch > v2.patch:
        return 1
    return -1


def handle(name: str, cfg: dict, cloud: Cloud, log: Logger, _):
    ansible_cfg: dict = cfg.get("ansible", {})
    if ansible_cfg:
        install, ansible_config = get_and_validate_config(ansible_cfg)
        install_ansible(cloud.distro, install)
        run_ansible_pull(deepcopy(ansible_config), log)


def get_and_validate_config(cfg: dict) -> Tuple[InstallMethod, dict]:
    pull: dict = cfg.get("pull", {})
    try:
        install: InstallMethod = InstallMethod[
            cfg.get("install_method", "none")
        ]
    except KeyError as value:
        raise ValueError(f"Invalid value for 'ansible.install': '{value}'")
    if not all([pull.get("playbook-name"), pull.get("url")]):
        raise ValueError(
            "Missing required key: playbook-name and "
            "url keys required for ansible module"
        )
    return (
        install,
        pull,
    )


def install_ansible(distro: Distro, install: InstallMethod):
    """Give users flexibility in whether to use the package install module or
    this module.
    """
    if install == InstallMethod.distro:
        distro.install_packages("ansible")
    elif install == InstallMethod.distro:
        Pip.install_packages("ansible")


def check_deps(dep: str):
    if not which(dep):
        raise ValueError(
            f"command: {dep} is not available, please set"
            "ansible.install: True in your config or otherwise ensure that"
            "it is installed (either in your base image or in a package"
            "install module)"
        )


def filter_args(cfg: dict) -> dict:
    """remove boolean false values"""
    return {key: value for (key, value) in cfg.items() if value is not False}


def run_ansible_pull(cfg: dict, log: Logger):
    cmd = "ansible-pull"
    check_deps(cmd)
    playbook_name: str = cfg.pop("playbook-name")

    v = get_version()
    if not v:
        log.warn("Cannot parse ansible version")
    elif compare_version(v, Version(2, 7, 0)) != 1:
        # diff was added in commit edaa0b52450ade9b86b5f63097ce18ebb147f46f
        if cfg.get("diff"):
            raise ValueError(
                f"Ansible version {v.major}.{v.minor}.{v.patch}"
                "doesn't support --diff flag, exiting."
            )
    stdout, _ = subp(
        [
            cmd,
            *[
                f"--{key}={value}" if value is not True else f"--{key}"
                for key, value in filter_args(cfg).items()
            ],
            playbook_name,
        ]
    )
    if stdout:
        sys.stdout.write(f"{stdout}")
