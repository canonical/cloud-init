# Cloud-Init DataSource for VMware
#
# Copyright (c) 2018-2022 VMware, Inc. All Rights Reserved.
#
# Authors: Anish Swaminathan <anishs@vmware.com>
#          Andrew Kutz <akutz@vmware.com>
#          Pengpeng Sun <pengpengs@vmware.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Cloud-Init DataSource for VMware

This module provides a cloud-init datasource for VMware systems and supports
multiple transports types, including:

    * VMware-imc (VMware Guest Customization)
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
from cloudinit import net, safeyaml, sources, util
from cloudinit.sources.helpers.vmware.imc.config import Config
from cloudinit.sources.helpers.vmware.imc.config_custom_script import (
    CustomScriptNotFound,
    PostCustomScript,
    PreCustomScript,
)
from cloudinit.sources.helpers.vmware.imc.config_file import ConfigFile
from cloudinit.sources.helpers.vmware.imc.config_nic import NicConfigurator
from cloudinit.sources.helpers.vmware.imc.config_passwd import (
    PasswordConfigurator,
)
from cloudinit.sources.helpers.vmware.imc.guestcust_error import (
    GuestCustErrorEnum,
)
from cloudinit.sources.helpers.vmware.imc.guestcust_event import (
    GuestCustEventEnum as GuestCustEvent,
)
from cloudinit.sources.helpers.vmware.imc.guestcust_state import (
    GuestCustStateEnum,
)
from cloudinit.sources.helpers.vmware.imc.guestcust_util import (
    enable_nics,
    get_nics_to_enable,
    get_tools_config,
    set_customization_status,
    set_gc_status,
)
from cloudinit.subp import ProcessExecutionError, subp, which

PRODUCT_UUID_FILE_PATH = "/sys/class/dmi/id/product_uuid"

LOG = logging.getLogger(__name__)
NOVAL = "No value found"

# Data transports names
DATA_ACCESS_METHOD_VMWARE_IMC = "vmware-imc"
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

