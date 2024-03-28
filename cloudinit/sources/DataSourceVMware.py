# Cloud-Init DataSource for VMware
#
# Copyright (c) 2018-2023 VMware, Inc. All Rights Reserved.
#
# Authors: Anish Swaminathan <anishs@vmware.com>
#          Andrew Kutz <akutz@vmware.com>
#          Pengpeng Sun <pengpengs@vmware.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Cloud-Init DataSource for VMware

This module provides a cloud-init datasource for VMware systems and supports
multiple transports types, including:

    * EnvVars
    * GuestInfo
    * IMC (Guest Customization)
"""

import collections
import copy
import ipaddress
import json
import logging
import os
import socket
import time

from cloudinit import atomic_helper, dmi, log, net, netinfo, sources, util
from cloudinit.sources.helpers.vmware.imc import guestcust_util
from cloudinit.subp import ProcessExecutionError, subp, which

PRODUCT_UUID_FILE_PATH = "/sys/class/dmi/id/product_uuid"

LOG = logging.getLogger(__name__)
NOVAL = "No value found"

# Data transports names
DATA_ACCESS_METHOD_ENVVAR = "envvar"
DATA_ACCESS_METHOD_GUESTINFO = "guestinfo"
DATA_ACCESS_METHOD_IMC = "imc"

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
        0.7.9 and does not support Network Config Version 2.

        imc transport:
            Either Network Config Version 1 or Network Config Version 2 is
            supported which depends on the customization type.
            For LinuxPrep customization, Network config Version 1 data is
            parsed from the customization specification.
            For CloudinitPrep customization, Network config Version 2 data
            is parsed from the customization specification.

        envvar and guestinfo transports:
            Network Config Version 2 data is supported as long as the Linux
            distro's cloud-init package is new enough to parse the data.
            The metadata key "network.encoding" may be used to indicate the
            format of the metadata key "network". Valid encodings are base64
            and gzip+base64.
    """

    dsname = "VMware"

    def __init__(self, sys_cfg, distro, paths, ud_proc=None):
        sources.DataSource.__init__(self, sys_cfg, distro, paths, ud_proc)

        self.cfg = {}
        self.data_access_method = None
        self.rpctool = None
        self.rpctool_fn = None

        # A list includes all possible data transports, each tuple represents
        # one data transport type. This datasource will try to get data from
        # each of transports follows the tuples order in this list.
        # A tuple has 3 elements which are:
        # 1. The transport name
        # 2. The function name to get data for the transport
        # 3. A boolean tells whether the transport requires VMware platform
        self.possible_data_access_method_list = [
            (DATA_ACCESS_METHOD_ENVVAR, self.get_envvar_data_fn, False),
            (DATA_ACCESS_METHOD_GUESTINFO, self.get_guestinfo_data_fn, True),
            (DATA_ACCESS_METHOD_IMC, self.get_imc_data_fn, True),
        ]

    def _unpickle(self, ci_pkl_version: int) -> None:
        super()._unpickle(ci_pkl_version)
        for attr in ("rpctool", "rpctool_fn"):
            if not hasattr(self, attr):
                setattr(self, attr, None)
        if not hasattr(self, "cfg"):
            setattr(self, "cfg", {})
        if not hasattr(self, "possible_data_access_method_list"):
            setattr(
                self,
                "possible_data_access_method_list",
                [
                    (
                        DATA_ACCESS_METHOD_ENVVAR,
                        self.get_envvar_data_fn,
                        False,
                    ),
                    (
                        DATA_ACCESS_METHOD_GUESTINFO,
                        self.get_guestinfo_data_fn,
                        True,
                    ),
                    (DATA_ACCESS_METHOD_IMC, self.get_imc_data_fn, True),
                ],
            )

    def __str__(self):
        root = sources.DataSource.__str__(self)
        return "%s [seed=%s]" % (root, self.data_access_method)

    def _get_data(self):
        """
        _get_data loads the metadata, userdata, and vendordata from one of
        the following locations in the given order:

            * envvars
            * guestinfo
            * imc

        Please note when updating this function with support for new data
        transports, the order should match the order in the dscheck_VMware
        function from the file ds-identify.
        """

        # Initialize the locally scoped metadata, userdata, and vendordata
        # variables. They are assigned below depending on the detected data
        # access method.
        md, ud, vd = None, None, None

        # Crawl data from all possible data transports
        for (
            data_access_method,
            get_data_fn,
            require_vmware_platform,
        ) in self.possible_data_access_method_list:
            if require_vmware_platform and not is_vmware_platform():
                continue
            (md, ud, vd) = get_data_fn()
            if md or ud or vd:
                self.data_access_method = data_access_method
                break

        if not self.data_access_method:
            LOG.debug("failed to find a valid data access method")
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
        advertise_local_ip_addrs(host_info, self.rpctool, self.rpctool_fn)

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
        elif self.data_access_method == DATA_ACCESS_METHOD_IMC:
            get_key_name_fn = get_imc_key_name
        else:
            return sources.METADATA_UNKNOWN

        return "%s (%s)" % (
            self.data_access_method,
            get_key_name_fn("metadata"),
        )

    # The data sources' config_obj is a cloud-config formatted
    # object that came to it from ways other than cloud-config
    # because cloud-config content would be handled elsewhere
    def get_config_obj(self):
        return self.cfg

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

    def check_if_fallback_is_allowed(self):
        if (
            self.data_access_method
            and self.data_access_method == DATA_ACCESS_METHOD_IMC
            and is_vmware_platform()
        ):
            LOG.debug(
                "Cache fallback is allowed for : %s", self._get_subplatform()
            )
            return True
        return False

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
            guestinfo_redact_keys(
                keys_to_redact, self.rpctool, self.rpctool_fn
            )

    def get_envvar_data_fn(self):
        """
        check to see if there is data via env vars
        """
        md, ud, vd = None, None, None
        if os.environ.get(VMX_GUESTINFO, ""):
            md = guestinfo_envvar("metadata")
            ud = guestinfo_envvar("userdata")
            vd = guestinfo_envvar("vendordata")

        return (md, ud, vd)

    def get_guestinfo_data_fn(self):
        """
        check to see if there is data via the guestinfo transport
        """

        vmtoolsd = which("vmtoolsd")
        vmware_rpctool = which("vmware-rpctool")

        # Default to using vmware-rpctool if it is available.
        if vmware_rpctool:
            self.rpctool = vmware_rpctool
            self.rpctool_fn = exec_vmware_rpctool
            LOG.debug("discovered vmware-rpctool: %s", vmware_rpctool)

        if vmtoolsd:
            # Default to using vmtoolsd if it is available and vmware-rpctool
            # is not.
            if not vmware_rpctool:
                self.rpctool = vmtoolsd
                self.rpctool_fn = exec_vmtoolsd
            LOG.debug("discovered vmtoolsd: %s", vmtoolsd)

        # If neither vmware-rpctool nor vmtoolsd are available, then nothing
        # can be done.
        if not self.rpctool:
            LOG.debug("no rpctool discovered")
            return (None, None, None)

        def query_guestinfo(rpctool, rpctool_fn):
            md, ud, vd = None, None, None
            LOG.info("query guestinfo with %s", rpctool)
            md = guestinfo("metadata", rpctool, rpctool_fn)
            ud = guestinfo("userdata", rpctool, rpctool_fn)
            vd = guestinfo("vendordata", rpctool, rpctool_fn)
            return md, ud, vd

        try:
            # The first attempt to query guestinfo could occur via either
            # vmware-rpctool *or* vmtoolsd.
            return query_guestinfo(self.rpctool, self.rpctool_fn)
        except Exception as error:
            util.logexc(
                LOG,
                "Failed to query guestinfo with %s: %s",
                self.rpctool,
                error,
            )

            # The second attempt to query guestinfo can only occur with
            # vmtoolsd.

            # If the first attempt at getting the data was with vmtoolsd, then
            # no second attempt is made.
            if vmtoolsd and self.rpctool == vmtoolsd:
                return (None, None, None)

            if not vmtoolsd:
                LOG.info("vmtoolsd fallback option not present")
                return (None, None, None)

            LOG.info("fallback to vmtoolsd")
            self.rpctool = vmtoolsd
            self.rpctool_fn = exec_vmtoolsd

            try:
                return query_guestinfo(self.rpctool, self.rpctool_fn)
            except Exception:
                util.logexc(
                    LOG,
                    "Failed to query guestinfo with %s: %s",
                    self.rpctool,
                    error,
                )

                return (None, None, None)

    def get_imc_data_fn(self):
        """
        check to see if there is data via vmware guest customization
        """
        md, ud, vd = None, None, None

        # Check if vmware guest customization is enabled.
        allow_vmware_cust = guestcust_util.is_vmware_cust_enabled(self.sys_cfg)
        allow_raw_data_cust = guestcust_util.is_raw_data_cust_enabled(
            self.ds_cfg
        )
        if not allow_vmware_cust and not allow_raw_data_cust:
            LOG.debug("Customization for VMware platform is disabled")
            return (md, ud, vd)

        # Check if "VMware Tools" plugin is available.
        if not guestcust_util.is_cust_plugin_available():
            return (md, ud, vd)

        # Wait for vmware guest customization configuration file.
        cust_cfg_file = guestcust_util.get_cust_cfg_file(self.ds_cfg)
        if cust_cfg_file is None:
            return (md, ud, vd)

        # Check what type of guest customization is this.
        cust_cfg_dir = os.path.dirname(cust_cfg_file)
        cust_cfg = guestcust_util.parse_cust_cfg(cust_cfg_file)
        (
            is_vmware_cust_cfg,
            is_raw_data_cust_cfg,
        ) = guestcust_util.get_cust_cfg_type(cust_cfg)

        # Get data only if guest customization type and flag matches.
        if is_vmware_cust_cfg and allow_vmware_cust:
            LOG.debug("Getting data via VMware customization configuration")
            (md, ud, vd, self.cfg) = guestcust_util.get_data_from_imc_cust_cfg(
                self.paths.cloud_dir,
                self.paths.get_cpath("scripts"),
                cust_cfg,
                cust_cfg_dir,
                self.distro,
            )
        elif is_raw_data_cust_cfg and allow_raw_data_cust:
            LOG.debug(
                "Getting data via VMware raw cloudinit data "
                "customization configuration"
            )
            (md, ud, vd) = guestcust_util.get_data_from_imc_raw_data_cust_cfg(
                cust_cfg
            )
        else:
            LOG.debug("No allowed customization configuration data found")

        # Clean customization configuration file and directory
        util.del_dir(cust_cfg_dir)
        return (md, ud, vd)


