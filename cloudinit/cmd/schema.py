# This file is part of cloud-init. See LICENSE file for license information.

"""Handle the cloud-init schema subcommand."""

import logging
from errno import EACCES

from cloudinit.cmd.devel import read_cfg_paths
from cloudinit.config import schema
from cloudinit.helpers import Paths
from cloudinit.sources import DataSourceNotFoundException

LOG = logging.getLogger(__name__)


def get_paths(args) -> Paths:
    """Return the Paths needed to validate the config selected by args.

    Only --system reads instance files such as
    /var/lib/cloud/instance/cloud-config.txt, which need the cached
    datasource to resolve. A --config-file is validated as given, so the
    datasource is not loaded for it.
    """
    if not args.system:
        return read_cfg_paths()
    try:
        return read_cfg_paths(fetch_existing_datasource="trust")
    except (IOError, OSError) as e:
        if e.errno != EACCES:
            raise
        LOG.debug(
            "Using default instance-data/user-data paths for non-root user"
        )
    except DataSourceNotFoundException:
        LOG.warning(
            "datasource not detected, using default"
            " instance-data/user-data paths."
        )
    return read_cfg_paths()


def handle_args(name, args):
    """Validate the config files selected by the command line arguments."""
    schema.handle_schema_args(name, args, get_paths(args))
