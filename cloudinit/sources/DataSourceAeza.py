# Copyright (C) 2024 Aeza.net.
#
# Author: Egor Ternovoy <cofob@riseup.net>
#
# This file is part of cloud-init. See LICENSE file for license information.

import logging

from cloudinit import dmi, sources, util

LOG = logging.getLogger(__name__)

BUILTIN_DS_CONFIG = {
    "metadata_url": "http://77.221.156.49/v1/cloudinit/{id}/",
}


class DataSourceAeza(sources.DataSource):

    dsname = "Aeza"

    def __init__(self, sys_cfg, distro, paths, ud_proc=None):
        super().__init__(sys_cfg, distro, paths, ud_proc)

        self.ds_cfg = util.mergemanydict([self.ds_cfg, BUILTIN_DS_CONFIG])

    @staticmethod
    def ds_detect():
        return dmi.read_dmi_data("system-manufacturer") == "Aeza"

    def _get_data(self):
        system_uuid = dmi.read_dmi_data("system-uuid")
        metadata_address = (
            self.ds_cfg["metadata_url"].format(
                id=system_uuid,
            )
            + "%s"
        )
        url_params = self.get_url_params()
        md, ud, vd = util.read_seeded(
            metadata_address,
            timeout=url_params.timeout_seconds,
            retries=url_params.num_retries,
        )

        if md is None:
            raise sources.InvalidMetaDataException(
                f"Failed to read metadata from {metadata_address}",
            )
        if not isinstance(md.get("instance-id"), str):
            raise sources.InvalidMetaDataException(
                f"Metadata does not contain instance-id: {md}"
            )
        if not isinstance(ud, bytes):
            raise sources.InvalidMetaDataException("Userdata is not bytes")

        self.metadata, self.userdata_raw, self.vendordata_raw = md, ud, vd

        return True


datasources = [
    (DataSourceAeza, (sources.DEP_NETWORK, sources.DEP_FILESYSTEM)),
]


def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