def is_vmware_platform():
    system_type = dmi.read_dmi_data("system-product-name")
    if system_type is None:
        LOG.debug("No system-product-name found")
        return False
    elif "vmware" not in system_type.lower():
        LOG.debug("Not a VMware platform")
        return False
    return True


def decode(key, enc_type, data):
    """
    decode returns the decoded string value of data
    key is a string used to identify the data being decoded in log messages
    """
    LOG.debug("Getting encoded data for key=%s, enc=%s", key, enc_type)

    raw_data = None
    if enc_type in ["gzip+base64", "gz+b64"]:
        LOG.debug("Decoding %s format %s", enc_type, key)
        raw_data = util.decomp_gzip(atomic_helper.b64d(data))
    elif enc_type in ["base64", "b64"]:
        LOG.debug("Decoding %s format %s", enc_type, key)
        raw_data = atomic_helper.b64d(data)
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


def advertise_local_ip_addrs(host_info, rpctool, rpctool_fn):
    """
    advertise_local_ip_addrs gets the local IP address information from
    the provided host_info map and sets the addresses in the guestinfo
    namespace
    """
    if not host_info or not rpctool or not rpctool_fn:
        return

    # Reflect any possible local IPv4 or IPv6 addresses in the guest
    # info.
    local_ipv4 = host_info.get(LOCAL_IPV4)
    if local_ipv4:
        guestinfo_set_value(LOCAL_IPV4, local_ipv4, rpctool, rpctool_fn)
        LOG.info("advertised local ipv4 address %s in guestinfo", local_ipv4)

    local_ipv6 = host_info.get(LOCAL_IPV6)
    if local_ipv6:
        guestinfo_set_value(LOCAL_IPV6, local_ipv6, rpctool, rpctool_fn)
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


