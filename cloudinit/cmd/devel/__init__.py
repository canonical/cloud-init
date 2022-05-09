# This file is part of cloud-init. See LICENSE file for license information.

"""Common cloud-init devel commandline utility functions."""


import errno
import logging

from cloudinit import log
from cloudinit.helpers import Paths
from cloudinit.stages import Init
from cloudinit.util import error


def addLogHandlerCLI(logger, log_level):
    """Add a commandline logging handler to emit messages to stderr."""
    formatter = logging.Formatter("%(levelname)s: %(message)s")
    log.setupBasicLogging(log_level, formatter=formatter)
    return logger


def read_cfg_paths() -> Paths:
    """Return a Paths object based on the system configuration on disk.

    It handles file permission errors.
    """
    init = Init(ds_deps=[])
    try:
        init.read_cfg()
    except OSError as e:
        if e.errno == errno.EACCES:
            error(
                f"Failed reading config file(s) due to permission error:\n{e}",
                rc=1,
                sys_exit=True,
            )
        raise
    return init.paths


# vi: ts=4 expandtab
