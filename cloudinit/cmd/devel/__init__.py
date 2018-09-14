# This file is part of cloud-init. See LICENSE file for license information.

"""Common cloud-init devel commandline utility functions."""


import logging

from cloudinit import log
from cloudinit.stages import Init


def addLogHandlerCLI(logger, log_level):
    """Add a commandline logging handler to emit messages to stderr."""
    formatter = logging.Formatter('%(levelname)s: %(message)s')
    log.setupBasicLogging(log_level, formatter=formatter)
    return logger


def read_cfg_paths():
    """Return a Paths object based on the system configuration on disk."""
    init = Init(ds_deps=[])
    init.read_cfg()
    return init.paths

# vi: ts=4 expandtab
