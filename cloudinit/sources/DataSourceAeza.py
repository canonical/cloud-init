# Copyright (C) 2024 Aeza.net.
#
# Author: Egor Ternovoy <cofob@riseup.net>
#
# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import sources, util
import cloudinit.sources.helpers.aeza as aeza_helper

BASE_URL_V1 = "http://77.221.156.49/v1/cloudinit"

BUILTIN_DS_CONFIG = {
    "retries": 60,
    "timeout": 2,
    "wait_retry": 2,
    "metadata_url": BASE_URL_V1 + "/{id}/meta-data",
    "userdata_url": BASE_URL_V1 + "/{id}/user-data",
    "vendordata_url": BASE_URL_V1 + "/{id}/vendor-data",
}

class DataSourceAeza(sources.DataSource):

    dsname = "Aeza"

    def __init__(self, sys_cfg, distro, paths, ud_proc=None):
        sources.DataSource.__init__(self, sys_cfg, distro, paths, ud_proc)
        self.metadata = {}
        self.vendordata_raw = None
        self.userdata_raw = ""

        self.ds_cfg = util.mergemanydict(
            [
                util.get_cfg_by_path(sys_cfg, ["datasource", "Aeza"], {}),
                BUILTIN_DS_CONFIG,
            ]
        )

        self.timeout = self.ds_cfg["timeout"]
        self.wait_retry = self.ds_cfg["wait_retry"]
        self.retries = self.ds_cfg["retries"]

        self.metadata_address = self.ds_cfg["metadata_url"]
        self.userdata_address = self.ds_cfg["userdata_url"]
        self.vendordata_address = self.ds_cfg["vendordata_url"]

    def _get_data(self):
        system_uuid = aeza_helper.read_system_uuid()

        md = aeza_helper.read_metadata(
            aeza_helper.format_url(self.metadata_address, system_uuid),
            timeout=self.timeout,
            sec_between=self.wait_retry,
            retries=self.retries,
        )
        ud = aeza_helper.read_data(
            aeza_helper.format_url(self.userdata_address, system_uuid),
            timeout=self.timeout,
            sec_between=self.wait_retry,
            retries=self.retries,
        )
        vd = aeza_helper.read_data(
            aeza_helper.format_url(self.vendordata_address, system_uuid),
            timeout=self.timeout,
            sec_between=self.wait_retry,
            retries=self.retries,
        )

        self.metadata = md
        self.userdata_raw = ud
        self.vendordata_raw = vd

        return True


datasources = [
    (DataSourceAeza, (sources.DEP_NETWORK, sources.DEP_FILESYSTEM)),
]


def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
