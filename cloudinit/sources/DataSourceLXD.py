"""Datasource for LXD, reads /dev/lxd/sock representation of instance data.

Notes:
 * This datasource replaces previous NoCloud datasource for LXD.
 * Older LXD images may not have updates for cloud-init so NoCloud may
   still be detected on those images.
 * Detect LXD datasource when /dev/lxd/sock is an active socket file.
 * Info on dev-lxd API: https://documentation.ubuntu.com/lxd/en/latest/dev-lxd/
"""

import logging
import os
import socket
import stat
import time
from enum import Flag, auto
from json.decoder import JSONDecodeError
from typing import Any, Dict, List, Optional, Tuple, Union, cast

import requests
from requests.adapters import HTTPAdapter

# Note: `urllib3` is transitively installed by `requests`.
from urllib3.connection import HTTPConnection
from urllib3.connectionpool import HTTPConnectionPool

from cloudinit import atomic_helper, sources, subp, url_helper, util
from cloudinit.net import find_fallback_nic

LOG = logging.getLogger(__name__)

LXD_SOCKET_PATH = "/dev/lxd/sock"
LXD_SOCKET_API_VERSION = "1.0"
LXD_URL = "http://lxd"

# Config key mappings to alias as top-level instance data keys
CONFIG_KEY_ALIASES = {
    "cloud-init.user-data": "user-data",
    "cloud-init.network-config": "network-config",
    "cloud-init.vendor-data": "vendor-data",
    "user.user-data": "user-data",
    "user.network-config": "network-config",
    "user.vendor-data": "vendor-data",
}


def _get_fallback_interface_name() -> str:
    default_name = "eth0"
    if subp.which("systemd-detect-virt"):
        try:
            virt_type, _ = subp.subp(["systemd-detect-virt"])
        except subp.ProcessExecutionError as err:
            LOG.warning(
                "Unable to run systemd-detect-virt: %s."
                " Rendering default network config.",
                err,
            )
            return default_name
        if virt_type.strip() in (
            "kvm",
            "qemu",
        ):  # instance.type VIRTUAL-MACHINE
            arch = util.system_info()["uname"][4]
            if arch == "ppc64le":
                return "enp0s5"
            elif arch == "s390x":
                return "enc9"
            else:
                return "enp5s0"
    return default_name


