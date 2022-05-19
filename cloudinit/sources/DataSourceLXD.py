"""Datasource for LXD, reads /dev/lxd/sock representaton of instance data.

Notes:
 * This datasource replaces previous NoCloud datasource for LXD.
 * Older LXD images may not have updates for cloud-init so NoCloud may
   still be detected on those images.
 * Detect LXD datasource when /dev/lxd/sock is an active socket file.
 * Info on dev-lxd API: https://linuxcontainers.org/lxd/docs/master/dev-lxd
 * TODO( Hotplug support using websockets API 1.0/events )
"""

import os
import socket
import stat
from json.decoder import JSONDecodeError

import requests
from requests.adapters import HTTPAdapter

# pylint fails to import the two modules below.
# These are imported via requests.packages rather than urllib3 because:
#  a.) the provider of the requests package should ensure that urllib3
#      contained in it is consistent/correct.
#  b.) cloud-init does not specifically have a dependency on urllib3
#
# For future reference, see:
#   https://github.com/kennethreitz/requests/pull/2375
#   https://github.com/requests/requests/issues/4104
# pylint: disable=E0401
from requests.packages.urllib3.connection import HTTPConnection
from requests.packages.urllib3.connectionpool import HTTPConnectionPool

from cloudinit import log as logging
from cloudinit import sources, subp, util

LOG = logging.getLogger(__name__)

LXD_SOCKET_PATH = "/dev/lxd/sock"
LXD_SOCKET_API_VERSION = "1.0"

# Config key mappings to alias as top-level instance data keys
CONFIG_KEY_ALIASES = {
    "cloud-init.user-data": "user-data",
    "cloud-init.network-config": "network-config",
    "cloud-init.vendor-data": "vendor-data",
    "user.user-data": "user-data",
    "user.network-config": "network-config",
    "user.vendor-data": "vendor-data",
}


def generate_fallback_network_config() -> dict:
    """Return network config V1 dict representing instance network config."""
    network_v1 = {
        "version": 1,
        "config": [
            {
                "type": "physical",
                "name": "eth0",
                "subnets": [{"type": "dhcp", "control": "auto"}],
            }
        ],
    }
    if subp.which("systemd-detect-virt"):
        try:
            virt_type, _ = subp.subp(["systemd-detect-virt"])
        except subp.ProcessExecutionError as err:
            LOG.warning(
                "Unable to run systemd-detect-virt: %s."
                " Rendering default network config.",
                err,
            )
            return network_v1
        if virt_type.strip() in (
            "kvm",
            "qemu",
        ):  # instance.type VIRTUAL-MACHINE
            arch = util.system_info()["uname"][4]
            if arch == "ppc64le":
                network_v1["config"][0]["name"] = "enp0s5"
            elif arch == "s390x":
                network_v1["config"][0]["name"] = "enc9"
            else:
                network_v1["config"][0]["name"] = "enp5s0"
    return network_v1


