"""ansible enables running on first boot either ansible-pull"""
import os
import re
import sys
from copy import deepcopy
from logging import Logger
from textwrap import dedent
from typing import NamedTuple, Optional

from cloudinit.cloud import Cloud
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.distros import ALL_DISTROS
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
              install-method: distro
              pull:
                url: "https://github.com/holmanb/vmboot.git"
                playbook-name: ubuntu.yml
            """
        ),
        dedent(
            """\
            #cloud-config
            ansible:
              install-method: pip
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


class Version(NamedTuple):
    major: int
    minor: int
    patch: int


class AnsiblePull:
    cmd_version: list = []
    cmd_pull: list = []
    env = os.environ.copy()

    def get_version(self) -> Optional[Version]:
        stdout, _ = subp(self.cmd_version, env=self.env)
        matches = re.search(
            r"^ansible.*(\d+)\.(\d+).(\d+).*", stdout.splitlines().pop(0)
        )
        if matches and matches.lastindex == 3:
            print(matches.lastindex)
            return Version(
                int(matches.group(1)),
                int(matches.group(2)),
                int(matches.group(3)),
            )
        return None

    def pull(self, *args) -> str:
        stdout, _ = subp([*self.cmd_pull, *args], env=self.env)
        return stdout

    def check_deps(self):
        if not self.is_installed():
            raise ValueError("command: ansible is not installed")

    def is_installed(self):
        raise NotImplementedError()

    def install(self):
        raise NotImplementedError()


class AnsiblePullPip(AnsiblePull):
    def __init__(self):
        self.cmd_pull = ["ansible-pull"]
        self.cmd_version = ["ansible-pull", "--version"]
        self.env["PATH"] = ":".join([self.env["PATH"], "/root/.local/bin/"])

    def install(self):
        """should cloud-init grow an interface for non-distro package
        managers? this seems reusable
        """
        if not self.is_installed():
            subp(["python3", "-m", "pip", "install", "--user", "ansible"])

    def is_installed(self) -> bool:
        stdout, _ = subp(["python3", "-m", "pip", "list"])
        return "ansible" in stdout


class AnsiblePullDistro(AnsiblePull):
    def __init__(self, distro):
        self.cmd_pull = ["ansible-pull"]
        self.cmd_version = ["ansible-pull", "--version"]
        self.distro = distro

    def install(self):
        if not self.is_installed():
            self.distro.install_packages("ansible")

    def is_installed(self) -> bool:
        return bool(which("ansible"))


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
        validate_config(ansible_cfg)
        install = ansible_cfg["install-method"]
        pull_cfg = ansible_cfg.get("pull")
        if pull_cfg:
            if install == "pip":
                ansible = AnsiblePullPip()
            else:
                ansible = AnsiblePullDistro(cloud.distro)
            ansible.install()
            ansible.check_deps()
            run_ansible_pull(ansible, deepcopy(pull_cfg), log)


def validate_config(cfg: dict):
    try:
        cfg["install-method"]
        pull_cfg: dict = cfg.get("pull", {})
        if pull_cfg:
            pull_cfg["url"]
            pull_cfg["playbook-name"]
    except KeyError as value:
        raise ValueError(f"Invalid value config key: '{value}'")

    install = cfg["install-method"]
    if install not in ("pip", "distro"):
        raise ValueError("Invalid install method {install}")


def filter_args(cfg: dict) -> dict:
    """remove boolean false values"""
    return {key: value for (key, value) in cfg.items() if value is not False}


def run_ansible_pull(pull: AnsiblePull, cfg: dict, log: Logger):
    playbook_name: str = cfg.pop("playbook-name")

    v = pull.get_version()
    if not v:
        log.warn("Cannot parse ansible version")
    elif compare_version(v, Version(2, 7, 0)) != 1:
        # diff was added in commit edaa0b52450ade9b86b5f63097ce18ebb147f46f
        if cfg.get("diff"):
            raise ValueError(
                f"Ansible version {v.major}.{v.minor}.{v.patch}"
                "doesn't support --diff flag, exiting."
            )
    stdout = pull.pull(
        *[
            f"--{key}={value}" if value is not True else f"--{key}"
            for key, value in filter_args(cfg).items()
        ],
        playbook_name,
    )
    if stdout:
        sys.stdout.write(f"{stdout}")
