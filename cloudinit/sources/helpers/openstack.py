# Copyright (C) 2012 Canonical Ltd.
# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import abc
import base64
import copy
import functools
import logging
import os

from cloudinit import net, sources, subp, url_helper, util
from cloudinit.sources import BrokenMetadata
from cloudinit.sources.helpers import ec2

# See https://docs.openstack.org/user-guide/cli-config-drive.html

LOG = logging.getLogger(__name__)

FILES_V1 = {
    # Path <-> (metadata key name, translator function, default value)
    "etc/network/interfaces": ("network_config", lambda x: x, ""),
    "meta.js": ("meta_js", util.load_json, {}),
    "root/.ssh/authorized_keys": ("authorized_keys", lambda x: x, ""),
}
KEY_COPIES = (
    # Cloud-init metadata names <-> (metadata key, is required)
    ("local-hostname", "hostname", False),
    ("instance-id", "uuid", True),
)

# Versions and names taken from nova source nova/api/metadata/base.py
OS_LATEST = "latest"
OS_FOLSOM = "2012-08-10"
OS_GRIZZLY = "2013-04-04"
OS_HAVANA = "2013-10-17"
OS_LIBERTY = "2015-10-15"
# NEWTON_ONE adds 'devices' to md (sriov-pf-passthrough-neutron-port-vlan)
OS_NEWTON_ONE = "2016-06-30"
# NEWTON_TWO adds vendor_data2.json (vendordata-reboot)
OS_NEWTON_TWO = "2016-10-06"
# OS_OCATA adds 'vif' field to devices (sriov-pf-passthrough-neutron-port-vlan)
OS_OCATA = "2017-02-22"
# OS_ROCKY adds a vf_trusted field to devices (sriov-trusted-vfs)
OS_ROCKY = "2018-08-27"


# keep this in chronological order. new supported versions go at the end.
OS_VERSIONS = (
    OS_FOLSOM,
    OS_GRIZZLY,
    OS_HAVANA,
    OS_LIBERTY,
    OS_NEWTON_ONE,
    OS_NEWTON_TWO,
    OS_OCATA,
    OS_ROCKY,
)

KNOWN_PHYSICAL_TYPES = (
    None,
    "bgpovs",  # not present in OpenStack upstream but used on OVH cloud.
    "bridge",
    "cascading",  # not present in OpenStack upstream, used on OpenTelekomCloud
    "dvs",
    "ethernet",
    "hw_veb",
    "hyperv",
    "ovs",
    "phy",
    "tap",
    "vhostuser",
    "vif",
)


class NonReadable(IOError):
    pass


class SourceMixin:
    def _ec2_name_to_device(self, name):
        if not self.ec2_metadata:
            return None
        bdm = self.ec2_metadata.get("block-device-mapping", {})
        for (ent_name, device) in bdm.items():
            if name == ent_name:
                return device
        return None

    def get_public_ssh_keys(self):
        name = "public_keys"
        if self.version == 1:
            name = "public-keys"
        return sources.normalize_pubkey_data(self.metadata.get(name))

    def _os_name_to_device(self, name):
        device = None
        try:
            criteria = "LABEL=%s" % (name)
            if name == "swap":
                criteria = "TYPE=%s" % (name)
            dev_entries = util.find_devs_with(criteria)
            if dev_entries:
                device = dev_entries[0]
        except subp.ProcessExecutionError:
            pass
        return device

    def _validate_device_name(self, device):
        if not device:
            return None
        if not device.startswith("/"):
            device = "/dev/%s" % device
        if os.path.exists(device):
            return device
        # Durn, try adjusting the mapping
        remapped = self._remap_device(os.path.basename(device))
        if remapped:
            LOG.debug("Remapped device name %s => %s", device, remapped)
            return remapped
        return None

    def device_name_to_device(self, name):
        # Translate a 'name' to a 'physical' device
        if not name:
            return None
        # Try the ec2 mapping first
        names = [name]
        if name == "root":
            names.insert(0, "ami")
        if name == "ami":
            names.append("root")
        device = None
        LOG.debug("Using ec2 style lookup to find device %s", names)
        for n in names:
            device = self._ec2_name_to_device(n)
            device = self._validate_device_name(device)
            if device:
                break
        # Try the openstack way second
        if not device:
            LOG.debug("Using openstack style lookup to find device %s", names)
            for n in names:
                device = self._os_name_to_device(n)
                device = self._validate_device_name(device)
                if device:
                    break
        # Ok give up...
        if not device:
            return None
        else:
            LOG.debug("Mapped %s to device %s", name, device)
            return device


