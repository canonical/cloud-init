"""ansible enables running on first boot either ansible-pull"""
import abc
import os
import re
import sys
import logging
from copy import deepcopy
from logging import Logger
from textwrap import dedent
from typing import Optional

from cloudinit.cloud import Cloud
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.distros import ALL_DISTROS
from cloudinit.settings import PER_INSTANCE
from cloudinit.subp import subp, which
from cloudinit.util import Version, get_cfg_by_path

meta: MetaSchema = {
    "id": "cc_ansible",
    "name": "Ansible",
    "title": "Configure ansible for instance",
    "frequency": PER_INSTANCE,
    "distros": [ALL_DISTROS],
    "activate_by_schema_keys": ["ansible"],
    "description": dedent(
        """\
        This module provides ``ansible`` integration for
        augmenting cloud-init's configuration of the local
        node.


        This module installs ansible during boot and
        then uses ``ansible-pull`` to run the playbook
        repository at the remote URL.
        """
    ),
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
              package-name: ansible-core
              install-method: pip
              pull:
                url: "https://github.com/holmanb/vmboot.git"
                playbook-name: ubuntu.yml
            """
        ),
    ],
}

__doc__ = get_meta_doc(meta)
LOG = logging.getLogger(__name__)


class AnsiblePull(abc.ABC):
    cmd_version: list = []
    cmd_pull: list = []
    env: dict = os.environ.copy()

    def get_version(self) -> Optional[Version]:
        stdout, _ = subp(self.cmd_version, env=self.env)
        first_line = stdout.splitlines().pop(0)
        matches = re.search(r"([\d\.]+)", first_line)
        if matches:
            version = matches.group(0)
            return Version.from_str(version)
        return None

    def pull(self, *args) -> str:
        stdout, _ = subp([*self.cmd_pull, *args], env=self.env)
        return stdout

    def check_deps(self):
        if not self.is_installed():
            raise ValueError("command: ansible is not installed")

    @abc.abstractmethod
    def is_installed(self):
        pass

    @abc.abstractmethod
    def install(self, pkg_name: str):
        pass


class AnsiblePullPip(AnsiblePull):
    def __init__(self):
        self.cmd_pull = ["ansible-pull"]
        self.cmd_version = ["ansible-pull", "--version"]
        self.env["PATH"] = ":".join([self.env["PATH"], "/root/.local/bin/"])

    def install(self, pkg_name: str):
        """should cloud-init grow an interface for non-distro package
        managers? this seems reusable
        """
        if not self.is_installed():
            subp(["python3", "-m", "pip", "install", "--user", pkg_name])

    def is_installed(self) -> bool:
        stdout, _ = subp(["python3", "-m", "pip", "list"])
        return "ansible" in stdout


class AnsiblePullDistro(AnsiblePull):
    def __init__(self, distro):
        self.cmd_pull = ["ansible-pull"]
        self.cmd_version = ["ansible-pull", "--version"]
        self.distro = distro

    def install(self, pkg_name: str):
        if not self.is_installed():
            self.distro.install_packages(pkg_name)

    def is_installed(self) -> bool:
        return bool(which("ansible"))


def handle(name: str, cfg: dict, cloud: Cloud, _, __):
    ansible_cfg: dict = cfg.get("ansible", {})
    if ansible_cfg:
        validate_config(ansible_cfg)
        install = ansible_cfg["install-method"]
        pull_cfg = ansible_cfg.get("pull")
        if pull_cfg:
            ansible: AnsiblePull
            if install == "pip":
                ansible = AnsiblePullPip()
            else:
                ansible = AnsiblePullDistro(cloud.distro)
            ansible.install(ansible_cfg["package-name"])
            ansible.check_deps()
            run_ansible_pull(ansible, deepcopy(pull_cfg))


def validate_config(cfg: dict):
    required_keys = {
        "install-method",
        "package-name",
        "pull/url",
        "pull/playbook-name",
    }
    for key in required_keys:
        if not get_cfg_by_path(cfg, key):
            raise ValueError(f"Invalid value config key: '{key}'")

    install = cfg["install-method"]
    if install not in ("pip", "distro"):
        raise ValueError("Invalid install method {install}")


def filter_args(cfg: dict) -> dict:
    """remove boolean false values"""
    return {key: value for (key, value) in cfg.items() if value is not False}


def run_ansible_pull(pull: AnsiblePull, cfg: dict):
    playbook_name: str = cfg.pop("playbook-name")

    v = pull.get_version()
    if not v:
        LOG.warn("Cannot parse ansible version")
    elif v < Version(2, 7, 0):
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
