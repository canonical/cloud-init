import binascii
import json
import logging
from base64 import b64decode
from contextlib import suppress as noop
from enum import Enum
from typing import Any, List, Tuple, Union

from cloudinit import sources, url_helper, util
from cloudinit.net import find_fallback_nic, get_interfaces_by_mac
from cloudinit.net.ephemeral import EphemeralIPNetwork
from cloudinit.sources.helpers.akamai import (
    get_dmi_config,
    get_local_instance_id,
    is_on_akamai,
)

LOG = logging.getLogger(__name__)


BUILTIN_DS_CONFIG = {
    "base_urls": {
        "ipv4": "http://169.254.169.254",
        "ipv6": "http://[fd00:a9fe:a9fe::1]",
    },
    "paths": {
        "token": "/v1/token",
        "metadata": "/v1/instance",
        "userdata": "/v1/user-data",
    },
    # configures the behavior of the datasource
    "allow_local_stage": True,
    "allow_init_stage": True,
    "allow_dhcp": True,
    "allow_ipv4": True,
    "allow_ipv6": True,
    # mac address prefixes for interfaces that we would prefer to use for
    # local-stage initialization
    "preferred_mac_prefixes": [
        "f2:3",
    ],
}


class MetadataAvailabilityResult(Enum):
    """
    Used to indicate how this instance should behave based on the availability
    of metadata to it
    """

    NOT_AVAILABLE = 0
    AVAILABLE = 1
    DEFER = 2