class SocketHTTPConnection(HTTPConnection):
    def __init__(self, socket_path):
        super().__init__("localhost")
        self.socket_path = socket_path

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

    _network_config = sources.UNSET
    _crawled_metadata = sources.UNSET

    sensitive_metadata_keys = (
        "merged_cfg",
        "user.meta-data",
        "user.vendor-data",
        "user.user-data",
    )

    def _is_platform_viable(self) -> bool:
        """Check platform environment to report if this datasource may run."""
        return is_platform_viable()

    def _get_data(self) -> bool:
        """Crawl LXD socket API instance data and return True on success"""
        if not self._is_platform_viable():
            LOG.debug("Not an LXD datasource: No LXD socket found.")
            return False

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
        if not isinstance(self.metadata, dict):
            self.metadata = util.mergemanydict(
                [util.load_yaml(self.metadata), user_metadata]
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
        response = read_metadata(metadata_only=True)
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
            if self._crawled_metadata.get("network-config"):
                self._network_config = self._crawled_metadata.get(
                    "network-config"
                )
            else:
                self._network_config = generate_fallback_network_config()
        return self._network_config


def is_platform_viable() -> bool:
    """Return True when this platform appears to have an LXD socket."""
    if os.path.exists(LXD_SOCKET_PATH):
        return stat.S_ISSOCK(os.lstat(LXD_SOCKET_PATH).st_mode)
    return False


def read_metadata(
    api_version: str = LXD_SOCKET_API_VERSION, metadata_only: bool = False
) -> dict:
    """Fetch metadata from the /dev/lxd/socket routes.

    Perform a number of HTTP GETs on known routes on the devlxd socket API.
    Minimally all containers must respond to http://lxd/1.0/meta-data when
    the LXD configuration setting `security.devlxd` is true.

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

    :return:
        A dict with the following mandatory key: meta-data.
        Optional keys: user-data, vendor-data, network-config, network_mode

        Below <LXD_SOCKET_API_VERSION> is a dict representation of all raw
        configuration keys and values provided to the container surfaced by
        the socket under the /1.0/config/ route.
    """
    md = {}
    lxd_url = "http://lxd"
    version_url = lxd_url + "/" + api_version + "/"
    with requests.Session() as session:
        session.mount(version_url, LXDSocketAdapter())
        # Raw meta-data as text
        md_route = "{route}meta-data".format(route=version_url)
        response = session.get(md_route)
        LOG.debug("[GET] [HTTP:%d] %s", response.status_code, md_route)
        if not response.ok:
            raise sources.InvalidMetaDataException(
                "Invalid HTTP response [{code}] from {route}: {resp}".format(
                    code=response.status_code,
                    route=md_route,
                    resp=response.text,
                )
            )

        md["meta-data"] = response.text
        if metadata_only:
            return md  # Skip network-data, vendor-data, user-data

        md = {
            "_metadata_api_version": api_version,  # Document API version read
            "config": {},
            "meta-data": md["meta-data"],
        }

        config_url = version_url + "config"
        # Represent all advertized/available config routes under
        # the dict path {LXD_SOCKET_API_VERSION: {config: {...}}.
        response = session.get(config_url)
        LOG.debug("[GET] [HTTP:%d] %s", response.status_code, config_url)
        if not response.ok:
            raise sources.InvalidMetaDataException(
                "Invalid HTTP response [{code}] from {route}: {resp}".format(
                    code=response.status_code,
                    route=config_url,
                    resp=response.text,
                )
            )
        try:
            config_routes = response.json()
        except JSONDecodeError as exc:
            raise sources.InvalidMetaDataException(
                "Unable to determine cloud-init config from {route}."
                " Expected JSON but found: {resp}".format(
                    route=config_url, resp=response.text
                )
            ) from exc

        # Sorting keys to ensure we always process in alphabetical order.
        # cloud-init.* keys will sort before user.* keys which is preferred
        # precedence.
        for config_route in sorted(config_routes):
            url = "http://lxd{route}".format(route=config_route)
            response = session.get(url)
            LOG.debug("[GET] [HTTP:%d] %s", response.status_code, url)
            if response.ok:
                cfg_key = config_route.rpartition("/")[-1]
                # Leave raw data values/format unchanged to represent it in
                # instance-data.json for cloud-init query or jinja template
                # use.
                md["config"][cfg_key] = response.text
                # Promote common CONFIG_KEY_ALIASES to top-level keys.
                if cfg_key in CONFIG_KEY_ALIASES:
                    # Due to sort of config_routes, promote cloud-init.*
                    # aliases before user.*. This allows user.* keys to act as
                    # fallback config on old LXD, with new cloud-init images.
                    if CONFIG_KEY_ALIASES[cfg_key] not in md:
                        md[CONFIG_KEY_ALIASES[cfg_key]] = response.text
                    else:
                        LOG.warning(
                            "Ignoring LXD config %s in favor of %s value.",
                            cfg_key,
                            cfg_key.replace("user", "cloud-init", 1),
                        )
            else:
                LOG.debug(
                    "Skipping %s on [HTTP:%d]:%s",
                    url,
                    response.status_code,
                    response.text,
                )
    return md


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
    print(util.json_dumps(read_metadata()))
# vi: ts=4 expandtab
