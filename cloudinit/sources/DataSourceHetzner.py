# Author: Jonas Keidel <jonas.keidel@hetzner.com>
# Author: Markus Schade <markus.schade@hetzner.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
#
"""Hetzner Cloud API Documentation
https://docs.hetzner.cloud/"""

import logging

import cloudinit.sources.helpers.hetzner as hc_helper
from cloudinit import dmi, net, sources, util
from cloudinit.net.dhcp import NoDHCPLeaseError
from cloudinit.net.ephemeral import EphemeralDHCPv4

LOG = logging.getLogger(__name__)

BASE_URL_V1 = "http://169.254.169.254/hetzner/v1"

BUILTIN_DS_CONFIG = {
    "metadata_url": BASE_URL_V1 + "/metadata",
    "userdata_url": BASE_URL_V1 + "/userdata",
}

MD_RETRIES = 60
MD_TIMEOUT = 2
MD_WAIT_RETRY = 2


class DataSourceHetzner(sources.DataSource):

    dsname = "Hetzner"

    def __init__(self, sys_cfg, distro, paths):
        sources.DataSource.__init__(self, sys_cfg, distro, paths)
        self.distro = distro
        self.metadata = dict()
        self.ds_cfg = util.mergemanydict(
            [
                util.get_cfg_by_path(sys_cfg, ["datasource", "Hetzner"], {}),
                BUILTIN_DS_CONFIG,
            ]
        )
        self.metadata_address = self.ds_cfg["metadata_url"]
        self.userdata_address = self.ds_cfg["userdata_url"]
        self.retries = self.ds_cfg.get("retries", MD_RETRIES)
        self.timeout = self.ds_cfg.get("timeout", MD_TIMEOUT)
        self.wait_retry = self.ds_cfg.get("wait_retry", MD_WAIT_RETRY)
        self._network_config = sources.UNSET
        self.dsmode = sources.DSMODE_NETWORK
        self.metadata_full = None

    def _get_data(self):
        (on_hetzner, serial) = get_hcloud_data()

        if not on_hetzner:
            return False

        try:
            with EphemeralDHCPv4(
                self.distro,
                iface=net.find_fallback_nic(),
                connectivity_url_data={
                    "url": BASE_URL_V1 + "/metadata/instance-id",
                },
            ):
                md = hc_helper.read_metadata(
                    self.metadata_address,
                    timeout=self.timeout,
                    sec_between=self.wait_retry,
                    retries=self.retries,
                )
                ud = hc_helper.read_userdata(
                    self.userdata_address,
                    timeout=self.timeout,
                    sec_between=self.wait_retry,
                    retries=self.retries,
                )
        except (NoDHCPLeaseError) as e:
            LOG.error("Bailing, DHCP Exception: %s", e)
            raise

        # Hetzner cloud does not support binary user-data. So here, do a
        # base64 decode of the data if we can. The end result being that a
        # user can provide base64 encoded (possibly gzipped) data as user-data.
        #
        # The fallout is that in the event of b64 encoded user-data,
        # /var/lib/cloud-init/cloud-config.txt will not be identical to the
        # user-data provided.  It will be decoded.
        self.userdata_raw = util.maybe_b64decode(ud)
        self.metadata_full = md

        # hostname is name provided by user at launch.  The API enforces it is
        # a valid hostname, but it is not guaranteed to be resolvable in dns or
        # fully qualified.
        self.metadata["instance-id"] = md["instance-id"]
        self.metadata["local-hostname"] = md["hostname"]
        self.metadata["network-config"] = md.get("network-config", None)
        self.metadata["public-keys"] = md.get("public-keys", None)
        self.vendordata_raw = md.get("vendor_data", None)

        # instance-id and serial from SMBIOS should be identical
        if self.get_instance_id() != serial:
            raise RuntimeError(
                "SMBIOS serial does not match instance ID from metadata"
            )

        return True

    def check_instance_id(self, sys_cfg):
        return sources.instance_id_matches_system_uuid(
            self.get_instance_id(), "system-serial-number"
        )

    @property
    def network_config(self):
        """Configure the networking. This needs to be done each boot, since
        the IP information may have changed due to snapshot and/or
        migration.
        """

        if self._network_config is None:
            LOG.warning(
                "Found None as cached _network_config. Resetting to %s",
                sources.UNSET,
            )
            self._network_config = sources.UNSET

        if self._network_config != sources.UNSET:
            return self._network_config

        _net_config = self.metadata["network-config"]
        if not _net_config:
            raise RuntimeError("Unable to get meta-data from server....")

        self._network_config = _net_config

        return self._network_config


def get_hcloud_data():
    vendor_name = dmi.read_dmi_data("system-manufacturer")
    if vendor_name != "Hetzner":
        return (False, None)

    serial = dmi.read_dmi_data("system-serial-number")
    if serial:
        LOG.debug("Running on Hetzner Cloud: serial=%s", serial)
    else:
        raise RuntimeError("Hetzner Cloud detected, but no serial found")

    return (True, serial)


# Used to match classes to dependencies
datasources = [
    (DataSourceHetzner, (sources.DEP_FILESYSTEM,)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
