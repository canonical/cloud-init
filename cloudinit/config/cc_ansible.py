"""ansible enables running on first boot either ansible-pull"""
import abc
from logging import Logger, getLogger
import os
import re
import sys
from copy import deepcopy
from textwrap import dedent
from typing import Optional

from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.distros import ALL_DISTROS, Distro
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
LOG = getLogger(__name__)
PIP_PKG = "python3-pip"
CFG_OVERRIDE = "ANSIBLE_CONFIG"


class AnsiblePull(abc.ABC):
    def __init__(self, distro: Distro):
        self.cmd_pull = ["ansible-pull"]
        self.cmd_version = ["ansible-pull", "--version"]
        self.distro = distro
        self.env = os.environ.copy()

    def get_version(self) -> Optional[Version]:
        stdout, _ = self.subp(self.cmd_version)
        first_line = stdout.splitlines().pop(0)
        matches = re.search(r"([\d\.]+)", first_line)
        if matches:
            version = matches.group(0)
            return Version.from_str(version)
        return None

    def pull(self, *args) -> str:
        stdout, _ = self.subp([*self.cmd_pull, *args])
        return stdout

    def check_deps(self):
        if not self.is_installed():
            raise ValueError("command: ansible is not installed")

    def subp(self, command, **kwargs):
        return subp(command, **kwargs)

    @abc.abstractmethod
    def is_installed(self):
        pass

    @abc.abstractmethod
    def install(self, pkg_name: str):
        pass


class AnsiblePullPip(AnsiblePull):
    def __init__(self, distro: Distro):
        super().__init__(distro)

        old_path = self.env.get("PATH")
        if old_path:
            self.env["PATH"] = ":".join([old_path, "/root/.local/bin/"])
        else:
            self.env["PATH"] = ""

    def install(self, pkg_name: str):
        """should cloud-init grow an interface for non-distro package
        managers? this seems reusable
        """
        if not self.is_installed():
            # bootstrap pip if required
            if not which("pip3"):
                self.distro.install_packages(PIP_PKG)
            self.subp(["python3", "-m", "pip", "install", "--user", pkg_name])

    def is_installed(self) -> bool:
        stdout, _ = self.subp(["python3", "-m", "pip", "list"])
        return "ansible" in stdout

    def subp(self, command, **kwargs):
        return subp(args=command, env=self.env, **kwargs)


class AnsiblePullDistro(AnsiblePull):
    def install(self, pkg_name: str):
        if not self.is_installed():
            self.distro.install_packages(pkg_name)

    def is_installed(self) -> bool:
        return bool(which("ansible"))


def handle(
    name: str, cfg: Config, cloud: Cloud, log: Logger, args: list
) -> None:

    ansible_cfg: dict = cfg.get("ansible", {})
    install_method = ansible_cfg.get("install-method")
    galaxy_cfg = ansible_cfg.get("galaxy")
    pull_cfg = ansible_cfg.get("pull")
    package_name = ansible_cfg.get("package-name", "")

    if ansible_cfg:
        ansible: AnsiblePull
        validate_config(ansible_cfg)

        distro: Distro = cloud.distro
        if install_method == "pip":
            ansible = AnsiblePullPip(distro)
        else:
            ansible = AnsiblePullDistro(distro)
        ansible.install(package_name)
        ansible.check_deps()

        if galaxy_cfg:
            ansible_galaxy(galaxy_cfg, ansible)

        if pull_cfg:
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
        LOG.warning("Cannot parse ansible version")
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


def ansible_galaxy(cfg: dict, ansible: AnsiblePull):
    actions = cfg.get("actions", [])
    ansible_config = cfg.get(CFG_OVERRIDE, "")
    if ansible_config:
        ansible.env[CFG_OVERRIDE] = ansible_config

    if not actions:
        LOG.warning("Invalid config: %s", cfg)
    for command in actions:
        ansible.subp(command)