class BaseReader(metaclass=abc.ABCMeta):
    def __init__(self, base_path):
        self.base_path = base_path

    @abc.abstractmethod
    def _path_join(self, base, *add_ons):
        pass

    @abc.abstractmethod
    def _path_read(self, path, decode=False):
        pass

    @abc.abstractmethod
    def _fetch_available_versions(self):
        pass

    @abc.abstractmethod
    def _read_ec2_metadata(self):
        pass

    def _find_working_version(self):
        try:
            versions_available = self._fetch_available_versions()
        except Exception as e:
            LOG.debug(
                "Unable to read openstack versions from %s due to: %s",
                self.base_path,
                e,
            )
            versions_available = []

        # openstack.OS_VERSIONS is stored in chronological order, so
        # reverse it to check newest first.
        supported = [v for v in reversed(list(OS_VERSIONS))]
        selected_version = OS_LATEST

        for potential_version in supported:
            if potential_version not in versions_available:
                continue
            selected_version = potential_version
            break

        LOG.debug(
            "Selected version '%s' from %s",
            selected_version,
            versions_available,
        )
        return selected_version

    def _read_content_path(self, item, decode=False):
        path = item.get("content_path", "").lstrip("/")
        path_pieces = path.split("/")
        valid_pieces = [p for p in path_pieces if len(p)]
        if not valid_pieces:
            raise BrokenMetadata("Item %s has no valid content path" % (item))
        path = self._path_join(self.base_path, "openstack", *path_pieces)
        return self._path_read(path, decode=decode)

    def read_v2(self):
        """Reads a version 2 formatted location.

        Return a dict with metadata, userdata, ec2-metadata, dsmode,
        network_config, files and version (2).

        If not a valid location, raise a NonReadable exception.
        """

        load_json_anytype = functools.partial(
            util.load_json, root_types=(dict, list, str)
        )

        def datafiles(version):
            files = {}
            files["metadata"] = (
                # File path to read
                self._path_join("openstack", version, "meta_data.json"),
                # Is it required?
                True,
                # Translator function (applied after loading)
                util.load_json,
            )
            files["userdata"] = (
                self._path_join("openstack", version, "user_data"),
                False,
                lambda x: x,
            )
            files["vendordata"] = (
                self._path_join("openstack", version, "vendor_data.json"),
                False,
                load_json_anytype,
            )
            files["vendordata2"] = (
                self._path_join("openstack", version, "vendor_data2.json"),
                False,
                load_json_anytype,
            )
            files["networkdata"] = (
                self._path_join("openstack", version, "network_data.json"),
                False,
                load_json_anytype,
            )
            return files

        results = {
            "userdata": "",
            "version": 2,
        }
        data = datafiles(self._find_working_version())
        for (name, (path, required, translator)) in data.items():
            path = self._path_join(self.base_path, path)
            data = None
            found = False
            try:
                data = self._path_read(path)
            except IOError as e:
                if not required:
                    LOG.debug(
                        "Failed reading optional path %s due to: %s", path, e
                    )
                else:
                    LOG.debug(
                        "Failed reading mandatory path %s due to: %s", path, e
                    )
            else:
                found = True
            if required and not found:
                raise NonReadable("Missing mandatory path: %s" % path)
            if found and translator:
                try:
                    data = translator(data)
                except Exception as e:
                    raise BrokenMetadata(
                        "Failed to process path %s: %s" % (path, e)
                    ) from e
            if found:
                results[name] = data

        metadata = results["metadata"]
        if "random_seed" in metadata:
            random_seed = metadata["random_seed"]
            try:
                metadata["random_seed"] = base64.b64decode(random_seed)
            except (ValueError, TypeError) as e:
                raise BrokenMetadata(
                    "Badly formatted metadata random_seed entry: %s" % e
                ) from e

        # load any files that were provided
        files = {}
        metadata_files = metadata.get("files", [])
        for item in metadata_files:
            if "path" not in item:
                continue
            path = item["path"]
            try:
                files[path] = self._read_content_path(item)
            except Exception as e:
                raise BrokenMetadata(
                    "Failed to read provided file %s: %s" % (path, e)
                ) from e
        results["files"] = files

        # The 'network_config' item in metadata is a content pointer
        # to the network config that should be applied. It is just a
        # ubuntu/debian '/etc/network/interfaces' file.
        net_item = metadata.get("network_config", None)
        if net_item:
            try:
                content = self._read_content_path(net_item, decode=True)
                results["network_config"] = content
            except IOError as e:
                raise BrokenMetadata(
                    "Failed to read network configuration: %s" % (e)
                ) from e

        # To openstack, user can specify meta ('nova boot --meta=key=value')
        # and those will appear under metadata['meta'].
        # if they specify 'dsmode' they're indicating the mode that they intend
        # for this datasource to operate in.
        try:
            results["dsmode"] = metadata["meta"]["dsmode"]
        except KeyError:
            pass

        # Read any ec2-metadata (if applicable)
        results["ec2-metadata"] = self._read_ec2_metadata()

        # Perform some misc. metadata key renames...
        for (target_key, source_key, is_required) in KEY_COPIES:
            if is_required and source_key not in metadata:
                raise BrokenMetadata("No '%s' entry in metadata" % source_key)
            if source_key in metadata:
                metadata[target_key] = metadata.get(source_key)
        return results


