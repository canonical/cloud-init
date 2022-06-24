"""ansible module"""

from textwrap import dedent

from logging import Logger
from cloudinit.cloud import Cloud
from cloudinit.distros import ALL_DISTROS
from cloudinit.settings import PER_INSTANCE
from cloudinit.config.schema import MetaSchema, get_meta_doc


meta: MetaSchema = {
    "id": "cc_ansible",
    "name": "Ansible",
    "title": "Configure ansible for instance",
    "description": dedent(
        """\
        This module handles TODO

        .. note::
            For more information about apt configuration, see the
            ``Additional apt configuration`` example.
        """
    ),
    "distros": [ALL_DISTROS],
    "examples": [
        dedent(
            """\
        ansible:
            """
        )
    ],
    "frequency": PER_INSTANCE,
}

__doc__ = get_meta_doc(meta)


def handle(name: str, cfg: dict, cloud: Cloud, log: Logger, args: list):
    log.debug(f"Hi from module {name} with args {args}, cloud {cloud} and cfg {cfg}")
