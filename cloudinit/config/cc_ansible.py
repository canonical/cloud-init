"""ansible enables running on first boot either ansible-pull"""

from logging import Logger
from textwrap import dedent
from typing import Tuple

from cloudinit.cloud import Cloud
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.distros import ALL_DISTROS, Distro
from cloudinit.settings import PER_INSTANCE
from cloudinit.subp import ProcessExecutionError, subp, which

meta: MetaSchema = {
    "id": "cc_ansible",
    "name": "Ansible",
    "title": "Configure ansible for instance",
    "description": dedent(
        """\
        This module provides ansible integration.``

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
}

__doc__ = get_meta_doc(meta)


def handle(name: str, cfg: dict, cloud: Cloud, log: Logger, _):
    ansible_cfg: dict = cfg.get("ansible", {})
    if ansible_cfg:
        install, ansible_config = get_and_validate_config(ansible_cfg)
        install_ansible(cloud.distro, install)
        run_ansible_pull(ansible_config, log)


def get_and_validate_config(cfg: dict) -> Tuple[bool, dict]:
    pull: dict = cfg.get("pull", {})
    install: bool = cfg.get("install", False)
    if not all([pull.get("playbook-name"), pull.get("url")]):
        raise ValueError(
            "Missing required key: playbook-name and "
            "url keys required for ansible module"
        )
    return (
        install,
        pull,
    )


def install_ansible(distro: Distro, install: bool):
    """Give users flexibility in whether to use the package install module or
    this module.
    """
    if install:
        distro.install_packages("ansible")


def check_deps(dep: str):
    if not which(dep):
        raise ValueError(
            f"command: {dep} is not available, please set"
            "ansible.install: True in your config or otherwise ensure that"
            "it is installed (either in your base image or in a package"
            "install module)"
        )


def filter_args(cfg: dict) -> dict:
    """remove value from boolean args should not be passed to ansible-pull
    flags
    """
    out: dict = {}
    for key, value in cfg.items():
        if isinstance(value, bool):
            if value:
                out[key] = None
        else:
            out[key] = value
    return out


def run_ansible_pull(cfg: dict, log: Logger):
    cmd = "ansible-pull"
    check_deps(cmd)
    playbook_name: str = cfg.pop("playbook-name")
    try:

        stdout, stderr = subp(
            [
                cmd,
                *[
                    f"--{key}={value}" if value else f"--{key}"
                    for key, value in filter_args(cfg).items()
                ],
                playbook_name,
            ]
        )
        if stderr:
            log.warn(f"{stderr}")
        if stdout:
            log.warn(f"{stdout}")
    except ProcessExecutionError as err:
        log.warn(f"Error executing ansible-pull, {err}")