def get_imc_key_name(key):
    return "vmware-tools"


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


def exec_vmware_rpctool(rpctool, arg):
    (stdout, stderr) = subp([rpctool, arg])
    return (stdout, stderr)


def exec_vmtoolsd(rpctool, arg):
    (stdout, stderr) = subp([rpctool, "--cmd", arg])
    return (stdout, stderr)


def guestinfo(key, rpctool, rpctool_fn):
    """
    guestinfo returns the guestinfo value for the provided key, decoding
    the value when required
    """
    val = guestinfo_get_value(key, rpctool, rpctool_fn)
    if not val:
        return None
    enc_type = guestinfo_get_value(key + ".encoding", rpctool, rpctool_fn)
    return decode(get_guestinfo_key_name(key), enc_type, val)


def guestinfo_get_value(key, rpctool, rpctool_fn):
    """
    Returns a guestinfo value for the specified key.
    """
    LOG.debug("Getting guestinfo value for key %s", key)

    try:
        (stdout, stderr) = rpctool_fn(
            rpctool, "info-get " + get_guestinfo_key_name(key)
        )
        if stderr == NOVAL:
            LOG.debug("No value found for key %s", key)
        elif not stdout:
            LOG.error("Failed to get guestinfo value for key %s", key)
        return handle_returned_guestinfo_val(key, stdout)
    except ProcessExecutionError as error:
        # No matter the tool used to access the data, if NOVAL was returned on
        # stderr, do not raise an exception.
        if error.stderr == NOVAL:
            LOG.debug("No value found for key %s", key)
        else:
            # Any other result gets logged as an error, and if the tool was
            # vmware-rpctool, then raise the exception so the caller can try
            # again with vmtoolsd.
            util.logexc(
                LOG,
                "Failed to get guestinfo value for key %s: %s",
                key,
                error,
            )
            raise error
    except Exception as error:
        util.logexc(
            LOG,
            "Unexpected error while trying to get "
            "guestinfo value for key %s: %s",
            key,
            error,
        )
        raise error

    return None