def generate_network_config(
    nics: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Return network config V1 dict representing instance network config."""
    # TODO: The original intent of this function was to use the nics retrieved
    # from LXD's devices endpoint to determine the primary nic and write
    # that out to network config. However, for LXD VMs, the device name
    # may differ from the interface name in the VM, so we'll instead rely
    # on our fallback nic code. Once LXD's devices endpoint grows the
    # ability to provide a MAC address, we should rely on that information
    # rather than just the glorified guessing that we're doing here.
    primary_nic = find_fallback_nic()
    if primary_nic:
        LOG.debug(
            "LXD datasource generating network from discovered active"
            " device: %s",
            primary_nic,
        )
    else:
        primary_nic = _get_fallback_interface_name()
        LOG.debug(
            "LXD datasource generating network from systemd-detect-virt"
            " platform default device: %s",
            primary_nic,
        )

    return {
        "version": 1,
        "config": [
            {
                "type": "physical",
                "name": primary_nic,
                "subnets": [{"type": "dhcp", "control": "auto"}],
            }
        ],
    }


class SocketHTTPConnection(HTTPConnection):
    def __init__(self, socket_path):
        super().__init__("localhost")
        self.socket_path = socket_path
        self.sock = None

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(self.socket_path)


class SocketConnectionPool(HTTPConnectionPool):
    def __init__(self, socket_path):
        self.socket_path = socket_path
        super().__init__("localhost")

    def _new_conn(self):
        return SocketHTTPConnection(self.socket_path)


class LXDSocketAdapter(HTTPAdapter):
    def get_connection(self, url, proxies=None):
        return SocketConnectionPool(LXD_SOCKET_PATH)

    # Fix for requests 2.32.2+:
    # https://github.com/psf/requests/pull/6710
    def get_connection_with_tls_context(
        self, request, verify, proxies=None, cert=None
    ):
        return self.get_connection(request.url, proxies)


def _raw_instance_data_to_dict(metadata_type: str, metadata_value) -> dict:
    """Convert raw instance data from str, bytes, YAML to dict

    :param metadata_type: string, one of as: meta-data, vendor-data, user-data
        network-config

    :param metadata_value: str, bytes or dict representing or instance-data.

    :raises: InvalidMetaDataError on invalid instance-data content.
    """
    if isinstance(metadata_value, dict):
        return metadata_value
    if metadata_value is None:
        return {}
    try:
        parsed_metadata = util.load_yaml(metadata_value)
    except AttributeError as exc:  # not str or bytes
        raise sources.InvalidMetaDataException(
            "Invalid {md_type}. Expected str, bytes or dict but found:"
            " {value}".format(md_type=metadata_type, value=metadata_value)
        ) from exc
    if parsed_metadata is None:
        raise sources.InvalidMetaDataException(
            "Invalid {md_type} format. Expected YAML but found:"
            " {value}".format(md_type=metadata_type, value=metadata_value)
        )
    return parsed_metadata


class DataSourceLXD(sources.DataSource):

    dsname = "LXD"

    _network_config: Union[Dict, str] = sources.UNSET
    _crawled_metadata: Optional[Union[Dict, str]] = sources.UNSET

    sensitive_metadata_keys: Tuple[
        str, ...
    ] = sources.DataSource.sensitive_metadata_keys + (
        "user.meta-data",
        "user.vendor-data",
        "user.user-data",
        "cloud-init.user-data",
        "cloud-init.vendor-data",
    )

    skip_hotplug_detect = True

    def _unpickle(self, ci_pkl_version: int) -> None:
        super()._unpickle(ci_pkl_version)
        self.skip_hotplug_detect = True

    @staticmethod
    def ds_detect() -> bool:
        """Check platform environment to report if this datasource may run."""
        return is_platform_viable()

    def _get_data(self) -> bool:
        """Crawl LXD socket API instance data and return True on success"""
        self._crawled_metadata = util.log_time(
            logfunc=LOG.debug,
            msg="Crawl of metadata service",
            func=read_metadata,
        )
        self.metadata = _raw_instance_data_to_dict(
            "meta-data", self._crawled_metadata.get("meta-data")
        )
        config = self._crawled_metadata.get("config", {})
        user_metadata = config.get("user.meta-data", {})
        if user_metadata:
            user_metadata = _raw_instance_data_to_dict(
                "user.meta-data", user_metadata
            )
        if "user-data" in self._crawled_metadata:
            self.userdata_raw = self._crawled_metadata["user-data"]
        if "network-config" in self._crawled_metadata:
            self._network_config = _raw_instance_data_to_dict(
                "network-config", self._crawled_metadata["network-config"]
            )
        if "vendor-data" in self._crawled_metadata:
            self.vendordata_raw = self._crawled_metadata["vendor-data"]
        return True

    def _get_subplatform(self) -> str:
        """Return subplatform details for this datasource"""
        return "LXD socket API v. {ver} ({socket})".format(
            ver=LXD_SOCKET_API_VERSION, socket=LXD_SOCKET_PATH
        )

    def check_instance_id(self, sys_cfg) -> str:
        """Return True if instance_id unchanged."""
        response = read_metadata(metadata_keys=MetaDataKeys.META_DATA)
        md = response.get("meta-data", {})
        if not isinstance(md, dict):
            md = util.load_yaml(md)
        return md.get("instance-id") == self.metadata.get("instance-id")

    @property
    def network_config(self) -> dict:
        """Network config read from LXD socket config/user.network-config.

        If none is present, then we generate fallback configuration.
        """
        if self._network_config == sources.UNSET:
            if self._crawled_metadata == sources.UNSET:
                self._get_data()
            if isinstance(self._crawled_metadata, dict):
                if self._crawled_metadata.get("network-config"):
                    LOG.debug("LXD datasource using provided network config")
                    self._network_config = self._crawled_metadata[
                        "network-config"
                    ]
                elif self._crawled_metadata.get("devices"):
                    # If no explicit network config, but we have net devices
                    # available to us, find the primary and set it up.
                    devices: List[str] = [
                        k
                        for k, v in self._crawled_metadata["devices"].items()
                        if v["type"] == "nic"
                    ]
                    self._network_config = generate_network_config(devices)
        if self._network_config == sources.UNSET:
            # We know nothing about network, so setup fallback
            LOG.debug(
                "LXD datasource generating network config using fallback."
            )
            self._network_config = generate_network_config()

        return cast(dict, self._network_config)


def is_platform_viable() -> bool:
    """Return True when this platform appears to have an LXD socket."""
    if os.path.exists(LXD_SOCKET_PATH):
        return stat.S_ISSOCK(os.lstat(LXD_SOCKET_PATH).st_mode)
    return False


def _get_json_response(
    session: requests.Session, url: str, do_raise: bool = True
):
    url_response = _do_request(session, url, do_raise)
    if not url_response.ok:
        LOG.debug(
            "Skipping %s on [HTTP:%d]:%s",
            url,
            url_response.status_code,
            url_response.content.decode("utf-8"),
        )
        return {}
    try:
        return url_response.json()
    except JSONDecodeError as exc:
        raise sources.InvalidMetaDataException(
            "Unable to process LXD config at {url}."
            " Expected JSON but found: {resp}".format(
                url=url, resp=url_response.content.decode("utf-8")
            )
        ) from exc


def _do_request(
    session: requests.Session, url: str, do_raise: bool = True
) -> requests.Response:
    for retries in range(30, 0, -1):
        response = session.get(url)
        if 500 == response.status_code:
            # retry every 0.1 seconds for 3 seconds in the case of 500 error
            # tis evil, but it also works around a bug
            time.sleep(0.1)
            LOG.warning(
                "[GET] [HTTP:%d] %s, retrying %d more time(s)",
                response.status_code,
                url,
                retries,
            )
        else:
            break
    LOG.debug("[GET] [HTTP:%d] %s", response.status_code, url)
    if do_raise and not response.ok:
        raise sources.InvalidMetaDataException(
            "Invalid HTTP response [{code}] from {route}: {resp}".format(
                code=response.status_code,
                route=url,
                resp=response.content.decode("utf-8"),
            )
        )
    return response


class MetaDataKeys(Flag):
    NONE = auto()
    CONFIG = auto()
    DEVICES = auto()
    META_DATA = auto()
    ALL = CONFIG | DEVICES | META_DATA  # pylint: disable=E1131


class _MetaDataReader:
    def __init__(self, api_version: str = LXD_SOCKET_API_VERSION):
        self.api_version = api_version
        self._version_url = url_helper.combine_url(LXD_URL, self.api_version)

    def _process_config(self, session: requests.Session) -> dict:
        """Iterate on LXD API config items. Promoting CONFIG_KEY_ALIASES

        Any CONFIG_KEY_ALIASES which affect cloud-init behavior are promoted
        as top-level configuration keys: user-data, network-data, vendor-data.

        LXD's cloud-init.* config keys override any user.* config keys.
        Log debug messages if any user.* keys are overridden by the related
        cloud-init.* key.
        """
        config: dict = {"config": {}}
        config_url = url_helper.combine_url(self._version_url, "config")
        # Represent all advertized/available config routes under
        # the dict path {LXD_SOCKET_API_VERSION: {config: {...}}.
        config_routes = _get_json_response(session, config_url)

        # Sorting keys to ensure we always process in alphabetical order.
        # cloud-init.* keys will sort before user.* keys which is preferred
        # precedence.
        for config_route in sorted(config_routes):
            config_route_url = url_helper.combine_url(LXD_URL, config_route)
            config_route_response = _do_request(
                session, config_route_url, do_raise=False
            )
            response_text = config_route_response.content.decode("utf-8")
            if not config_route_response.ok:
                LOG.debug(
                    "Skipping %s on [HTTP:%d]:%s",
                    config_route_url,
                    config_route_response.status_code,
                    response_text,
                )
                continue

            cfg_key = config_route.rpartition("/")[-1]
            # Leave raw data values/format unchanged to represent it in
            # instance-data.json for cloud-init query or jinja template
            # use.
            config["config"][cfg_key] = response_text
            # Promote common CONFIG_KEY_ALIASES to top-level keys.
            if cfg_key in CONFIG_KEY_ALIASES:
                # Due to sort of config_routes, promote cloud-init.*
                # aliases before user.*. This allows user.* keys to act as
                # fallback config on old LXD, with new cloud-init images.
                if CONFIG_KEY_ALIASES[cfg_key] not in config:
                    config[CONFIG_KEY_ALIASES[cfg_key]] = response_text
                else:
                    LOG.warning(
                        "Ignoring LXD config %s in favor of %s value.",
                        cfg_key,
                        cfg_key.replace("user", "cloud-init", 1),
                    )
        return config

    def __call__(self, *, metadata_keys: MetaDataKeys) -> dict:
        with requests.Session() as session:
            session.mount(self._version_url, LXDSocketAdapter())
            # Document API version read
            md: dict = {"_metadata_api_version": self.api_version}
            if MetaDataKeys.META_DATA in metadata_keys:
                md_route = url_helper.combine_url(
                    self._version_url, "meta-data"
                )
                md["meta-data"] = _do_request(
                    session, md_route
                ).content.decode("utf-8")
            if MetaDataKeys.CONFIG in metadata_keys:
                md.update(self._process_config(session))
            if MetaDataKeys.DEVICES in metadata_keys:
                url = url_helper.combine_url(self._version_url, "devices")
                devices = _get_json_response(session, url, do_raise=False)
                if devices:
                    md["devices"] = devices
            return md


def read_metadata(
    api_version: str = LXD_SOCKET_API_VERSION,
    metadata_keys: MetaDataKeys = MetaDataKeys.ALL,
) -> dict:
    """Fetch metadata from the /dev/lxd/socket routes.

    Perform a number of HTTP GETs on known routes on the devlxd socket API.
    Minimally all containers must respond to <LXD_SOCKET_API_VERSION>/meta-data
    when the LXD configuration setting `security.devlxd` is true.

    When `security.devlxd` is false, no /dev/lxd/socket file exists. This
    datasource will return False from `is_platform_viable` in that case.

    Perform a GET of <LXD_SOCKET_API_VERSION>/config` and walk all `user.*`
    configuration keys, storing all keys and values under a dict key
        LXD_SOCKET_API_VERSION: config {...}.

    In the presence of the following optional user config keys,
    create top level aliases:
      - user.user-data -> user-data
      - user.vendor-data -> vendor-data
      - user.network-config -> network-config

    :param api_version:
        LXD API version to operated with.
    :param metadata_keys:
        Instance of `MetaDataKeys` indicating what keys to fetch.
    :return:
        A dict with the following optional keys: meta-data, user-data,
        vendor-data, network-config, network_mode, devices.

        Below <LXD_SOCKET_API_VERSION> is a dict representation of all raw
        configuration keys and values provided to the container surfaced by
        the socket under the /1.0/config/ route.
    """
    return _MetaDataReader(api_version=api_version)(
        metadata_keys=metadata_keys
    )


# Used to match classes to dependencies
datasources = [
    (DataSourceLXD, (sources.DEP_FILESYSTEM,)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)


if __name__ == "__main__":
    import argparse

    description = """Query LXD metadata and emit a JSON object."""
    parser = argparse.ArgumentParser(description=description)
    parser.parse_args()
    print(
        atomic_helper.json_dumps(read_metadata(metadata_keys=MetaDataKeys.ALL))
    )
