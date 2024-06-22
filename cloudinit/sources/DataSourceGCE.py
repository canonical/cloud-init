# Author: Vaidas Jablonskis <jablonskis@gmail.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import datetime
import json
import logging
from base64 import b64decode

from cloudinit import dmi, net, sources, url_helper, util
from cloudinit.distros import ug_util
from cloudinit.event import EventScope, EventType
from cloudinit.net.dhcp import NoDHCPLeaseError
from cloudinit.net.ephemeral import EphemeralDHCPv4
from cloudinit.sources import DataSourceHostname

LOG = logging.getLogger(__name__)

MD_V1_URL = "http://metadata.google.internal/computeMetadata/v1/"
BUILTIN_DS_CONFIG = {"metadata_url": MD_V1_URL}
GUEST_ATTRIBUTES_URL = (
    "http://metadata.google.internal/computeMetadata/"
    "v1/instance/guest-attributes"
)
HOSTKEY_NAMESPACE = "hostkeys"
HEADERS = {"Metadata-Flavor": "Google"}
DEFAULT_PRIMARY_INTERFACE = "ens4"


class GoogleMetadataFetcher:
    def __init__(self, metadata_address, num_retries, sec_between_retries):
        self.metadata_address = metadata_address
        self.num_retries = num_retries
        self.sec_between_retries = sec_between_retries

    def get_value(self, path, is_text, is_recursive=False):
        value = None
        try:
            url = self.metadata_address + path
            if is_recursive:
                url += "/?recursive=True"
            resp = url_helper.readurl(
                url=url,
                headers=HEADERS,
                retries=self.num_retries,
                sec_between=self.sec_between_retries,
            )
        except url_helper.UrlError as exc:
            msg = "url %s raised exception %s"
            LOG.debug(msg, path, exc)
        else:
            if resp.code == 200:
                if is_text:
                    value = util.decode_binary(resp.contents)
                else:
                    value = resp.contents.decode("utf-8")
            else:
                LOG.debug("url %s returned code %s", path, resp.code)
        return value


class DataSourceGCE(sources.DataSource):

    dsname = "GCE"
    perform_dhcp_setup = False
    default_update_events = {
        EventScope.NETWORK: {
            EventType.BOOT_NEW_INSTANCE,
            EventType.BOOT,
        }
    }

    def __init__(self, sys_cfg, distro, paths):
        sources.DataSource.__init__(self, sys_cfg, distro, paths)
        self.default_user = None
        if distro:
            (users, _groups) = ug_util.normalize_users_groups(sys_cfg, distro)
            (self.default_user, _user_config) = ug_util.extract_default(users)
        self.metadata = dict()
        self.ds_cfg = util.mergemanydict(
            [
                util.get_cfg_by_path(sys_cfg, ["datasource", "GCE"], {}),
                BUILTIN_DS_CONFIG,
            ]
        )
        self.metadata_address = self.ds_cfg["metadata_url"]

    def _get_data(self):
        url_params = self.get_url_params()
        if self.perform_dhcp_setup:
            candidate_nics = net.find_candidate_nics()
            if DEFAULT_PRIMARY_INTERFACE in candidate_nics:
                candidate_nics.remove(DEFAULT_PRIMARY_INTERFACE)
                candidate_nics.insert(0, DEFAULT_PRIMARY_INTERFACE)
            LOG.debug("Looking for the primary NIC in: %s", candidate_nics)
            assert (
                len(candidate_nics) >= 1
            ), "The instance has to have at least one candidate NIC"
            for candidate_nic in candidate_nics:
                network_context = EphemeralDHCPv4(
                    self.distro,
                    iface=candidate_nic,
                )
                try:
                    with network_context:
                        try:
                            ret = util.log_time(
                                LOG.debug,
                                "Crawl of GCE metadata service",
                                read_md,
                                kwargs={
                                    "address": self.metadata_address,
                                    "url_params": url_params,
                                },
                            )
                        except Exception as e:
                            LOG.debug(
                                "Error fetching IMD with candidate NIC %s: %s",
                                candidate_nic,
                                e,
                            )
                            continue
                except NoDHCPLeaseError:
                    continue
                if ret["success"]:
                    self.distro.fallback_interface = candidate_nic
                    LOG.debug("Primary NIC found: %s.", candidate_nic)
                    break
            if self.distro.fallback_interface is None:
                LOG.warning(
                    "Did not find a fallback interface on %s.", self.cloud_name
                )
        else:
            ret = util.log_time(
                LOG.debug,
                "Crawl of GCE metadata service",
                read_md,
                kwargs={
                    "address": self.metadata_address,
                    "url_params": url_params,
                },
            )

        if not ret["success"]:
            if ret["platform_reports_gce"]:
                LOG.warning(ret["reason"])
            else:
                LOG.debug(ret["reason"])
            return False
        self.metadata = ret["meta-data"]
        self.userdata_raw = ret["user-data"]
        return True

    @property
    def launch_index(self):
        # GCE does not provide launch_index property.
        return None

    def get_instance_id(self):
        return self.metadata["instance-id"]

    def get_public_ssh_keys(self):
        public_keys_data = self.metadata["public-keys-data"]
        return _parse_public_keys(public_keys_data, self.default_user)

    def publish_host_keys(self, hostkeys):
        for key in hostkeys:
            _write_host_key_to_guest_attributes(*key)

    def get_hostname(self, fqdn=False, resolve_ip=False, metadata_only=False):
        # GCE has long FDQN's and has asked for short hostnames.
        return DataSourceHostname(
            self.metadata["local-hostname"].split(".")[0], False
        )

    @property
    def availability_zone(self):
        return self.metadata["availability-zone"]

    @property
    def region(self):
        return self.availability_zone.rsplit("-", 1)[0]