def guestinfo_set_value(key, value, rpctool, rpctool_fn):
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
        rpctool_fn(
            rpctool, "info-set %s %s" % (get_guestinfo_key_name(key), value)
        )
        return True
    except ProcessExecutionError as error:
        # Any error result gets logged as an error, and if the tool was
        # vmware-rpctool, then raise the exception so the caller can try
        # again with vmtoolsd.
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
            "guestinfo key=%s to value=%s",
            key,
            value,
        )

    return None


def guestinfo_redact_keys(keys, rpctool, rpctool_fn):
    """
    guestinfo_redact_keys redacts guestinfo of all of the keys in the given
    list. each key will have its value set to "---". Since the value is valid
    YAML, cloud-init can still read it if it tries.
    """
    if not keys:
        return
    if type(keys) not in (list, tuple):
        keys = [keys]
    for key in keys:
        key_name = get_guestinfo_key_name(key)
        LOG.info("clearing %s", key_name)
        if not guestinfo_set_value(
            key, GUESTINFO_EMPTY_YAML_VAL, rpctool, rpctool_fn
        ):
            LOG.error("failed to clear %s", key_name)
        LOG.info("clearing %s.encoding", key_name)
        if not guestinfo_set_value(key + ".encoding", "", rpctool, rpctool_fn):
            LOG.error("failed to clear %s.encoding", key_name)


def load_json_or_yaml(data):
    """
    load first attempts to unmarshal the provided data as JSON, and if
    that fails then attempts to unmarshal the data as YAML. If data is
    None then a new dictionary is returned.
    """
    if not data:
        return {}
    # If data is already a dictionary, here will return it directly.
    if isinstance(data, dict):
        return data
    try:
        return util.load_json(data)
    except (json.JSONDecodeError, TypeError):
        return util.load_yaml(data)


