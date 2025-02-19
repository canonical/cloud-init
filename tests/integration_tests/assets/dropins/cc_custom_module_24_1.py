# This file is part of cloud-init. See LICENSE file for license information.
"""This was the canonical example module from 24.1

Ensure cloud-init still supports it."""

import logging

from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.distros import ALL_DISTROS
from cloudinit.settings import PER_INSTANCE

MODULE_DESCRIPTION = """\
Description that will be used in module documentation.

This will likely take multiple lines.
"""

LOG = logging.getLogger(__name__)

meta: MetaSchema = {
    "id": "cc_example",
    "name": "Example Module",
    "title": "Shows how to create a module",
    "description": MODULE_DESCRIPTION,
    "distros": [ALL_DISTROS],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": ["example_key, example_other_key"],
    "examples": [
        "example_key: example_value",
        "example_other_key: ['value', 2]",
    ],
}

__doc__ = get_meta_doc(meta)


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    LOG.debug(f"Hi from module {name}")
    # Add one more line for easier testing
    print("Hello from module")
