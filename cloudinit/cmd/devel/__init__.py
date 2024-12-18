# This file is part of cloud-init. See LICENSE file for license information.

"""Common cloud-init devel command line utility functions."""

from typing import Optional

from cloudinit import stages
from cloudinit.helpers import Paths


def read_cfg_paths(cache_mode: Optional[str] = None) -> Paths:
    """Return a Paths object based on the system configuration on disk.

    :param cache_mode: String one of check or trust. Whether to
        load the pickled datasource before returning Paths. This is necessary
        when using instance paths via Paths.get_ipath method which are only
        known from the instance-id metadata in the detected datasource.

    :raises: DataSourceNotFoundException when no datasource cache exists.
    """
    init = stages.Init(stages.single, cache_mode=cache_mode)
    if cache_mode:
        init.fetch()
    init.read_cfg()
    return init.paths