def process_metadata(data):
    """
    process_metadata processes metadata and loads the optional network
    configuration.
    """
    if not data:
        return {}
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

    # Get ipv4 and ipv6 interfaces associated with default routes
    ipv4_if = None
    ipv6_if = None
    routes = netinfo.route_info()
    for route in routes["ipv4"]:
        if route["destination"] == "0.0.0.0":
            ipv4_if = route["iface"]
            break
    for route in routes["ipv6"]:
        if route["destination"] == "::/0":
            ipv6_if = route["iface"]
            break

    # Get ip address associated with default interface
    ipv4 = None
    ipv6 = None
    netdev = netinfo.netdev_info()
    if ipv4_if in netdev:
        addrs = netdev[ipv4_if]["ipv4"]
        if len(addrs) > 1:
            LOG.debug(
                "device %s has more than one ipv4 address: %s", ipv4_if, addrs
            )
        elif len(addrs) == 1 and "ip" in addrs[0]:
            ipv4 = addrs[0]["ip"]
    if ipv6_if in netdev:
        addrs = netdev[ipv6_if]["ipv6"]
        if len(addrs) > 1:
            LOG.debug(
                "device %s has more than one ipv6 address: %s", ipv6_if, addrs
            )
        elif len(addrs) == 1 and "ip" in addrs[0]:
            ipv6 = addrs[0]["ip"]

    # If there is a default IPv4 address but not IPv6, then see if there is a
    # single IPv6 address associated with the same device associated with the
    # default IPv4 address.
    if ipv4 is not None and ipv6 is None:
        for dev_name in netdev:
            for addr in netdev[dev_name]["ipv4"]:
                if addr["ip"] == ipv4 and len(netdev[dev_name]["ipv6"]) == 1:
                    ipv6 = netdev[dev_name]["ipv6"][0]["ip"]
                    break

    # If there is a default IPv6 address but not IPv4, then see if there is a
    # single IPv4 address associated with the same device associated with the
    # default IPv6 address.
    if ipv4 is None and ipv6 is not None:
        for dev_name in netdev:
            for addr in netdev[dev_name]["ipv6"]:
                if addr["ip"] == ipv6 and len(netdev[dev_name]["ipv4"]) == 1:
                    ipv4 = netdev[dev_name]["ipv4"][0]["ip"]
                    break

    return ipv4, ipv6


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


def convert_to_netifaces_ipv4_format(addr: dict) -> dict:
    """
    Takes a cloudinit.netinfo formatted address and converts to netifaces
    format, since this module was originally written with netifaces as the
    network introspection module.
    netifaces ipv4 format:
    {
      "broadcast": "10.15.255.255",
      "netmask": "255.240.0.0",
      "addr": "10.0.1.4"
    }
    cloudinit.netinfo ipv4 format:
    {
      "ip": "10.0.1.4",
      "mask": "255.240.0.0",
      "bcast": "10.15.255.255",
      "scope": "global",
    }
    """
    if not addr.get("ip"):
        return {}
    return {
        "broadcast": addr.get("bcast"),
        "netmask": addr.get("mask"),
        "addr": addr.get("ip"),
    }


def convert_to_netifaces_ipv6_format(addr: dict) -> dict:
    """
    Takes a cloudinit.netinfo formatted address and converts to netifaces
    format, since this module was originally written with netifaces as the
    network introspection module.
    netifaces ipv6 format:
    {
      "netmask": "ffff:ffff:ffff:ffff::/64",
      "addr": "2001:db8:abcd:1234::1"
    }
    cloudinit.netinfo ipv6 format:
    {
      "ip": "2001:db8:abcd:1234::1/64",
      "scope6": "global",
    }
    """
    if not addr.get("ip"):
        return {}
    ipv6 = ipaddress.IPv6Interface(addr.get("ip"))
    return {
        "netmask": f"{ipv6.netmask}/{ipv6.network.prefixlen}",
        "addr": str(ipv6.ip),
    }


def get_host_info():
    """
    Returns host information such as the host name and network interfaces.
    """
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

    ifaces = netinfo.netdev_info()
    for dev_name in ifaces:
        af_inet4 = []
        af_inet6 = []
        for addr in ifaces[dev_name]["ipv4"]:
            af_inet4.append(convert_to_netifaces_ipv4_format(addr))
        for addr in ifaces[dev_name]["ipv6"]:
            af_inet6.append(convert_to_netifaces_ipv6_format(addr))

        mac = ifaces[dev_name].get("hwaddr")

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
        log.setup_basic_logging()
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
    print(atomic_helper.json_dumps(metadata))


if __name__ == "__main__":
    main()