class ConfigDriveReader(BaseReader):
    def __init__(self, base_path):
        super(ConfigDriveReader, self).__init__(base_path)
        self._versions = None

    def _path_join(self, base, *add_ons):
        components = [base] + list(add_ons)
        return os.path.join(*components)

    def _path_read(self, path, decode=False):
        return (
            util.load_text_file(path)
            if decode
            else util.load_binary_file(path)
        )

    def _fetch_available_versions(self):
        if self._versions is None:
            path = self._path_join(self.base_path, "openstack")
            found = [
                d
                for d in os.listdir(path)
                if os.path.isdir(os.path.join(path))
            ]
            self._versions = sorted(found)
        return self._versions

    def _read_ec2_metadata(self):
        path = self._path_join(
            self.base_path, "ec2", "latest", "meta-data.json"
        )
        if not os.path.exists(path):
            return {}
        else:
            try:
                return util.load_json(self._path_read(path))
            except Exception as e:
                raise BrokenMetadata(
                    "Failed to process path %s: %s" % (path, e)
                ) from e

    def read_v1(self):
        """Reads a version 1 formatted location.

        Return a dict with metadata, userdata, dsmode, files and version (1).

        If not a valid path, raise a NonReadable exception.
        """

        found = {}
        for name in FILES_V1.keys():
            path = self._path_join(self.base_path, name)
            if os.path.exists(path):
                found[name] = path
        if len(found) == 0:
            raise NonReadable("%s: no files found" % (self.base_path))

        md = {}
        for (name, (key, translator, default)) in FILES_V1.items():
            if name in found:
                path = found[name]
                try:
                    contents = self._path_read(path)
                except IOError as e:
                    raise BrokenMetadata("Failed to read: %s" % path) from e
                try:
                    # Disable not-callable pylint check; pylint isn't able to
                    # determine that every member of FILES_V1 has a callable in
                    # the appropriate position
                    md[key] = translator(contents)  # pylint: disable=E1102
                except Exception as e:
                    raise BrokenMetadata(
                        "Failed to process path %s: %s" % (path, e)
                    ) from e
            else:
                md[key] = copy.deepcopy(default)

        keydata = md["authorized_keys"]
        meta_js = md["meta_js"]

        # keydata in meta_js is preferred over "injected"
        keydata = meta_js.get("public-keys", keydata)
        if keydata:
            lines = keydata.splitlines()
            md["public-keys"] = [
                line
                for line in lines
                if len(line) and not line.startswith("#")
            ]

        # config-drive-v1 has no way for openstack to provide the instance-id
        # so we copy that into metadata from the user input
        if "instance-id" in meta_js:
            md["instance-id"] = meta_js["instance-id"]

        results = {
            "version": 1,
            "metadata": md,
        }

        # allow the user to specify 'dsmode' in a meta tag
        if "dsmode" in meta_js:
            results["dsmode"] = meta_js["dsmode"]

        # config-drive-v1 has no way of specifying user-data, so the user has
        # to cheat and stuff it in a meta tag also.
        results["userdata"] = meta_js.get("user-data", "")

        # this implementation does not support files other than
        # network/interfaces and authorized_keys...
        results["files"] = {}

        return results