class DataSourceAkamai(sources.DataSource):
    dsname = "Akamai"
    local_stage = False

    def __init__(self, sys_cfg, distro, paths):
        LOG.debug("Setting up Akamai DataSource")
        sources.DataSource.__init__(self, sys_cfg, distro, paths)
        self.metadata = dict()

        # build our config
        self.ds_cfg = util.mergemanydict(
            [
                get_dmi_config(),
                util.get_cfg_by_path(
                    sys_cfg,
                    ["datasource", "Akamai"],
                    {},
                ),
                BUILTIN_DS_CONFIG,
            ],
        )

    def _build_url(self, path_name: str, use_v6: bool = False) -> str:
        """
        Looks up the path for a given name and returns a full url for it.  If
        use_v6 is passed in, the IPv6 base url is used; otherwise the IPv4 url
        is used unless IPv4 is not allowed in ds_cfg
        """
        if path_name not in self.ds_cfg["paths"]:
            raise ValueError("Unknown path name {}".format(path_name))

        version_key = "ipv4"
        if use_v6 or not self.ds_cfg["allow_ipv4"]:
            version_key = "ipv6"

        base_url = self.ds_cfg["base_urls"][version_key]
        path = self.ds_cfg["paths"][path_name]

        return "{}{}".format(base_url, path)

    def _should_fetch_data(self) -> MetadataAvailabilityResult:
        """
        Returns whether metadata should be retrieved at this stage, at the next
        stage, or never, in the form of a MetadataAvailabilityResult.
        """
        if (
            not self.ds_cfg["allow_ipv4"] and not self.ds_cfg["allow_ipv6"]
        ) or (
            not self.ds_cfg["allow_local_stage"]
            and not self.ds_cfg["allow_init_stage"]
        ):
            # if we're not allowed to fetch data, we shouldn't try
            LOG.info("Configuration prohibits fetching metadata.")
            return MetadataAvailabilityResult.NOT_AVAILABLE

        if self.local_stage:
            return self._should_fetch_data_local()
        else:
            return self._should_fetch_data_network()

    def _should_fetch_data_local(self) -> MetadataAvailabilityResult:
        """
        Returns whether metadata should be retrieved during the local stage, or
        if it should wait for the init stage.
        """
        if not self.ds_cfg["allow_local_stage"]:
            # if this stage is explicitly disabled, don't attempt to fetch here
            LOG.info("Configuration prohibits local stage setup")
            return MetadataAvailabilityResult.DEFER

        if not self.ds_cfg["allow_dhcp"] and not self.ds_cfg["allow_ipv6"]:
            # without dhcp, we can't fetch during the local stage over IPv4.
            # If we're not allowed to use IPv6 either, then we can't init
            # during this stage
            LOG.info(
                "Configuration does not allow for ephemeral network setup."
            )
            return MetadataAvailabilityResult.DEFER

        return MetadataAvailabilityResult.AVAILABLE

    def _should_fetch_data_network(self) -> MetadataAvailabilityResult:
        """
        Returns whether metadata should be fetched during the init stage.
        """
        if not self.ds_cfg["allow_init_stage"]:
            # if this stage is explicitly disabled, don't attempt to fetch here
            LOG.info("Configuration does not allow for init stage setup")
            return MetadataAvailabilityResult.DEFER

        return MetadataAvailabilityResult.AVAILABLE

    def _get_network_context_managers(
        self,
    ) -> List[Tuple[Union[Any, EphemeralIPNetwork], bool]]:
        """
        Returns a list of context managers which should be tried when setting
        up a network context.  If we're running in init mode, this return a
        noop since networking should already be configured.
        """
        network_context_managers: List[
            Tuple[Union[Any, EphemeralIPNetwork], bool]
        ] = []
        if self.local_stage:
            # at this stage, networking isn't up yet.  To support that, we need
            # an ephemeral network

            # find the first interface that isn't lo or a vlan interface
            interfaces = get_interfaces_by_mac()
            interface = None
            preferred_prefixes = self.ds_cfg["preferred_mac_prefixes"]
            for mac, inf in interfaces.items():
                # try to match on the preferred mac prefixes
                if any(
                    [mac.startswith(prefix) for prefix in preferred_prefixes]
                ):
                    interface = inf
                    break

            if interface is None:
                LOG.warning(
                    "Failed to find default interface, attempting DHCP on "
                    "fallback interface"
                )
                interface = find_fallback_nic()

            network_context_managers = []

            if self.ds_cfg["allow_ipv6"]:
                network_context_managers.append(
                    (
                        EphemeralIPNetwork(
                            self.distro,
                            interface,
                            ipv4=False,
                            ipv6=True,
                        ),
                        True,
                    ),
                )

            if self.ds_cfg["allow_ipv4"] and self.ds_cfg["allow_dhcp"]:
                network_context_managers.append(
                    (
                        EphemeralIPNetwork(
                            self.distro,
                            interface,
                            ipv4=True,
                        ),
                        False,
                    )
                )
        else:
            if self.ds_cfg["allow_ipv6"]:
                network_context_managers.append(
                    (
                        noop(),
                        True,
                    ),
                )

            if self.ds_cfg["allow_ipv4"]:
                network_context_managers.append(
                    (
                        noop(),
                        False,
                    ),
                )

        return network_context_managers

    def _fetch_metadata(self, use_v6: bool = False) -> bool:
        """
        Runs through the sequence of requests necessary to retrieve our
        metadata and user data, creating a token for use in doing so, capturing
        the results.
        """
        try:
            # retrieve a token for future requests
            token_response = url_helper.readurl(
                self._build_url("token", use_v6=use_v6),
                request_method="PUT",
                timeout=30,
                sec_between=2,
                retries=4,
                headers={
                    "Metadata-Token-Expiry-Seconds": "300",
                },
            )
            if token_response.code != 200:
                LOG.info(
                    "Fetching token returned %s; not fetching data",
                    token_response.code,
                )
                return True

            token = str(token_response)

            # fetch general metadata
            metadata = url_helper.readurl(
                self._build_url("metadata", use_v6=use_v6),
                timeout=30,
                sec_between=2,
                retries=2,
                headers={
                    "Accept": "application/json",
                    "Metadata-Token": token,
                },
            )
            self.metadata = json.loads(str(metadata))

            # fetch user data
            userdata = url_helper.readurl(
                self._build_url("userdata", use_v6=use_v6),
                timeout=30,
                sec_between=2,
                retries=2,
                headers={
                    "Metadata-Token": token,
                },
            )
            self.userdata_raw = str(userdata)
            try:
                self.userdata_raw = b64decode(self.userdata_raw).decode()
            except binascii.Error as e:
                LOG.warning("Failed to base64 decode userdata due to %s", e)
        except url_helper.UrlError as e:
            # we failed to retrieve data with an exception; log the error and
            # return false, indicating that we should retry using a different
            # network if possible
            LOG.warning(
                "Failed to retrieve metadata using IPv%s due to %s",
                "6" if use_v6 else "4",
                e,
            )
            return False

        return True

    def _get_data(self) -> bool:
        """
        Overrides _get_data in the DataSource class to actually retrieve data
        """
        LOG.debug("Getting data from Akamai DataSource")

        if not is_on_akamai():
            LOG.info("Not running on Akamai, not running.")
            return False

        local_instance_id = get_local_instance_id()
        self.metadata = {
            "instance-id": local_instance_id,
        }
        availability = self._should_fetch_data()

        if availability != MetadataAvailabilityResult.AVAILABLE:
            if availability == MetadataAvailabilityResult.NOT_AVAILABLE:
                LOG.info(
                    "Metadata is not available, returning local data only."
                )
                return True

            LOG.info(
                "Configured not to fetch data at this stage; waiting for "
                "a later stage."
            )
            return False

        network_context_managers = self._get_network_context_managers()
        for manager, use_v6 in network_context_managers:
            with manager:
                done = self._fetch_metadata(use_v6=use_v6)
                if done:
                    # fix up some field names
                    self.metadata["instance-id"] = self.metadata.get(
                        "id",
                        local_instance_id,
                    )
                    break
        else:
            # even if we failed to reach the metadata service this loop, we
            # still have the locally-available metadata (namely the instance id
            # and cloud name), and by accepting just that we ensure that
            # cloud-init won't run on our next boot
            LOG.warning(
                "Failed to contact metadata service, falling back to local "
                "metadata only."
            )

        return True

    def check_instance_id(self, sys_cfg) -> bool:
        """
        A local-only check to see if the instance id matches the id we see on
        the system
        """
        return sources.instance_id_matches_system_uuid(
            self.get_instance_id(), "system-serial-number"
        )


class DataSourceAkamaiLocal(DataSourceAkamai):
    """
    A subclass of DataSourceAkamai that runs the same functions, but during the
    init-local stage.  This allows configuring networking via cloud-init, as
    networking hasn't been configured yet.
    """

    local_stage = True


datasources = [
    # run in init-local if possible
    (DataSourceAkamaiLocal, (sources.DEP_FILESYSTEM,)),
    # if not, run in init
    (
        DataSourceAkamai,
        (
            sources.DEP_FILESYSTEM,
            sources.DEP_NETWORK,
        ),
    ),
]


# cloudinit/sources/__init__.py will look for and call this when deciding if
# we're a valid DataSource for the stage its running
def get_datasource_list(depends) -> List[sources.DataSource]:
    return sources.list_from_depends(depends, datasources)
