# Copyright (C) 2024 Aeza.net.
#
# Author: Egor Ternovoy <cofob@riseup.net>
#
# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import sources, dmi, util

BUILTIN_DS_CONFIG = {
    "metadata_url": "http://77.221.156.49/v1/cloudinit/{id}/",
}


class DataSourceAeza(sources.DataSource):

    dsname = "Aeza"

    def __init__(self, sys_cfg, distro, paths, ud_proc=None):
        super().__init__(sys_cfg, distro, paths, ud_proc)

        self.ds_cfg = util.mergemanydict([self.ds_cfg, BUILTIN_DS_CONFIG])

        url_params = self.get_url_params()
        self.timeout_seconds = url_params.timeout_seconds
        self.max_wait_seconds = url_params.max_wait_seconds
        self.retries = url_params.num_retries
        self.sec_between_retries = url_params.sec_between_retries

        system_uuid = dmi.read_dmi_data("system-uuid")
        self.metadata_address = (
            self.ds_cfg["metadata_url"].format(
                id=system_uuid,
            )
            + "%s"
        )

    @staticmethod
    def ds_detect():
        return dmi.read_dmi_data("system-manufacturer") == "Aeza"

    def _get_data(self):
        md, ud, vd = util.read_seeded(
            self.metadata_address,
            timeout=self.timeout_seconds,
            retries=self.retries,
        )
        self.metadata, self.userdata_raw, self.vendordata_raw = md, ud, vd

        return True


datasources = [
    (DataSourceAeza, (sources.DEP_NETWORK, sources.DEP_FILESYSTEM)),
]


def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