class DataSourceGCELocal(DataSourceGCE):
    perform_dhcp_setup = True


def _write_host_key_to_guest_attributes(key_type, key_value):
    url = "%s/%s/%s" % (GUEST_ATTRIBUTES_URL, HOSTKEY_NAMESPACE, key_type)
    key_value = key_value.encode("utf-8")
    resp = url_helper.readurl(
        url=url,
        data=key_value,
        headers=HEADERS,
        request_method="PUT",
        check_status=False,
    )
    if resp.ok():
        LOG.debug("Wrote %s host key to guest attributes.", key_type)
    else:
        LOG.debug("Unable to write %s host key to guest attributes.", key_type)


def _has_expired(public_key):
    # Check whether an SSH key is expired. Public key input is a single SSH
    # public key in the GCE specific key format documented here:
    # https://cloud.google.com/compute/docs/instances/adding-removing-ssh-keys#sshkeyformat
    try:
        # Check for the Google-specific schema identifier.
        schema, json_str = public_key.split(None, 3)[2:]
    except (ValueError, AttributeError):
        return False

    # Do not expire keys if they do not have the expected schema identifier.
    if schema != "google-ssh":
        return False

    try:
        json_obj = json.loads(json_str)
    except ValueError:
        return False

    # Do not expire keys if there is no expiration timestamp.
    if "expireOn" not in json_obj:
        return False

    expire_str = json_obj["expireOn"]
    format_str = "%Y-%m-%dT%H:%M:%S+0000"
    try:
        expire_time = datetime.datetime.strptime(expire_str, format_str)
    except ValueError:
        return False

    # Expire the key if and only if we have exceeded the expiration timestamp.
    return datetime.datetime.utcnow() > expire_time


def _parse_public_keys(public_keys_data, default_user=None):
    # Parse the SSH key data for the default user account. Public keys input is
    # a list containing SSH public keys in the GCE specific key format
    # documented here:
    # https://cloud.google.com/compute/docs/instances/adding-removing-ssh-keys#sshkeyformat
    public_keys = []
    if not public_keys_data:
        return public_keys
    for public_key in public_keys_data:
        if not public_key or not all(ord(c) < 128 for c in public_key):
            continue
        split_public_key = public_key.split(":", 1)
        if len(split_public_key) != 2:
            continue
        user, key = split_public_key
        if user in ("cloudinit", default_user) and not _has_expired(key):
            public_keys.append(key)
    return public_keys


