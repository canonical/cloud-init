# Cloud-Init DataSource for VMware
#
# Copyright (c) 2018-2021 VMware, Inc. All Rights Reserved.
#
# Authors: Anish Swaminathan <anishs@vmware.com>
#          Andrew Kutz <akutz@vmware.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Cloud-Init DataSource for VMware

This module provides a cloud-init datasource for VMware systems and supports
multiple transports types, including:

    * EnvVars
    * GuestInfo

Netifaces (https://github.com/al45tair/netifaces)

    Please note this module relies on the netifaces project to introspect the
    runtime, network configuration of the host on which this datasource is
    running. This is in contrast to the rest of cloud-init which uses the
    cloudinit/netinfo module.

    The reasons for using netifaces include:

        * Netifaces is built in C and is more portable across multiple systems
          and more deterministic than shell exec'ing local network commands and
          parsing their output.

        * Netifaces provides a stable way to determine the view of the host's
          network after DHCP has brought the network online. Unlike most other
          datasources, this datasource still provides support for JINJA queries
          based on networking information even when the network is based on a
          DHCP lease. While this does not tie this datasource directly to
          netifaces, it does mean the ability to consistently obtain the
          correct information is paramount.

        * It is currently possible to execute this datasource on macOS
          (which many developers use today) to print the output of the
          get_host_info function. This function calls netifaces to obtain
          the same runtime network configuration that the datasource would
          persist to the local system's instance data.

          However, the netinfo module fails on macOS. The result is either a
          hung operation that requires a SIGINT to return control to the user,
          or, if brew is used to install iproute2mac, the ip commands are used
          but produce output the netinfo module is unable to parse.

          While macOS is not a target of cloud-init, this feature is quite
          useful when working on this datasource.

          For more information about this behavior, please see the following
          PR comment, https://bit.ly/3fG7OVh.

    The authors of this datasource are not opposed to moving away from
    netifaces. The goal may be to eventually do just that. This proviso was
    added to the top of this module as a way to remind future-us and others
    why netifaces was used in the first place in order to either smooth the
    transition away from netifaces or embrace it further up the cloud-init
    stack.
"""

import collections
import copy
import ipaddress
import json
import os
import socket
import time

import netifaces

from cloudinit import dmi
from cloudinit import log as logging
from cloudinit import net, sources, util
from cloudinit.subp import ProcessExecutionError, subp, which

PRODUCT_UUID_FILE_PATH = "/sys/class/dmi/id/product_uuid"

LOG = logging.getLogger(__name__)
NOVAL = "No value found"

DATA_ACCESS_METHOD_ENVVAR = "envvar"
DATA_ACCESS_METHOD_GUESTINFO = "guestinfo"

VMWARE_RPCTOOL = which("vmware-rpctool")
REDACT = "redact"
CLEANUP_GUESTINFO = "cleanup-guestinfo"
VMX_GUESTINFO = "VMX_GUESTINFO"
GUESTINFO_EMPTY_YAML_VAL = "---"

LOCAL_IPV4 = "local-ipv4"
LOCAL_IPV6 = "local-ipv6"
WAIT_ON_NETWORK = "wait-on-network"
WAIT_ON_NETWORK_IPV4 = "ipv4"
WAIT_ON_NETWORK_IPV6 = "ipv6"


class DataSourceVMware(sources.DataSource):
    """
    Setting the hostname:
        The hostname is set by way of the metadata key "local-hostname".

    Setting the instance ID:
        The instance ID may be set by way of the metadata key "instance-id".
        However, if this value is absent then the instance ID is read
        from the file /sys/class/dmi/id/product_uuid.

    Configuring the network:
        The network is configured by setting the metadata key "network"
        with a value consistent with Network Config Versions 1 or 2,
        depending on the Linux distro's version of cloud-init:

            Network Config Version 1 - http://bit.ly/cloudinit-net-conf-v1
            Network Config Version 2 - http://bit.ly/cloudinit-net-conf-v2

        For example, CentOS 7's official cloud-init package is version
        0.7.9 and does not support Network Config Version 2. However,
        this datasource still supports supplying Network Config Version 2
        data as long as the Linux distro's cloud-init package is new
        enough to parse the data.

        The metadata key "network.encoding" may be used to indicate the
        format of the metadata key "network". Valid encodings are base64
        and gzip+base64.
    """

    dsname = "VMware"

    def __init__(self, sys_cfg, distro, paths, ud_proc=None):
        sources.DataSource.__init__(self, sys_cfg, distro, paths, ud_proc)

        self.data_access_method = None
        self.vmware_rpctool = VMWARE_RPCTOOL

    def _get_data(self):
        """
        _get_data loads the metadata, userdata, and vendordata from one of
        the following locations in the given order:

            * envvars
            * guestinfo

        Please note when updating this function with support for new data
        transports, the order should match the order in the dscheck_VMware
        function from the file ds-identify.
        """

        # Initialize the locally scoped metadata, userdata, and vendordata
        # variables. They are assigned below depending on the detected data
        # access method.
        md, ud, vd = None, None, None

        # First check to see if there is data via env vars.
        if os.environ.get(VMX_GUESTINFO, ""):
            md = guestinfo_envvar("metadata")
            ud = guestinfo_envvar("userdata")
            vd = guestinfo_envvar("vendordata")

            if md or ud or vd:
                self.data_access_method = DATA_ACCESS_METHOD_ENVVAR

        # At this point, all additional data transports are valid only on
        # a VMware platform.
        if not self.data_access_method:
            system_type = dmi.read_dmi_data("system-product-name")
            if system_type is None:
                LOG.debug("No system-product-name found")
                return False
            if "vmware" not in system_type.lower():
                LOG.debug("Not a VMware platform")
                return False

        # If no data was detected, check the guestinfo transport next.
        if not self.data_access_method:
            if self.vmware_rpctool:
                md = guestinfo("metadata", self.vmware_rpctool)
                ud = guestinfo("userdata", self.vmware_rpctool)
                vd = guestinfo("vendordata", self.vmware_rpctool)

                if md or ud or vd:
                    self.data_access_method = DATA_ACCESS_METHOD_GUESTINFO

        if not self.data_access_method:
            LOG.error("failed to find a valid data access method")
            return False

        LOG.info("using data access method %s", self._get_subplatform())

        # Get the metadata.
        self.metadata = process_metadata(load_json_or_yaml(md))

        # Get the user data.
        self.userdata_raw = ud

        # Get the vendor data.
        self.vendordata_raw = vd

        # Redact any sensitive information.
        self.redact_keys()

        # get_data returns true if there is any available metadata,
        # userdata, or vendordata.
        if self.metadata or self.userdata_raw or self.vendordata_raw:
            return True
        else:
            return False

    def setup(self, is_new_instance):
        """setup(is_new_instance)

        This is called before user-data and vendor-data have been processed.

        Unless the datasource has set mode to 'local', then networking
        per 'fallback' or per 'network_config' will have been written and
        brought up the OS at this point.
        """

        host_info = wait_on_network(self.metadata)
        LOG.info("got host-info: %s", host_info)

        # Reflect any possible local IPv4 or IPv6 addresses in the guest
        # info.
        advertise_local_ip_addrs(host_info)

        # Ensure the metadata gets updated with information about the
        # host, including the network interfaces, default IP addresses,
        # etc.
        self.metadata = util.mergemanydict([self.metadata, host_info])

        # Persist the instance data for versions of cloud-init that support
        # doing so. This occurs here rather than in the get_data call in
        # order to ensure that the network interfaces are up and can be
        # persisted with the metadata.
        self.persist_instance_data()

    def _get_subplatform(self):
        get_key_name_fn = None
        if self.data_access_method == DATA_ACCESS_METHOD_ENVVAR:
            get_key_name_fn = get_guestinfo_envvar_key_name
        elif self.data_access_method == DATA_ACCESS_METHOD_GUESTINFO:
            get_key_name_fn = get_guestinfo_key_name
        else:
            return sources.METADATA_UNKNOWN

        return "%s (%s)" % (
            self.data_access_method,
            get_key_name_fn("metadata"),
        )

    @property
    def network_config(self):
        if "network" in self.metadata:
            LOG.debug("using metadata network config")
        else:
            LOG.debug("using fallback network config")
            self.metadata["network"] = {
                "config": self.distro.generate_fallback_config(),
            }
        return self.metadata["network"]["config"]

    def get_instance_id(self):
        # Pull the instance ID out of the metadata if present. Otherwise
        # read the file /sys/class/dmi/id/product_uuid for the instance ID.
        if self.metadata and "instance-id" in self.metadata:
            return self.metadata["instance-id"]
        with open(PRODUCT_UUID_FILE_PATH, "r") as id_file:
            self.metadata["instance-id"] = str(id_file.read()).rstrip().lower()
            return self.metadata["instance-id"]

    def get_public_ssh_keys(self):
        for key_name in (
            "public-keys-data",
            "public_keys_data",
            "public-keys",
            "public_keys",
        ):
            if key_name in self.metadata:
                return sources.normalize_pubkey_data(self.metadata[key_name])
        return []

    def redact_keys(self):
        # Determine if there are any keys to redact.
        keys_to_redact = None
        if REDACT in self.metadata:
            keys_to_redact = self.metadata[REDACT]
        elif CLEANUP_GUESTINFO in self.metadata:
            # This is for backwards compatibility.
            keys_to_redact = self.metadata[CLEANUP_GUESTINFO]

        if self.data_access_method == DATA_ACCESS_METHOD_GUESTINFO:
            guestinfo_redact_keys(keys_to_redact, self.vmware_rpctool)


def decode(key, enc_type, data):
    """
    decode returns the decoded string value of data
    key is a string used to identify the data being decoded in log messages
    """
    LOG.debug("Getting encoded data for key=%s, enc=%s", key, enc_type)

    raw_data = None
    if enc_type in ["gzip+base64", "gz+b64"]:
        LOG.debug("Decoding %s format %s", enc_type, key)
        raw_data = util.decomp_gzip(util.b64d(data))
    elif enc_type in ["base64", "b64"]:
        LOG.debug("Decoding %s format %s", enc_type, key)
        raw_data = util.b64d(data)
    else:
        LOG.debug("Plain-text data %s", key)
        raw_data = data

    return util.decode_binary(raw_data)


def get_none_if_empty_val(val):
    """
    get_none_if_empty_val returns None if the provided value, once stripped
    of its trailing whitespace, is empty or equal to GUESTINFO_EMPTY_YAML_VAL.

    The return value is always a string, regardless of whether the input is
    a bytes class or a string.
    """

    # If the provided value is a bytes class, convert it to a string to
    # simplify the rest of this function's logic.
    val = util.decode_binary(val)
    val = val.rstrip()
    if len(val) == 0 or val == GUESTINFO_EMPTY_YAML_VAL:
        return None
    return val


def advertise_local_ip_addrs(host_info):
    """
    advertise_local_ip_addrs gets the local IP address information from
    the provided host_info map and sets the addresses in the guestinfo
    namespace
    """
    if not host_info:
        return

    # Reflect any possible local IPv4 or IPv6 addresses in the guest
    # info.
    local_ipv4 = host_info.get(LOCAL_IPV4)
    if local_ipv4:
        guestinfo_set_value(LOCAL_IPV4, local_ipv4)
        LOG.info("advertised local ipv4 address %s in guestinfo", local_ipv4)

    local_ipv6 = host_info.get(LOCAL_IPV6)
    if local_ipv6:
        guestinfo_set_value(LOCAL_IPV6, local_ipv6)
        LOG.info("advertised local ipv6 address %s in guestinfo", local_ipv6)


def handle_returned_guestinfo_val(key, val):
    """
    handle_returned_guestinfo_val returns the provided value if it is
    not empty or set to GUESTINFO_EMPTY_YAML_VAL, otherwise None is
    returned
    """
    val = get_none_if_empty_val(val)
    if val:
        return val
    LOG.debug("No value found for key %s", key)
    return None


def get_guestinfo_key_name(key):
    return "guestinfo." + key


def get_guestinfo_envvar_key_name(key):
    return ("vmx." + get_guestinfo_key_name(key)).upper().replace(".", "_", -1)


def guestinfo_envvar(key):
    val = guestinfo_envvar_get_value(key)
    if not val:
        return None
    enc_type = guestinfo_envvar_get_value(key + ".encoding")
    return decode(get_guestinfo_envvar_key_name(key), enc_type, val)


def guestinfo_envvar_get_value(key):
    env_key = get_guestinfo_envvar_key_name(key)
    return handle_returned_guestinfo_val(key, os.environ.get(env_key, ""))


def guestinfo(key, vmware_rpctool=VMWARE_RPCTOOL):
    """
    guestinfo returns the guestinfo value for the provided key, decoding
    the value when required
    """
    val = guestinfo_get_value(key, vmware_rpctool)
    if not val:
        return None
    enc_type = guestinfo_get_value(key + ".encoding", vmware_rpctool)
    return decode(get_guestinfo_key_name(key), enc_type, val)


def guestinfo_get_value(key, vmware_rpctool=VMWARE_RPCTOOL):
    """
    Returns a guestinfo value for the specified key.
    """
    LOG.debug("Getting guestinfo value for key %s", key)

    try:
        (stdout, stderr) = subp(
            [
                vmware_rpctool,
                "info-get " + get_guestinfo_key_name(key),
            ]
        )
        if stderr == NOVAL:
            LOG.debug("No value found for key %s", key)
        elif not stdout:
            LOG.error("Failed to get guestinfo value for key %s", key)
        return handle_returned_guestinfo_val(key, stdout)
    except ProcessExecutionError as error:
        if error.stderr == NOVAL:
            LOG.debug("No value found for key %s", key)
        else:
            util.logexc(
                LOG,
                "Failed to get guestinfo value for key %s: %s",
                key,
                error,
            )
    except Exception:
        util.logexc(
            LOG,
            "Unexpected error while trying to get "
            + "guestinfo value for key %s",
            key,
        )

    return None


def guestinfo_set_value(key, value, vmware_rpctool=VMWARE_RPCTOOL):
    """
    Sets a guestinfo value for the specified key. Set value to an empty string
    to clear an existing guestinfo key.
    """

    # If value is an empty string then set it to a single space as it is not
    # possible to set a guestinfo key to an empty string. Setting a guestinfo
    # key to a single space is as close as it gets to clearing an existing
    # guestinfo key.
    if value == "":
        value = " "

    LOG.debug("Setting guestinfo key=%s to value=%s", key, value)

    try:
        subp(
            [
                vmware_rpctool,
                "info-set %s %s" % (get_guestinfo_key_name(key), value),
            ]
        )
        return True
    except ProcessExecutionError as error:
        util.logexc(
            LOG,
            "Failed to set guestinfo key=%s to value=%s: %s",
            key,
            value,
            error,
        )
    except Exception:
        util.logexc(
            LOG,
            "Unexpected error while trying to set "
            + "guestinfo key=%s to value=%s",
            key,
            value,
        )

    return None


def guestinfo_redact_keys(keys, vmware_rpctool=VMWARE_RPCTOOL):
    """
    guestinfo_redact_keys redacts guestinfo of all of the keys in the given
    list. each key will have its value set to "---". Since the value is valid
    YAML, cloud-init can still read it if it tries.
    """
    if not keys:
        return
    if not type(keys) in (list, tuple):
        keys = [keys]
    for key in keys:
        key_name = get_guestinfo_key_name(key)
        LOG.info("clearing %s", key_name)
        if not guestinfo_set_value(
            key, GUESTINFO_EMPTY_YAML_VAL, vmware_rpctool
        ):
            LOG.error("failed to clear %s", key_name)
        LOG.info("clearing %s.encoding", key_name)
        if not guestinfo_set_value(key + ".encoding", "", vmware_rpctool):
            LOG.error("failed to clear %s.encoding", key_name)


def load_json_or_yaml(data):
    """
    load first attempts to unmarshal the provided data as JSON, and if
    that fails then attempts to unmarshal the data as YAML. If data is
    None then a new dictionary is returned.
    """
    if not data:
        return {}
    try:
        return util.load_json(data)
    except (json.JSONDecodeError, TypeError):
        return util.load_yaml(data)


def process_metadata(data):
    """
    process_metadata processes metadata and loads the optional network
    configuration.
    """
    network = None
    if "network" in data:
        network = data["network"]
        del data["network"]

    network_enc = None
    if "network.encoding" in data:
        network_enc = data["network.encoding"]
        del data["network.encoding"]

    if network:
        if isinstance(network, collections.abc.Mapping):
            LOG.debug("network data copied to 'config' key")
            network = {"config": copy.deepcopy(network)}
        else:
            LOG.debug("network data to be decoded %s", network)
            dec_net = decode("metadata.network", network_enc, network)
            network = {
                "config": load_json_or_yaml(dec_net),
            }

        LOG.debug("network data %s", network)
        data["network"] = network

    return data


# Used to match classes to dependencies
datasources = [
    (DataSourceVMware, (sources.DEP_FILESYSTEM,)),  # Run at init-local
    (DataSourceVMware, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
]


def get_datasource_list(depends):
    """
    Return a list of data sources that match this set of dependencies
    """
    return sources.list_from_depends(depends, datasources)


def get_default_ip_addrs():
    """
    Returns the default IPv4 and IPv6 addresses based on the device(s) used for
    the default route. Please note that None may be returned for either address
    family if that family has no default route or if there are multiple
    addresses associated with the device used by the default route for a given
    address.
    """
    # TODO(promote and use netifaces in cloudinit.net* modules)
    gateways = netifaces.gateways()
    if "default" not in gateways:
        return None, None

    default_gw = gateways["default"]
    if (
        netifaces.AF_INET not in default_gw
        and netifaces.AF_INET6 not in default_gw
    ):
        return None, None

    ipv4 = None
    ipv6 = None

    gw4 = default_gw.get(netifaces.AF_INET)
    if gw4:
        _, dev4 = gw4
        addr4_fams = netifaces.ifaddresses(dev4)
        if addr4_fams:
            af_inet4 = addr4_fams.get(netifaces.AF_INET)
            if af_inet4:
                if len(af_inet4) > 1:
                    LOG.warning(
                        "device %s has more than one ipv4 address: %s",
                        dev4,
                        af_inet4,
                    )
                elif "addr" in af_inet4[0]:
                    ipv4 = af_inet4[0]["addr"]

    # Try to get the default IPv6 address by first seeing if there is a default
    # IPv6 route.
    gw6 = default_gw.get(netifaces.AF_INET6)
    if gw6:
        _, dev6 = gw6
        addr6_fams = netifaces.ifaddresses(dev6)
        if addr6_fams:
            af_inet6 = addr6_fams.get(netifaces.AF_INET6)
            if af_inet6:
                if len(af_inet6) > 1:
                    LOG.warning(
                        "device %s has more than one ipv6 address: %s",
                        dev6,
                        af_inet6,
                    )
                elif "addr" in af_inet6[0]:
                    ipv6 = af_inet6[0]["addr"]

    # If there is a default IPv4 address but not IPv6, then see if there is a
    # single IPv6 address associated with the same device associated with the
    # default IPv4 address.
    if ipv4 and not ipv6:
        af_inet6 = addr4_fams.get(netifaces.AF_INET6)
        if af_inet6:
            if len(af_inet6) > 1:
                LOG.warning(
                    "device %s has more than one ipv6 address: %s",
                    dev4,
                    af_inet6,
                )
            elif "addr" in af_inet6[0]:
                ipv6 = af_inet6[0]["addr"]

    # If there is a default IPv6 address but not IPv4, then see if there is a
    # single IPv4 address associated with the same device associated with the
    # default IPv6 address.
    if not ipv4 and ipv6:
        af_inet4 = addr6_fams.get(netifaces.AF_INET)
        if af_inet4:
            if len(af_inet4) > 1:
                LOG.warning(
                    "device %s has more than one ipv4 address: %s",
                    dev6,
                    af_inet4,
                )
            elif "addr" in af_inet4[0]:
                ipv4 = af_inet4[0]["addr"]

    return ipv4, ipv6


# patched socket.getfqdn() - see https://bugs.python.org/issue5004


def getfqdn(name=""):
    """Get fully qualified domain name from name.
    An empty argument is interpreted as meaning the local host.
    """
    # TODO(may want to promote this function to util.getfqdn)
    # TODO(may want to extend util.get_hostname to accept fqdn=True param)
    name = name.strip()
    if not name or name == "0.0.0.0":
        name = util.get_hostname()
    try:
        addrs = socket.getaddrinfo(
            name, None, 0, socket.SOCK_DGRAM, 0, socket.AI_CANONNAME
        )
    except socket.error:
        pass
    else:
        for addr in addrs:
            if addr[3]:
                name = addr[3]
                break
    return name


def is_valid_ip_addr(val):
    """
    Returns false if the address is loopback, link local or unspecified;
    otherwise true is returned.
    """
    addr = net.maybe_get_address(ipaddress.ip_address, val)
    return addr and not (
        addr.is_link_local or addr.is_loopback or addr.is_unspecified
    )


def get_host_info():
    """
    Returns host information such as the host name and network interfaces.
    """
    # TODO(look to promote netifices use up in cloud-init netinfo funcs)
    host_info = {
        "network": {
            "interfaces": {
                "by-mac": collections.OrderedDict(),
                "by-ipv4": collections.OrderedDict(),
                "by-ipv6": collections.OrderedDict(),
            },
        },
    }
    hostname = getfqdn(util.get_hostname())
    if hostname:
        host_info["hostname"] = hostname
        host_info["local-hostname"] = hostname
        host_info["local_hostname"] = hostname

    default_ipv4, default_ipv6 = get_default_ip_addrs()
    if default_ipv4:
        host_info[LOCAL_IPV4] = default_ipv4
    if default_ipv6:
        host_info[LOCAL_IPV6] = default_ipv6

    by_mac = host_info["network"]["interfaces"]["by-mac"]
    by_ipv4 = host_info["network"]["interfaces"]["by-ipv4"]
    by_ipv6 = host_info["network"]["interfaces"]["by-ipv6"]

    ifaces = netifaces.interfaces()
    for dev_name in ifaces:
        addr_fams = netifaces.ifaddresses(dev_name)
        af_link = addr_fams.get(netifaces.AF_LINK)
        af_inet4 = addr_fams.get(netifaces.AF_INET)
        af_inet6 = addr_fams.get(netifaces.AF_INET6)

        mac = None
        if af_link and "addr" in af_link[0]:
            mac = af_link[0]["addr"]

        # Do not bother recording localhost
        if mac == "00:00:00:00:00:00":
            continue

        if mac and (af_inet4 or af_inet6):
            key = mac
            val = {}
            if af_inet4:
                af_inet4_vals = []
                for ip_info in af_inet4:
                    if not is_valid_ip_addr(ip_info["addr"]):
                        continue
                    af_inet4_vals.append(ip_info)
                val["ipv4"] = af_inet4_vals
            if af_inet6:
                af_inet6_vals = []
                for ip_info in af_inet6:
                    if not is_valid_ip_addr(ip_info["addr"]):
                        continue
                    af_inet6_vals.append(ip_info)
                val["ipv6"] = af_inet6_vals
            by_mac[key] = val

        if af_inet4:
            for ip_info in af_inet4:
                key = ip_info["addr"]
                if not is_valid_ip_addr(key):
                    continue
                val = copy.deepcopy(ip_info)
                del val["addr"]
                if mac:
                    val["mac"] = mac
                by_ipv4[key] = val

        if af_inet6:
            for ip_info in af_inet6:
                key = ip_info["addr"]
                if not is_valid_ip_addr(key):
                    continue
                val = copy.deepcopy(ip_info)
                del val["addr"]
                if mac:
                    val["mac"] = mac
                by_ipv6[key] = val

    return host_info


def wait_on_network(metadata):
    # Determine whether we need to wait on the network coming online.
    wait_on_ipv4 = False
    wait_on_ipv6 = False
    if WAIT_ON_NETWORK in metadata:
        wait_on_network = metadata[WAIT_ON_NETWORK]
        if WAIT_ON_NETWORK_IPV4 in wait_on_network:
            wait_on_ipv4_val = wait_on_network[WAIT_ON_NETWORK_IPV4]
            if isinstance(wait_on_ipv4_val, bool):
                wait_on_ipv4 = wait_on_ipv4_val
            else:
                wait_on_ipv4 = util.translate_bool(wait_on_ipv4_val)
        if WAIT_ON_NETWORK_IPV6 in wait_on_network:
            wait_on_ipv6_val = wait_on_network[WAIT_ON_NETWORK_IPV6]
            if isinstance(wait_on_ipv6_val, bool):
                wait_on_ipv6 = wait_on_ipv6_val
            else:
                wait_on_ipv6 = util.translate_bool(wait_on_ipv6_val)

    # Get information about the host.
    host_info, ipv4_ready, ipv6_ready = None, False, False
    while host_info is None:
        # This loop + sleep results in two logs every second while waiting
        # for either ipv4 or ipv6 up. Do we really need to log each iteration
        # or can we log once and log on successful exit?
        host_info = get_host_info()

        network = host_info.get("network") or {}
        interfaces = network.get("interfaces") or {}
        by_ipv4 = interfaces.get("by-ipv4") or {}
        by_ipv6 = interfaces.get("by-ipv6") or {}

        if wait_on_ipv4:
            ipv4_ready = len(by_ipv4) > 0 if by_ipv4 else False
            if not ipv4_ready:
                host_info = None

        if wait_on_ipv6:
            ipv6_ready = len(by_ipv6) > 0 if by_ipv6 else False
            if not ipv6_ready:
                host_info = None

        if host_info is None:
            LOG.debug(
                "waiting on network: wait4=%s, ready4=%s, wait6=%s, ready6=%s",
                wait_on_ipv4,
                ipv4_ready,
                wait_on_ipv6,
                ipv6_ready,
            )
            time.sleep(1)

    LOG.debug("waiting on network complete")
    return host_info


def main():
    """
    Executed when this file is used as a program.
    """
    try:
        logging.setupBasicLogging()
    except Exception:
        pass
    metadata = {
        WAIT_ON_NETWORK: {
            WAIT_ON_NETWORK_IPV4: True,
            WAIT_ON_NETWORK_IPV6: False,
        },
        "network": {"config": {"dhcp": True}},
    }
    host_info = wait_on_network(metadata)
    metadata = util.mergemanydict([metadata, host_info])
    print(util.json_dumps(metadata))


if __name__ == "__main__":
    main()

# vi: ts=4 expandtab
