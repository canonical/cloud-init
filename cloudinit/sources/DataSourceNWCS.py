# Author: NWCS.sh <foss@nwcs.sh>
#
# This file is part of cloud-init. See LICENSE file for license information.

import logging

from requests import exceptions

from cloudinit import dmi, net, sources, subp, url_helper, util
from cloudinit.net.dhcp import NoDHCPLeaseError
from cloudinit.net.ephemeral import EphemeralDHCPv4

LOG = logging.getLogger(__name__)

BASE_URL_V1 = "http://169.254.169.254/api/v1"

BUILTIN_DS_CONFIG = {
    "metadata_url": BASE_URL_V1 + "/metadata",
}

MD_RETRIES = 30
MD_TIMEOUT = 5
MD_WAIT_RETRY = 5


class DataSourceNWCS(sources.DataSource):

    dsname = "NWCS"

    def __init__(self, sys_cfg, distro, paths):
        sources.DataSource.__init__(self, sys_cfg, distro, paths)
        self.distro = distro
        self.metadata = dict()
        self.ds_cfg = util.mergemanydict(
            [
                util.get_cfg_by_path(sys_cfg, ["datasource", "NWCS"], {}),
                BUILTIN_DS_CONFIG,
            ]
        )
        self.metadata_address = self.ds_cfg["metadata_url"]
        self.retries = self.ds_cfg.get("retries", MD_RETRIES)
        self.timeout = self.ds_cfg.get("timeout", MD_TIMEOUT)
        self.wait_retry = self.ds_cfg.get("wait_retry", MD_WAIT_RETRY)
        self._network_config = sources.UNSET
        self.dsmode = sources.DSMODE_NETWORK
        self.metadata_full = None

    def _unpickle(self, ci_pkl_version: int) -> None:
        super()._unpickle(ci_pkl_version)
        if not self._network_config:
            self._network_config = sources.UNSET

    def _get_data(self):
        md = self.get_metadata()

        if md is None:
            raise RuntimeError("failed to get metadata")

        self.metadata_full = md

        self.metadata["instance-id"] = md["instance-id"]
        self.metadata["public-keys"] = md["public-keys"]
        self.metadata["network"] = md["network"]
        self.metadata["local-hostname"] = md["hostname"]

        self.userdata_raw = md.get("userdata", None)

        self.vendordata_raw = md.get("vendordata", None)

        return True

    def get_metadata(self):
        try:
            LOG.info("Attempting to get metadata via DHCP")

            with EphemeralDHCPv4(
                self.distro,
                iface=net.find_fallback_nic(),
                connectivity_url_data={
                    "url": BASE_URL_V1 + "/metadata/instance-id",
                },
            ):
                return read_metadata(
                    self.metadata_address,
                    timeout=self.timeout,
                    sec_between=self.wait_retry,
                    retries=self.retries,
                )

        except (
            NoDHCPLeaseError,
            subp.ProcessExecutionError,
            RuntimeError,
            exceptions.RequestException,
        ) as e:
            LOG.error("DHCP failure: %s", e)
            raise

    @property
    def network_config(self):
        LOG.debug("Attempting network configuration")

        if self._network_config != sources.UNSET:
            return self._network_config

        if not self.metadata["network"]["config"]:
            raise RuntimeError("Unable to get metadata from server")

        # metadata sends interface names, but we dont want to use them
        for i in self.metadata["network"]["config"]:
            iface_name = get_interface_name(i["mac_address"])

            if iface_name:
                LOG.info("Overriding %s with %s", i["name"], iface_name)
                i["name"] = iface_name

        self._network_config = self.metadata["network"]

        return self._network_config

    @staticmethod
    def ds_detect():
        return "NWCS" == dmi.read_dmi_data("system-manufacturer")


def get_interface_name(mac):
    macs_to_nic = net.get_interfaces_by_mac()

    if mac not in macs_to_nic:
        return None

    return macs_to_nic.get(mac)


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)


def read_metadata(url, timeout=2, sec_between=2, retries=30):
    response = url_helper.readurl(
        url, timeout=timeout, sec_between=sec_between, retries=retries
    )

    if not response.ok():
        raise RuntimeError("unable to read metadata at %s" % url)

    return util.load_json(response.contents.decode())


# Used to match classes to dependencies
datasources = [
    (DataSourceNWCS, (sources.DEP_FILESYSTEM,)),
]