GUEST_CUSTOMIZATION_CONF_GROUPNAME = "deployPkg"
GUEST_CUSTOMIZATION_ENABLE_CUST_SCRIPTS = "enable-custom-scripts"


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

        vmware-imc transport:
        Either Network Config Version 1 or Network Config Version 2 is
        supported which depends on the customization type.
        For LinuxPrep customization, Network config Version 1 data is
        parsed from the customization specification.
        For CloudinitPrep customization, Network config Version 2 data
        is parsed from the customization specification.

        envvar and guestinfo tranports:
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
        self.vmware_rpctool = VMWARE_RPCTOOL

        # A list includes all possible data transports, each tuple represents
        # one data transport type. This datasource will try to get data from
        # each of transports follows the tuples order in this list.
        # A tuple has 3 elements which are:
        # 1. The transport name
        # 2. The function name to get data for the transport
        # 3. A boolean tells whether the transport requires VMware platform
        self.possible_data_access_method_list = [
            (DATA_ACCESS_METHOD_VMWARE_IMC, self.get_vmware_imc_data_fn, True),
            (DATA_ACCESS_METHOD_ENVVAR, self.get_envvar_data_fn, False),
            (DATA_ACCESS_METHOD_GUESTINFO, self.get_guestinfo_data_fn, True),
        ]

    def __str__(self):
        root = sources.DataSource.__str__(self)
        return "%s [seed=%s]" % (root, self.data_access_method)

    def _get_data(self):
        """
        _get_data loads the metadata, userdata, and vendordata from one of
        the following locations in the given order:

            * vmware-imc
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
            LOG.error("failed to find a valid data access method")
            return False

        LOG.info("using data access method %s", self._get_subplatform())

        # Get the metadata.
        self.metadata = process_metadata(md)

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
        if self.data_access_method == DATA_ACCESS_METHOD_VMWARE_IMC:
            get_key_name_fn = get_vmware_imc_key_name
        elif self.data_access_method == DATA_ACCESS_METHOD_ENVVAR:
            get_key_name_fn = get_guestinfo_envvar_key_name
        elif self.data_access_method == DATA_ACCESS_METHOD_GUESTINFO:
            get_key_name_fn = get_guestinfo_key_name
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

    def get_envvar_data_fn(self):
        """
        check to see if there is data via env vars
        """
        md, ud, vd = None, None, None
        if os.environ.get(VMX_GUESTINFO, ""):
            md_in_json_or_yaml = guestinfo_envvar("metadata")
            ud = guestinfo_envvar("userdata")
            vd = guestinfo_envvar("vendordata")

            if md_in_json_or_yaml:
                md = load_json_or_yaml(md_in_json_or_yaml)
        return (md, ud, vd)

    def get_guestinfo_data_fn(self):
        """
        check to see if there is data via the guestinfo transport
        """
        md, ud, vd = None, None, None
        if self.vmware_rpctool:
            md_in_json_or_yaml = guestinfo("metadata", self.vmware_rpctool)
            ud = guestinfo("userdata", self.vmware_rpctool)
            vd = guestinfo("vendordata", self.vmware_rpctool)

            if md_in_json_or_yaml:
                md = load_json_or_yaml(md_in_json_or_yaml)
        return (md, ud, vd)

    def get_vmware_imc_data_fn(self):
        """
        check to see if there is data via vmware guest customization
        """
        md, ud, vd = None, None, None

        # Check if vmware guest customization is enabled.
        allow_vmware_cust = self.is_vmware_cust_enabled()
        allow_raw_data_cust = self.is_raw_data_cust_enabled()
        if not allow_vmware_cust and not allow_raw_data_cust:
            LOG.debug("Customization for VMware platform is disabled")
            return (md, ud, vd)

        # Check if "VMware Tools" plugin is available.
        if not is_cust_plugin_available():
            return (md, ud, vd)

        # Wait for vmware guest customization configuration file.
        cust_cfg_file = self.get_cust_cfg_file()
        if cust_cfg_file is None:
            return (md, ud, vd)

        # Check what type of guest customization is this.
        cust_cfg_dir = os.path.dirname(cust_cfg_file)
        cust_cfg = parse_cust_cfg(cust_cfg_file)
        (is_vmware_cust_cfg, is_raw_data_cust_cfg) = get_cust_cfg_type(
            cust_cfg
        )

        # Get data only if guest customization type and flag matches.
        if is_vmware_cust_cfg and allow_vmware_cust:
            LOG.debug("Getting data via VMware customization configuration")
            (md, ud, vd) = self.get_data_from_vmware_cust_cfg(
                cust_cfg, cust_cfg_dir
            )
        elif is_raw_data_cust_cfg and allow_raw_data_cust:
            LOG.debug(
                "Getting data via VMware raw cloudinit data "
                "customization configuration"
            )
            (md, ud, vd) = self.get_data_from_raw_data_cust_cfg(cust_cfg)
        else:
            LOG.debug("No allowed customization configuration data found")

        # Clean customization configuration file and directory
        util.del_dir(cust_cfg_dir)
        return (md, ud, vd)

    def is_vmware_cust_enabled(self):
        return not util.get_cfg_option_bool(
            self.sys_cfg, "disable_vmware_customization", True
        )

    def is_raw_data_cust_enabled(self):
        return util.get_cfg_option_bool(self.ds_cfg, "allow_raw_data", True)

    def get_cust_cfg_file(self):
        # When the VM is powered on, the "VMware Tools" daemon
        # copies the customization specification file to
        # /var/run/vmware-imc directory. cloud-init code needs
        # to search for the file in that directory which indicates
        # that required metadata and userdata files are now
        # present.
        max_wait = get_max_wait_from_cfg(self.ds_cfg)
        cust_cfg_file_path = util.log_time(
            logfunc=LOG.debug,
            msg="Waiting for VMware customization configuration file",
            func=wait_for_cust_cfg_file,
            args=("cust.cfg", max_wait),
        )
        if cust_cfg_file_path:
            LOG.debug(
                "Found VMware customization configuration file at %s",
                cust_cfg_file_path,
            )
            return cust_cfg_file_path
        else:
            LOG.debug("No VMware customization configuration file found")
        return None

    def get_data_from_vmware_cust_cfg(self, cust_cfg, cust_cfg_dir):
        md = {}
        ud, vd = None, None

        set_gc_status(cust_cfg, "Started")
        (md, self.cfg) = get_non_network_data_from_vmware_cust_cfg(cust_cfg)

        is_special_customization = self.check_markers(cust_cfg)
        if is_special_customization:
            if not self.do_special_customization(cust_cfg, cust_cfg_dir):
                return (None, None, None)
        if not self.recheck_markers(cust_cfg):
            return (None, None, None)

        try:
            LOG.debug("Preparing the Network configuration")
            md["network"] = get_network_data_from_vmware_cust_cfg(
                cust_cfg, True, True, self.distro.osfamily
            )
        except Exception as e:
            set_cust_error_status(
                "Error preparing Network Configuration",
                str(e),
                GuestCustEvent.GUESTCUST_EVENT_NETWORK_SETUP_FAILED,
                cust_cfg,
            )
            return (None, None, None)

        connect_nics(cust_cfg_dir)
        set_customization_status(
            GuestCustStateEnum.GUESTCUST_STATE_DONE,
            GuestCustErrorEnum.GUESTCUST_ERROR_SUCCESS,
        )
        set_gc_status(cust_cfg, "Successful")
        return (md, ud, vd)

    def get_data_from_raw_data_cust_cfg(self, cust_cfg):
        set_gc_status(cust_cfg, "Started")
        md, ud, vd = None, None, None
        md_file = cust_cfg.meta_data_name
        if md_file:
            md_path = os.path.join(get_vmware_imc_dir(), md_file)
            if not os.path.exists(md_path):
                set_cust_error_status(
                    "Error locating the cloud-init meta data file",
                    "Meta data file is not found: %s" % md_path,
                    GuestCustEvent.GUESTCUST_EVENT_CUSTOMIZE_FAILED,
                    cust_cfg,
                )
                return (None, None, None)
            try:
                md = safeload_yaml_or_dict(util.load_file(md_path))
            except safeyaml.YAMLError as e:
                set_cust_error_status(
                    "Error parsing the cloud-init meta data",
                    str(e),
                    GuestCustErrorEnum.GUESTCUST_ERROR_WRONG_META_FORMAT,
                    cust_cfg,
                )
                return (None, None, None)
            except Exception as e:
                set_cust_error_status(
                    "Error loading cloud-init customization configuration",
                    str(e),
                    GuestCustEvent.GUESTCUST_EVENT_CUSTOMIZE_FAILED,
                    cust_cfg,
                )
                return (None, None, None)

            ud_file = cust_cfg.user_data_name
            if ud_file:
                ud_path = os.path.join(get_vmware_imc_dir(), ud_file)
                if not os.path.exists(ud_path):
                    set_cust_error_status(
                        "Error locating the cloud-init userdata file",
                        "Userdata file is not found: %s" % ud_path,
                        GuestCustEvent.GUESTCUST_EVENT_CUSTOMIZE_FAILED,
                        cust_cfg,
                    )
                    return (None, None, None)
                ud = util.load_file(ud_path).replace("\r", "")

        set_customization_status(
            GuestCustStateEnum.GUESTCUST_STATE_DONE,
            GuestCustErrorEnum.GUESTCUST_ERROR_SUCCESS,
        )
        set_gc_status(cust_cfg, "Successful")
        return (md, ud, vd)

    def check_markers(self, cust_cfg):
        product_marker = cust_cfg.marker_id
        has_marker_file = check_marker_exists(
            product_marker, os.path.join(self.paths.cloud_dir, "data")
        )
        return product_marker and not has_marker_file

    def do_special_customization(self, cust_cfg, cust_cfg_dir):
        is_pre_custom_successful = False
        is_password_custom_successful = False
        is_post_custom_successful = False
        is_custom_script_enabled = False
        custom_script = cust_cfg.custom_script_name
        if custom_script:
            is_custom_script_enabled = check_custom_script_enablement(cust_cfg)
            if is_custom_script_enabled:
                is_pre_custom_successful = do_pre_custom_script(
                    cust_cfg, custom_script, cust_cfg_dir
                )
        is_password_custom_successful = do_password_customization(
            cust_cfg, self.distro
        )
        if custom_script and is_custom_script_enabled:
            ccScriptsDir = os.path.join(
                self.paths.get_cpath("scripts"), "per-instance"
            )
            is_post_custom_successful = do_post_custom_script(
                cust_cfg, custom_script, cust_cfg_dir, ccScriptsDir
            )
        if custom_script:
            return (
                is_pre_custom_successful
                and is_password_custom_successful
                and is_post_custom_successful
            )
        return is_password_custom_successful

    def recheck_markers(self, cust_cfg):
        product_marker = cust_cfg.marker_id
        if product_marker:
            cloud_dir = self.paths.cloud_dir
            if not create_marker_file(cust_cfg, cloud_dir):
                return False
        return True


def is_vmware_platform():
    system_type = dmi.read_dmi_data("system-product-name")
    if system_type is None:
        LOG.debug("No system-product-name found")
        return False
    elif "vmware" not in system_type.lower():
        LOG.debug("Not a VMware platform")
        return False
    return True


def get_vmware_imc_dir():
    return "/var/run/vmware-imc"


def get_non_network_data_from_vmware_cust_cfg(cust_cfg):
    md = {}
    cfg = {}
    if cust_cfg.host_name:
        if cust_cfg.domain_name:
            md["local-hostname"] = (
                cust_cfg.host_name + "." + cust_cfg.domain_name
            )
        else:
            md["local-hostname"] = cust_cfg.host_name
    if cust_cfg.timezone:
        cfg["timezone"] = cust_cfg.timezone
    if cust_cfg.instance_id:
        md["instance-id"] = cust_cfg.instance_id
    return (md, cfg)


def do_pre_custom_script(cust_cfg, custom_script, cust_cfg_dir):
    try:
        precust = PreCustomScript(custom_script, cust_cfg_dir)
        precust.execute()
    except CustomScriptNotFound as e:
        set_cust_error_status(
            "Error executing pre-customization script",
            str(e),
            GuestCustEvent.GUESTCUST_EVENT_CUSTOMIZE_FAILED,
            cust_cfg,
        )
        return False
    return True


def do_post_custom_script(cust_cfg, custom_script, cust_cfg_dir, ccScriptsDir):
    try:
        postcust = PostCustomScript(custom_script, cust_cfg_dir, ccScriptsDir)
        postcust.execute()
    except CustomScriptNotFound as e:
        set_cust_error_status(
            "Error executing post-customization script",
            str(e),
            GuestCustEvent.GUESTCUST_EVENT_CUSTOMIZE_FAILED,
            cust_cfg,
        )
        return False
    return True


def do_password_customization(cust_cfg, distro):
    LOG.debug("Applying password customization")
    pwdConfigurator = PasswordConfigurator()
    admin_pwd = cust_cfg.admin_password
    try:
        reset_pwd = cust_cfg.reset_password
        if admin_pwd or reset_pwd:
            pwdConfigurator.configure(admin_pwd, reset_pwd, distro)
        else:
            LOG.debug("Changing password is not needed")
    except Exception as e:
        set_cust_error_status(
            "Error applying password configuration",
            str(e),
            GuestCustEvent.GUESTCUST_EVENT_CUSTOMIZE_FAILED,
            cust_cfg,
        )
        return False
    return True


def create_marker_file(cust_cfg, cloud_dir):
    try:
        setup_marker_files(cust_cfg.marker_id, os.path.join(cloud_dir, "data"))
    except Exception as e:
        set_cust_error_status(
            "Error creating marker files",
            str(e),
            GuestCustEvent.GUESTCUST_EVENT_CUSTOMIZE_FAILED,
            cust_cfg,
        )
        return False
    return True


def setup_marker_files(marker_id, marker_dir):
    """
    Create a new marker file.
    Marker files are unique to a full customization workflow in VMware
    environment.
    @param marker_id: is an unique string representing a particular product
                      marker.
    @param: marker_dir: The directory in which markers exist.
    """
    LOG.debug("Handle marker creation")
    marker_file = os.path.join(marker_dir, ".markerfile-" + marker_id + ".txt")
    for fname in os.listdir(marker_dir):
        if fname.startswith(".markerfile"):
            util.del_file(os.path.join(marker_dir, fname))
    open(marker_file, "w").close()


def check_custom_script_enablement(cust_cfg):
    is_custom_script_enabled = False
    default_value = "false"
    if cust_cfg.default_run_post_script:
        LOG.debug(
            "Set default value to true due to customization " "configuration."
        )
        default_value = "true"
    custom_script_enablement = get_tools_config(
        GUEST_CUSTOMIZATION_CONF_GROUPNAME,
        GUEST_CUSTOMIZATION_ENABLE_CUST_SCRIPTS,
        default_value,
    )
    if custom_script_enablement.lower() != "true":
        set_cust_error_status(
            "Custom script is disabled by VM Administrator",
            "Error checking custom script enablement",
            GuestCustErrorEnum.GUESTCUST_ERROR_SCRIPT_DISABLED,
            cust_cfg,
        )
    else:
        is_custom_script_enabled = True
    return is_custom_script_enabled


def check_marker_exists(markerid, marker_dir):
    """
    Check the existence of a marker file.
    Presence of marker file determines whether a certain code path is to be
    executed. It is needed for partial guest customization in VMware.
    @param markerid: is an unique string representing a particular product
                     marker.
    @param: marker_dir: The directory in which markers exist.
    """
    if not markerid:
        return False
    markerfile = os.path.join(marker_dir, ".markerfile-" + markerid + ".txt")
    if os.path.exists(markerfile):
        return True
    return False


def get_network_data_from_vmware_cust_cfg(
    cust_cfg, use_system_devices=True, configure=False, osfamily=None
):
    nicConfigurator = NicConfigurator(cust_cfg.nics, use_system_devices)
    nics_cfg_list = nicConfigurator.generate(configure, osfamily)

    return get_v1_network_config(
        nics_cfg_list, cust_cfg.name_servers, cust_cfg.dns_suffixes
    )


def get_v1_network_config(nics_cfg_list=None, nameservers=None, search=None):
    config_list = nics_cfg_list

    if nameservers or search:
        config_list.append(
            {"type": "nameserver", "address": nameservers, "search": search}
        )

    return {"version": 1, "config": config_list}


def set_cust_error_status(prefix, error, event, cust_cfg):
    """
    Set customization status to the underlying VMware Virtualization Platform
    """
    util.logexc(LOG, "%s: %s", prefix, error)
    set_customization_status(GuestCustStateEnum.GUESTCUST_STATE_RUNNING, event)
    set_gc_status(cust_cfg, prefix)


def parse_cust_cfg(cfg_file):
    return Config(ConfigFile(cfg_file))


def get_cust_cfg_type(cust_cfg):
    is_vmware_cust_cfg, is_raw_data_cust_cfg = False, False
    if cust_cfg.meta_data_name:
        is_raw_data_cust_cfg = True
        LOG.debug("raw cloudinit data cust cfg found")
    else:
        is_vmware_cust_cfg = True
        LOG.debug("vmware cust cfg found")
    return (is_vmware_cust_cfg, is_raw_data_cust_cfg)


def get_max_wait_from_cfg(ds_cfg):
    default_max_wait = 15
    max_wait_cfg_option = "vmware_cust_file_max_wait"
    max_wait = default_max_wait

    if not ds_cfg:
        return max_wait

    try:
        max_wait = int(ds_cfg.get(max_wait_cfg_option, default_max_wait))
    except ValueError:
        LOG.warning(
            "Failed to get '%s', using %s",
            max_wait_cfg_option,
            default_max_wait,
        )

    if max_wait < 0:
        LOG.warning(
            "Invalid value '%s' for '%s', using '%s' instead",
            max_wait,
            max_wait_cfg_option,
            default_max_wait,
        )
        max_wait = default_max_wait

    return max_wait


def wait_for_cust_cfg_file(
    filename, maxwait=180, naplen=5, dirpath="/var/run/vmware-imc"
):
    waited = 0
    if maxwait <= naplen:
        naplen = 1

    while waited < maxwait:
        fileFullPath = os.path.join(dirpath, filename)
        if os.path.isfile(fileFullPath):
            return fileFullPath
        LOG.debug("Waiting for VMware customization configuration file")
        time.sleep(naplen)
        waited += naplen
    return None


def is_cust_plugin_available():
    search_paths = (
        "/usr/lib/vmware-tools",
        "/usr/lib64/vmware-tools",
        "/usr/lib/open-vm-tools",
        "/usr/lib64/open-vm-tools",
        "/usr/lib/x86_64-linux-gnu/open-vm-tools",
        "/usr/lib/aarch64-linux-gnu/open-vm-tools",
    )
    cust_plugin = "libdeployPkgPlugin.so"
    for path in search_paths:
        cust_plugin_path = search_file(path, cust_plugin)
        if cust_plugin_path:
            LOG.debug("Found the customization plugin at %s", cust_plugin_path)
            return True
    return False


def search_file(dirpath, filename):
    if not dirpath or not filename:
        return None

    for root, _dirs, files in os.walk(dirpath):
        if filename in files:
            return os.path.join(root, filename)

    return None


def connect_nics(cust_cfg_dir):
    nics_file = os.path.join(cust_cfg_dir, "nics.txt")
    if os.path.exists(nics_file):
        LOG.debug("%s file found, to connect nics", nics_file)
        enable_nics(get_nics_to_enable(nics_file))


def safeload_yaml_or_dict(data):
    """
    The meta data could be JSON or YAML. Since YAML is a strict superset of
    JSON, we will unmarshal the data as YAML. If data is None then a new
    dictionary is returned.
    """
    if not data:
        return {}
    return safeyaml.load(data)


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


def get_vmware_imc_key_name(key):
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
    host_info = None
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
        "wait-on-network": {"ipv4": True, "ipv6": "false"},
        "network": {"config": {"dhcp": True}},
    }
    host_info = wait_on_network(metadata)
    metadata = util.mergemanydict([metadata, host_info])
    print(util.json_dumps(metadata))


if __name__ == "__main__":
    main()

# vi: ts=4 expandtab