class MetadataReader(BaseReader):
    def __init__(self, base_url, ssl_details=None, timeout=5, retries=5):
        super(MetadataReader, self).__init__(base_url)
        self.ssl_details = ssl_details
        self.timeout = float(timeout)
        self.retries = int(retries)
        self._versions = None

    def _fetch_available_versions(self):
        # <baseurl>/openstack/ returns a newline separated list of versions
        if self._versions is not None:
            return self._versions
        found = []
        version_path = self._path_join(self.base_path, "openstack")
        content = self._path_read(version_path, decode=True)
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            found.append(line)
        self._versions = found
        return self._versions

    def _path_read(self, path, decode=False):
        def should_retry_cb(_request_args, cause):
            try:
                code = int(cause.code)
                if code >= 400:
                    return False
            except (TypeError, ValueError):
                # Older versions of requests didn't have a code.
                pass
            return True

        response = url_helper.readurl(
            path,
            retries=self.retries,
            ssl_details=self.ssl_details,
            timeout=self.timeout,
            exception_cb=should_retry_cb,
        )
        if decode:
            return response.contents.decode()
        else:
            return response.contents

    def _path_join(self, base, *add_ons):
        return url_helper.combine_url(base, *add_ons)

    def _read_ec2_metadata(self):
        return ec2.get_instance_metadata(
            ssl_details=self.ssl_details,
            timeout=self.timeout,
            retries=self.retries,
        )


