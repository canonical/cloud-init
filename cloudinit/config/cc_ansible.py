"""ansible enables running on first boot either ansible-pull"""

from textwrap import dedent

from logging import Logger
from cloudinit.cloud import Cloud
from cloudinit.subp import subp, which, ProcessExecutionError
from cloudinit.distros import ALL_DISTROS, Distro
from cloudinit.settings import PER_INSTANCE
from cloudinit.config.schema import MetaSchema, get_meta_doc


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
            """
        ),
        dedent(
            """\
        ansible:
          local:
            """
        )
    ],
    "frequency": PER_INSTANCE,
}

__doc__ = get_meta_doc(meta)


def handle(name: str, cfg: dict, cloud: Cloud, log: Logger, args: list):
    # TODO: Remove this before PR
    if not name or not cfg or not cloud or not log or args:
        raise ValueError(f"Configuration not supported: {name} {cfg} {cloud} {log} {args}")
    ansible_cfg: dict = cfg.get("ansible", {})
    pull: dict = ansible_cfg.get("pull", {})
    local: dict = ansible_cfg.get("local", {})
    install: bool = ansible_cfg.get("install", False)
    log.debug(f"Hi from module {name} with args {args}, cloud {cloud} and cfg {cfg}")
    if not (pull or local):
        return
    if pull and local:
        raise ValueError(
            "Both ansible-pull and ansible-local configured. "
            "Simultaneous use not supported")
    if install:
        install_ansible(cloud.distro)
    if pull:
        if not which("ansible-pull"):
            raise ValueError(
                "command: ansible-pull is not available, please set"
                "ansible.install: True in your config or ensure that"
                "it is installed (either in your base image or in a package"
                "install module"
            )
        run_ansible_pull(pull, log)
    elif local:
        if not which("ansible-playbook"):
            raise ValueError(
                "command: ansible-pull is not available, please set"
                "ansible.install: True in your config or ensure that"
                "it is installed (either in your base image or in a package"
                "install module"
            )
        run_ansible_local(local, log)


def install_ansible(distro: Distro):
    distro.install_packages("ansible")


def run_ansible_pull(cfg: dict, log: Logger):
    try:
        playbook_name = cfg.get("playbook-name")
        if not playbook_name:
            raise ValueError("Missing required key: 'playbook-name'")

        stdout, stderr = subp(
            ["ansible-pull",
                *[
                    f"--{key}={value}" if value else
                    f"--{key}" for key, value in cfg.items()
                    if key != "playbook-name"],
                playbook_name]
        )
        if stderr:
            log.warn(f"{stderr}")
        if stdout:
            log.warn(f"{stdout}")
    except ProcessExecutionError as err:
        log.warn(f"Error executing ansible-pull, {err}")


def run_ansible_local(cfg: dict, log: Logger):
    """TODO: ansible-playbook playbook.yml --connection=local"""
