# Author: Antti Myyrä <antti.myyra@upcloud.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

# UpCloud server metadata API:
# https://developers.upcloud.com/1.3/8-servers/#metadata-service

from cloudinit import log as logging
from cloudinit import net as cloudnet
from cloudinit import sources, util
from cloudinit.net.dhcp import NoDHCPLeaseError
from cloudinit.net.ephemeral import EphemeralDHCPv4
from cloudinit.sources.helpers import upcloud as uc_helper

LOG = logging.getLogger(__name__)

BUILTIN_DS_CONFIG = {"metadata_url": "http://169.254.169.254/metadata/v1.json"}

# Wait for a up to a minute, retrying the meta-data server
# every 2 seconds.
MD_RETRIES = 30
MD_TIMEOUT = 2
MD_WAIT_RETRY = 2


class DataSourceUpCloud(sources.DataSource):

    dsname = "UpCloud"

    # We'll perform DHCP setup only in init-local, see DataSourceUpCloudLocal
    perform_dhcp_setup = False

    def __init__(self, sys_cfg, distro, paths):
        sources.DataSource.__init__(self, sys_cfg, distro, paths)
        self.distro = distro
        self.metadata = dict()
        self.ds_cfg = util.mergemanydict(
            [
                util.get_cfg_by_path(sys_cfg, ["datasource", "UpCloud"], {}),
                BUILTIN_DS_CONFIG,
            ]
        )
        self.metadata_address = self.ds_cfg["metadata_url"]
        self.retries = self.ds_cfg.get("retries", MD_RETRIES)
        self.timeout = self.ds_cfg.get("timeout", MD_TIMEOUT)
        self.wait_retry = self.ds_cfg.get("wait_retry", MD_WAIT_RETRY)
        self._network_config = None

    def _get_sysinfo(self):
        return uc_helper.read_sysinfo()

    def _read_metadata(self):
        return uc_helper.read_metadata(
            self.metadata_address,
            timeout=self.timeout,
            sec_between=self.wait_retry,
            retries=self.retries,
        )

    def _get_data(self):
        (is_upcloud, server_uuid) = self._get_sysinfo()

        # only proceed if we know we are on UpCloud
        if not is_upcloud:
            return False

        LOG.info("Running on UpCloud. server_uuid=%s", server_uuid)

        if self.perform_dhcp_setup:  # Setup networking in init-local stage.
            try:
                LOG.debug("Finding a fallback NIC")
                nic = cloudnet.find_fallback_nic()
                LOG.debug("Discovering metadata via DHCP interface %s", nic)
                with EphemeralDHCPv4(
                    nic, tmp_dir=self.distro.get_tmp_exec_path()
                ):
                    md = util.log_time(
                        logfunc=LOG.debug,
                        msg="Reading from metadata service",
                        func=self._read_metadata,
                    )
            except (NoDHCPLeaseError, sources.InvalidMetaDataException) as e:
                util.logexc(LOG, str(e))
                return False
        else:
            try:
                LOG.debug(
                    "Discovering metadata without DHCP-configured networking"
                )
                md = util.log_time(
                    logfunc=LOG.debug,
                    msg="Reading from metadata service",
                    func=self._read_metadata,
                )
            except sources.InvalidMetaDataException as e:
                util.logexc(LOG, str(e))
                LOG.info(
                    "No DHCP-enabled interfaces available, "
                    "unable to fetch metadata for %s",
                    server_uuid,
                )
                return False

        self.metadata_full = md
        self.metadata["instance-id"] = md.get("instance_id", server_uuid)
        self.metadata["local-hostname"] = md.get("hostname")
        self.metadata["network"] = md.get("network")
        self.metadata["public-keys"] = md.get("public_keys")
        self.metadata["availability_zone"] = md.get("region", "default")
        self.vendordata_raw = md.get("vendor_data", None)
        self.userdata_raw = md.get("user_data", None)

        return True

    def check_instance_id(self, sys_cfg):
        return sources.instance_id_matches_system_uuid(self.get_instance_id())

    @property
    def network_config(self):
        """
        Configure the networking. This needs to be done each boot,
        since the IP and interface information might have changed
        due to reconfiguration.
        """

        if self._network_config:
            return self._network_config

        raw_network_config = self.metadata.get("network")
        if not raw_network_config:
            raise Exception("Unable to get network meta-data from server....")

        self._network_config = uc_helper.convert_network_config(
            raw_network_config,
        )

        return self._network_config


class DataSourceUpCloudLocal(DataSourceUpCloud):
    """
    Run in init-local using a DHCP discovery prior to metadata crawl.

    In init-local, no network is available. This subclass sets up minimal
    networking with dhclient on a viable nic so that it can talk to the
    metadata service. If the metadata service provides network configuration
    then render the network configuration for that instance based on metadata.
    """

    perform_dhcp_setup = True  # Get metadata network config if present


# Used to match classes to dependencies
datasources = [
    (DataSourceUpCloudLocal, (sources.DEP_FILESYSTEM,)),
    (DataSourceUpCloud, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)


# vi: ts=4 expandtab