# Convert OpenStack ConfigDrive NetworkData json to network_config yaml
def convert_net_json(network_json=None, known_macs=None):
    """Return a dictionary of network_config by parsing provided
       OpenStack ConfigDrive NetworkData json format

    OpenStack network_data.json provides a 3 element dictionary
      - "links" (links are network devices, physical or virtual)
      - "networks" (networks are ip network configurations for one or more
                    links)
      -  services (non-ip services, like dns)

    networks and links are combined via network items referencing specific
    links via a 'link_id' which maps to a links 'id' field.

    To convert this format to network_config yaml, we first iterate over the
    links and then walk the network list to determine if any of the networks
    utilize the current link; if so we generate a subnet entry for the device

    We also need to map network_data.json fields to network_config fields. For
    example, the network_data links 'id' field is equivalent to network_config
    'name' field for devices.  We apply more of this mapping to the various
    link types that we encounter.

    There are additional fields that are populated in the network_data.json
    from OpenStack that are not relevant to network_config yaml, so we
    enumerate a dictionary of valid keys for network_yaml and apply filtering
    to drop these superfluous keys from the network_config yaml.
    """
    if network_json is None:
        return None

    # dict of network_config key for filtering network_json
    valid_keys = {
        "physical": [
            "name",
            "type",
            "mac_address",
            "subnets",
            "params",
            "mtu",
        ],
        "subnet": [
            "type",
            "address",
            "netmask",
            "broadcast",
            "metric",
            "gateway",
            "pointopoint",
            "scope",
            "dns_nameservers",
            "dns_search",
            "routes",
        ],
    }

    links = network_json.get("links", [])
    networks = network_json.get("networks", [])
    services = network_json.get("services", [])

    link_updates = []
    link_id_info = {}
    bond_name_fmt = "bond%d"
    bond_number = 0
    config = []
    for link in links:
        subnets = []
        cfg = dict(
            (k, v) for k, v in link.items() if k in valid_keys["physical"]
        )
        # 'name' is not in openstack spec yet, but we will support it if it is
        # present.  The 'id' in the spec is currently implemented as the host
        # nic's name, meaning something like 'tap-adfasdffd'.  We do not want
        # to name guest devices with such ugly names.
        if "name" in link:
            cfg["name"] = link["name"]

        link_mac_addr = None
        if link.get("ethernet_mac_address"):
            link_mac_addr = link.get("ethernet_mac_address").lower()
            link_id_info[link["id"]] = link_mac_addr

        curinfo = {
            "name": cfg.get("name"),
            "mac": link_mac_addr,
            "id": link["id"],
            "type": link["type"],
        }

        for network in [n for n in networks if n["link"] == link["id"]]:
            subnet = dict(
                (k, v) for k, v in network.items() if k in valid_keys["subnet"]
            )

            if network["type"] == "ipv4_dhcp":
                subnet.update({"type": "dhcp4"})
            elif network["type"] == "ipv6_dhcp":
                subnet.update({"type": "dhcp6"})
            elif network["type"] in [
                "ipv6_slaac",
                "ipv6_dhcpv6-stateless",
                "ipv6_dhcpv6-stateful",
            ]:
                subnet.update({"type": network["type"]})
            elif network["type"] in ["ipv4", "static"]:
                subnet.update(
                    {
                        "type": "static",
                        "address": network.get("ip_address"),
                    }
                )
            elif network["type"] in ["ipv6", "static6"]:
                cfg.update({"accept-ra": False})
                subnet.update(
                    {
                        "type": "static6",
                        "address": network.get("ip_address"),
                    }
                )

            dns_nameservers = [
                service["address"]
                for service in network.get("services", [])
                if service.get("type") == "dns"
            ]
            if dns_nameservers:
                subnet["dns_nameservers"] = dns_nameservers

            # Enable accept_ra for stateful and legacy ipv6_dhcp types
            if network["type"] in ["ipv6_dhcpv6-stateful", "ipv6_dhcp"]:
                cfg.update({"accept-ra": True})

            if network["type"] == "ipv4":
                subnet["ipv4"] = True
            if network["type"] == "ipv6":
                subnet["ipv6"] = True
            subnets.append(subnet)
        cfg.update({"subnets": subnets})
        if link["type"] in ["bond"]:
            params = {}
            if link_mac_addr:
                cfg.update({"mac_address": link_mac_addr})
            for k, v in link.items():
                if k == "bond_links":
                    continue
                elif k.startswith("bond"):
                    # There is a difference in key name formatting for
                    # bond parameters in the cloudinit and OpenStack
                    # network schemas. The keys begin with 'bond-' in the
                    # cloudinit schema but 'bond_' in OpenStack
                    # network_data.json schema. Translate them to what
                    # is expected by cloudinit.
                    translated_key = "bond-{}".format(k.split("bond_", 1)[-1])
                    params.update({translated_key: v})

            # openstack does not provide a name for the bond.
            # they do provide an 'id', but that is possibly non-sensical.
            # so we just create our own name.
            link_name = bond_name_fmt % bond_number
            bond_number += 1

            # bond_links reference links by their id, but we need to add
            # to the network config by their nic name.
            # store that in bond_links_needed, and update these later.
            link_updates.append(
                (
                    cfg,
                    "bond_interfaces",
                    "%s",
                    copy.deepcopy(link["bond_links"]),
                )
            )
            cfg.update({"params": params, "name": link_name})

            curinfo["name"] = link_name
        elif link["type"] in ["vlan"]:
            name = "%s.%s" % (link["vlan_link"], link["vlan_id"])
            cfg.update(
                {
                    "name": name,
                    "vlan_id": link["vlan_id"],
                }
            )
            link_updates.append((cfg, "vlan_link", "%s", link["vlan_link"]))
            link_updates.append(
                (cfg, "name", "%%s.%s" % link["vlan_id"], link["vlan_link"])
            )
            curinfo.update({"mac": link["vlan_mac_address"], "name": name})
        else:
            if link["type"] not in KNOWN_PHYSICAL_TYPES:
                LOG.warning(
                    "Unknown network_data link type (%s); treating as"
                    " physical",
                    link["type"],
                )
            cfg.update({"type": "physical", "mac_address": link_mac_addr})

        config.append(cfg)
        link_id_info[curinfo["id"]] = curinfo

    need_names = [
        d for d in config if d.get("type") == "physical" and "name" not in d
    ]

    if need_names or link_updates:
        if known_macs is None:
            known_macs = net.get_interfaces_by_mac()

        # go through and fill out the link_id_info with names
        for _link_id, info in link_id_info.items():
            if info.get("name"):
                continue
            if info.get("mac") in known_macs:
                info["name"] = known_macs[info["mac"]]

        for d in need_names:
            mac = d.get("mac_address")
            if not mac:
                raise ValueError("No mac_address or name entry for %s" % d)
            if mac not in known_macs:
                raise ValueError("Unable to find a system nic for %s" % d)
            d["name"] = known_macs[mac]

        for cfg, key, fmt, targets in link_updates:
            if isinstance(targets, (list, tuple)):
                cfg[key] = [
                    fmt % link_id_info[target]["name"] for target in targets
                ]
            else:
                cfg[key] = fmt % link_id_info[targets]["name"]

    # Infiniband interfaces may be referenced in network_data.json by a 6 byte
    # Ethernet MAC-style address, and we use that address to look up the
    # interface name above. Now ensure that the hardware address is set to the
    # full 20 byte address.
    ib_known_hwaddrs = net.get_ib_hwaddrs_by_interface()
    if ib_known_hwaddrs:
        for cfg in config:
            if cfg["name"] in ib_known_hwaddrs:
                cfg["mac_address"] = ib_known_hwaddrs[cfg["name"]]
                cfg["type"] = "infiniband"

    for service in services:
        cfg = copy.deepcopy(service)
        cfg.update({"type": "nameserver"})
        config.append(cfg)

    return {"version": 1, "config": config}
