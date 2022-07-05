"""ansible enables running on first boot either ansible-pull"""

from logging import Logger, getLogger
from textwrap import dedent
from typing import Callable, Tuple

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
        This module provides ansible-pull integration
        """
    ),
    "distros": [ALL_DISTROS],
    "examples": [
        dedent(
            """\
        ansible:
          pull:
            url: "don't forget to set required properties in schema"
            """
        ),
        dedent(
            """\
        ansible:
          local:
            TODO: next
            """
        ),
    ],
    "frequency": PER_INSTANCE,
}

__doc__ = get_meta_doc(meta)


def handle(name: str, cfg: dict, cloud: Cloud, log: Logger, _):

    # TODO: Remove this before PR
    if not all([name, cfg, cloud, log]):
        raise ValueError(
            f"Configuration not supported: {name} {cfg} {cloud} {log}"
        )

    install, ansible_config, run_ansible = get_and_validate_config(cfg)
    install_ansible(cloud.distro, install)
    run_ansible(ansible_config, log)


def get_and_validate_config(
    cfg: dict
) -> Tuple[bool, dict, Callable[[dict, Logger], None]]:
    ansible_cfg: dict = cfg.get("ansible", {})
    pull: dict = ansible_cfg.get("pull", {})
    local: dict = ansible_cfg.get("local", {})
    install: bool = ansible_cfg.get("install", False)
    if all([pull, local]):
        raise ValueError(
            "Both ansible-pull and ansible-local configured."
            "Simultaneous use not supported"
        )
    if pull:
        return (
            install,
            pull,
            run_ansible_pull,
        )
    elif local:
        return (
            install,
            local,
            run_ansible_local,
        )
    raise ValueError(
        "ansible module key missing (requires either 'pull' or 'local')")


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
            "ansible.install: True in your config or ensure that"
            "it is installed (either in your base image or in a package"
            "install module)"
        )


def run_ansible_pull(cfg: dict, log: Logger):
    cmd = "ansible-pull"
    check_deps(cmd)
    log.warn("in run_ansible_pull")
    try:
        playbook_name = cfg.get("playbook-name")
        if not playbook_name:
            raise ValueError("Missing required key: 'playbook-name'")

        stdout, stderr = subp(
            [
                cmd,
                *[
                    f"--{key}={value}" if value else f"--{key}"
                    for key, value in cfg.items()
                    if key != "playbook-name"
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


def run_ansible_local(cfg: dict, log: Logger):
    """TODO: ansible-playbook playbook.yml --connection=local"""
    cmd = "ansible-playbook"
    check_deps(cmd)
    raise NotImplementedError()
