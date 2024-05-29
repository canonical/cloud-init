# This file is part of cloud-init. See LICENSE file for license information.

"""Common cloud-init devel command line utility functions."""

from cloudinit.helpers import Paths
from cloudinit.stages import Init


def read_cfg_paths(fetch_existing_datasource: str = "") -> Paths:
    """Return a Paths object based on the system configuration on disk.

    :param fetch_existing_datasource: String one of check or trust. Whether to
        load the pickled datasource before returning Paths. This is necessary
        when using instance paths via Paths.get_ipath method which are only
        known from the instance-id metadata in the detected datasource.

    :raises: DataSourceNotFoundException when no datasource cache exists.
    """
    init = Init(ds_deps=[])
    if fetch_existing_datasource:
        init.fetch(existing=fetch_existing_datasource)
    init.read_cfg()
    return init.paths