def read_md(address=None, url_params=None, platform_check=True):

    if address is None:
        address = MD_V1_URL

    ret = {
        "meta-data": None,
        "user-data": None,
        "success": False,
        "reason": None,
    }
    ret["platform_reports_gce"] = platform_reports_gce()

    if platform_check and not ret["platform_reports_gce"]:
        ret["reason"] = "Not running on GCE."
        return ret

    # If we cannot resolve the metadata server, then no point in trying.
    if not util.is_resolvable_url(address):
        LOG.debug("%s is not resolvable", address)
        ret["reason"] = 'address "%s" is not resolvable' % address
        return ret

    # url_map: (our-key, path, required, is_text, is_recursive)
    url_map = [
        ("instance-id", ("instance/id",), True, True, False),
        ("availability-zone", ("instance/zone",), True, True, False),
        ("local-hostname", ("instance/hostname",), True, True, False),
        ("instance-data", ("instance/attributes",), False, False, True),
        ("project-data", ("project/attributes",), False, False, True),
    ]
    metadata_fetcher = GoogleMetadataFetcher(
        address, url_params.num_retries, url_params.sec_between_retries
    )
    md = {}
    # Iterate over url_map keys to get metadata items.
    for (mkey, paths, required, is_text, is_recursive) in url_map:
        value = None
        for path in paths:
            new_value = metadata_fetcher.get_value(path, is_text, is_recursive)
            if new_value is not None:
                value = new_value
        if required and value is None:
            msg = "required key %s returned nothing. not GCE"
            ret["reason"] = msg % mkey
            return ret
        md[mkey] = value

    instance_data = json.loads(md["instance-data"] or "{}")
    project_data = json.loads(md["project-data"] or "{}")
    valid_keys = [instance_data.get("sshKeys"), instance_data.get("ssh-keys")]
    block_project = instance_data.get("block-project-ssh-keys", "").lower()
    if block_project != "true" and not instance_data.get("sshKeys"):
        valid_keys.append(project_data.get("ssh-keys"))
        valid_keys.append(project_data.get("sshKeys"))
    public_keys_data = "\n".join([key for key in valid_keys if key])
    md["public-keys-data"] = public_keys_data.splitlines()

    if md["availability-zone"]:
        md["availability-zone"] = md["availability-zone"].split("/")[-1]

    if "user-data" in instance_data:
        # instance_data was json, so values are all utf-8 strings.
        ud = instance_data["user-data"].encode("utf-8")
        encoding = instance_data.get("user-data-encoding")
        if encoding == "base64":
            ud = b64decode(ud)
        elif encoding:
            LOG.warning("unknown user-data-encoding: %s, ignoring", encoding)
        ret["user-data"] = ud

    ret["meta-data"] = md
    ret["success"] = True

    return ret


def platform_reports_gce():
    pname = dmi.read_dmi_data("system-product-name") or "N/A"
    if pname == "Google Compute Engine" or pname == "Google":
        return True

    # system-product-name is not always guaranteed (LP: #1674861)
    serial = dmi.read_dmi_data("system-serial-number") or "N/A"
    if serial.startswith("GoogleCloud-"):
        return True

    LOG.debug(
        "Not running on google cloud. product-name=%s serial=%s", pname, serial
    )
    return False


# Used to match classes to dependencies.
datasources = [
    (DataSourceGCELocal, (sources.DEP_FILESYSTEM,)),
    (DataSourceGCE, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
]


# Return a list of data sources that match this set of dependencies.
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)


if __name__ == "__main__":
    import argparse
    import sys
    from base64 import b64encode

    parser = argparse.ArgumentParser(description="Query GCE Metadata Service")
    parser.add_argument(
        "--endpoint",
        metavar="URL",
        help="The url of the metadata service.",
        default=MD_V1_URL,
    )
    parser.add_argument(
        "--no-platform-check",
        dest="platform_check",
        help="Ignore smbios platform check",
        action="store_false",
        default=True,
    )
    args = parser.parse_args()
    data = read_md(address=args.endpoint, platform_check=args.platform_check)
    if "user-data" in data:
        # user-data is bytes not string like other things. Handle it specially.
        # If it can be represented as utf-8 then do so. Otherwise print base64
        # encoded value in the key user-data-b64.
        try:
            data["user-data"] = data["user-data"].decode()
        except UnicodeDecodeError:
            sys.stderr.write(
                "User-data cannot be decoded. Writing as base64\n"
            )
            del data["user-data"]
            # b64encode returns a bytes value. Decode to get the string.
            data["user-data-b64"] = b64encode(data["user-data"]).decode()

    print(json.dumps(data, indent=1, sort_keys=True, separators=(",", ": ")))
