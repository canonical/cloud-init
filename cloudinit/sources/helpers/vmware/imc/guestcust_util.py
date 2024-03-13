# Copyright (C) 2016 Canonical Ltd.
# Copyright (C) 2016-2023 VMware Inc.
#
# Author: Sankar Tanguturi <stanguturi@vmware.com>
#         Pengpeng Sun <pegnpengs@vmware.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import logging
import os
import re
import time

from cloudinit import safeyaml, subp, util

from .config import Config
from .config_custom_script import PostCustomScript, PreCustomScript
from .config_file import ConfigFile
from .config_nic import NicConfigurator
from .config_passwd import PasswordConfigurator
from .guestcust_error import GuestCustErrorEnum
from .guestcust_event import GuestCustEventEnum
from .guestcust_state import GuestCustStateEnum

logger = logging.getLogger(__name__)


CLOUDINIT_LOG_FILE = "/var/log/cloud-init.log"
QUERY_NICS_SUPPORTED = "queryNicsSupported"
NICS_STATUS_CONNECTED = "connected"
# Path to the VMware IMC directory
IMC_DIR_PATH = "/var/run/vmware-imc"
# Customization script configuration in tools conf
IMC_TOOLS_CONF_GROUPNAME = "deployPkg"
IMC_TOOLS_CONF_ENABLE_CUST_SCRIPTS = "enable-custom-scripts"


# This will send a RPC command to the underlying
# VMware Virtualization Platform.
def send_rpc(rpc):
    if not rpc:
        return None

    out = ""
    err = "Error sending the RPC command"

    try:
        logger.debug("Sending RPC command: %s", rpc)
        (out, err) = subp.subp(["vmware-rpctool", rpc], rcs=[0])
        # Remove the trailing newline in the output.
        if out:
            out = out.rstrip()
    except Exception as e:
        logger.debug("Failed to send RPC command")
        logger.exception(e)

    return (out, err)


# This will send the customization status to the
# underlying VMware Virtualization Platform.
def set_customization_status(custstate, custerror, errormessage=None):
    message = ""

    if errormessage:
        message = CLOUDINIT_LOG_FILE + "@" + errormessage
    else:
        message = CLOUDINIT_LOG_FILE

    rpc = "deployPkg.update.state %d %d %s" % (custstate, custerror, message)
    (out, err) = send_rpc(rpc)
    return (out, err)


def get_nics_to_enable(nicsfilepath):
    """Reads the NICS from the specified file path and returns the content

    @param nicsfilepath: Absolute file path to the NICS.txt file.
    """

    if not nicsfilepath:
        return None

    NICS_SIZE = 1024
    if not os.path.exists(nicsfilepath):
        return None

    with open(nicsfilepath, "r") as fp:
        nics = fp.read(NICS_SIZE)

    return nics


# This will send a RPC command to the underlying VMware Virtualization platform
# and enable nics.
def enable_nics(nics):
    if not nics:
        logger.warning("No Nics found")
        return

    enableNicsWaitRetries = 5
    enableNicsWaitCount = 5
    enableNicsWaitSeconds = 1

    for attempt in range(enableNicsWaitRetries):
        logger.debug("Trying to connect interfaces, attempt %d", attempt)
        (out, _err) = set_customization_status(
            GuestCustStateEnum.GUESTCUST_STATE_RUNNING,
            GuestCustEventEnum.GUESTCUST_EVENT_ENABLE_NICS,
            nics,
        )
        if not out:
            time.sleep(enableNicsWaitCount * enableNicsWaitSeconds)
            continue

        if out != QUERY_NICS_SUPPORTED:
            logger.warning("NICS connection status query is not supported")
            return

        for count in range(enableNicsWaitCount):
            (out, _err) = set_customization_status(
                GuestCustStateEnum.GUESTCUST_STATE_RUNNING,
                GuestCustEventEnum.GUESTCUST_EVENT_QUERY_NICS,
                nics,
            )
            if out and out == NICS_STATUS_CONNECTED:
                logger.info("NICS are connected on %d second", count)
                return

            time.sleep(enableNicsWaitSeconds)

    logger.warning(
        "Can't connect network interfaces after %d attempts",
        enableNicsWaitRetries,
    )


def get_tools_config(section, key, defaultVal):
    """Return the value of [section] key from VMTools configuration.

    @param section: String of section to read from VMTools config
    @returns: String value from key in [section] or defaultVal if
              [section] is not present or vmware-toolbox-cmd is
              not installed.
    """

    if not subp.which("vmware-toolbox-cmd"):
        logger.debug(
            "vmware-toolbox-cmd not installed, returning default value"
        )
        return defaultVal

    cmd = ["vmware-toolbox-cmd", "config", "get", section, key]

    try:
        out = subp.subp(cmd)
    except subp.ProcessExecutionError as e:
        if e.exit_code == 69:
            logger.debug(
                "vmware-toolbox-cmd returned 69 (unavailable) for cmd: %s."
                " Return default value: %s",
                " ".join(cmd),
                defaultVal,
            )
        else:
            logger.error("Failed running %s[%s]", cmd, e.exit_code)
            logger.exception(e)
        return defaultVal

    retValue = defaultVal
    m = re.match(r"([^=]+)=(.*)", out.stdout)
    if m:
        retValue = m.group(2).strip()
        logger.debug("Get tools config: [%s] %s = %s", section, key, retValue)
    else:
        logger.debug(
            "Tools config: [%s] %s is not found, return default value: %s",
            section,
            key,
            retValue,
        )

    return retValue


# Sets message to the VMX guestinfo.gc.status property to the
# underlying VMware Virtualization Platform.
def set_gc_status(config, gcMsg):
    if config and config.post_gc_status:
        rpc = "info-set guestinfo.gc.status %s" % gcMsg
        return send_rpc(rpc)
    return None


def get_imc_dir_path():
    return IMC_DIR_PATH


def get_data_from_imc_cust_cfg(
    cloud_dir,
    scripts_cpath,
    cust_cfg,
    cust_cfg_dir,
    distro,
):
    md, ud, vd, cfg = {}, None, None, {}
    set_gc_status(cust_cfg, "Started")
    (md, cfg) = get_non_network_data_from_vmware_cust_cfg(cust_cfg)
    is_special_customization = check_markers(cloud_dir, cust_cfg)
    if is_special_customization:
        if not do_special_customization(
            scripts_cpath, cust_cfg, cust_cfg_dir, distro
        ):
            return (None, None, None, None)
    if not recheck_markers(cloud_dir, cust_cfg):
        return (None, None, None, None)
    try:
        logger.debug("Preparing the Network configuration")
        md["network"] = get_network_data_from_vmware_cust_cfg(
            cust_cfg, True, True, distro.osfamily
        )
    except Exception as e:
        set_cust_error_status(
            "Error preparing Network Configuration",
            str(e),
            GuestCustEventEnum.GUESTCUST_EVENT_NETWORK_SETUP_FAILED,
            cust_cfg,
        )
        return (None, None, None, None)
    connect_nics(cust_cfg_dir)
    set_customization_status(
        GuestCustStateEnum.GUESTCUST_STATE_DONE,
        GuestCustErrorEnum.GUESTCUST_ERROR_SUCCESS,
    )
    set_gc_status(cust_cfg, "Successful")
    return (md, ud, vd, cfg)


def get_data_from_imc_raw_data_cust_cfg(cust_cfg):
    set_gc_status(cust_cfg, "Started")
    md, ud, vd = None, None, None
    md_file = cust_cfg.meta_data_name
    if md_file:
        md_path = os.path.join(get_imc_dir_path(), md_file)
        if not os.path.exists(md_path):
            set_cust_error_status(
                "Error locating the cloud-init meta data file",
                "Meta data file is not found: %s" % md_path,
                GuestCustEventEnum.GUESTCUST_EVENT_CUSTOMIZE_FAILED,
                cust_cfg,
            )
            return (None, None, None)
        try:
            md = util.load_text_file(md_path)
        except Exception as e:
            set_cust_error_status(
                "Error loading cloud-init meta data file",
                str(e),
                GuestCustEventEnum.GUESTCUST_EVENT_CUSTOMIZE_FAILED,
                cust_cfg,
            )
            return (None, None, None)

        try:
            logger.debug("Validating if meta data is valid or not")
            md = safeyaml.load(md)
        except safeyaml.YAMLError as e:
            set_cust_error_status(
                "Error parsing the cloud-init meta data",
                str(e),
                GuestCustErrorEnum.GUESTCUST_ERROR_WRONG_META_FORMAT,
                cust_cfg,
            )

        ud_file = cust_cfg.user_data_name
        if ud_file:
            ud_path = os.path.join(get_imc_dir_path(), ud_file)
            if not os.path.exists(ud_path):
                set_cust_error_status(
                    "Error locating the cloud-init userdata file",
                    "Userdata file is not found: %s" % ud_path,
                    GuestCustEventEnum.GUESTCUST_EVENT_CUSTOMIZE_FAILED,
                    cust_cfg,
                )
                return (None, None, None)
            try:
                ud = util.load_text_file(ud_path).replace("\r", "")
            except Exception as e:
                set_cust_error_status(
                    "Error loading cloud-init userdata file",
                    str(e),
                    GuestCustEventEnum.GUESTCUST_EVENT_CUSTOMIZE_FAILED,
                    cust_cfg,
                )
                return (None, None, None)

    set_customization_status(
        GuestCustStateEnum.GUESTCUST_STATE_DONE,
        GuestCustErrorEnum.GUESTCUST_ERROR_SUCCESS,
    )
    set_gc_status(cust_cfg, "Successful")
    return (md, ud, vd)


def get_non_network_data_from_vmware_cust_cfg(cust_cfg):
    md, cfg = {}, {}
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


def connect_nics(cust_cfg_dir):
    nics_file = os.path.join(cust_cfg_dir, "nics.txt")
    if os.path.exists(nics_file):
        logger.debug("%s file found, to connect nics", nics_file)
        enable_nics(get_nics_to_enable(nics_file))


def is_vmware_cust_enabled(sys_cfg):
    return not util.get_cfg_option_bool(
        sys_cfg, "disable_vmware_customization", True
    )


def is_raw_data_cust_enabled(ds_cfg):
    return util.get_cfg_option_bool(ds_cfg, "allow_raw_data", True)


def get_cust_cfg_file(ds_cfg):
    # When the VM is powered on, the "VMware Tools" daemon
    # copies the customization specification file to
    # /var/run/vmware-imc directory. cloud-init code needs
    # to search for the file in that directory which indicates
    # that required metadata and userdata files are now
    # present.
    max_wait = get_max_wait_from_cfg(ds_cfg)
    cust_cfg_file_path = util.log_time(
        logfunc=logger.debug,
        msg="Waiting for VMware customization configuration file",
        func=wait_for_cust_cfg_file,
        args=("cust.cfg", max_wait),
    )
    if cust_cfg_file_path:
        logger.debug(
            "Found VMware customization configuration file at %s",
            cust_cfg_file_path,
        )
        return cust_cfg_file_path
    else:
        logger.debug("No VMware customization configuration file found")
    return None


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
        logger.debug("Waiting for VMware customization configuration file")
        time.sleep(naplen)
        waited += naplen
    return None


def get_max_wait_from_cfg(ds_cfg):
    default_max_wait = 15
    max_wait_cfg_option = "vmware_cust_file_max_wait"
    max_wait = default_max_wait
    if not ds_cfg:
        return max_wait
    try:
        max_wait = int(ds_cfg.get(max_wait_cfg_option, default_max_wait))
    except ValueError:
        logger.warning(
            "Failed to get '%s', using %s",
            max_wait_cfg_option,
            default_max_wait,
        )
    if max_wait < 0:
        logger.warning(
            "Invalid value '%s' for '%s', using '%s' instead",
            max_wait,
            max_wait_cfg_option,
            default_max_wait,
        )
        max_wait = default_max_wait
    return max_wait


def check_markers(cloud_dir, cust_cfg):
    product_marker = cust_cfg.marker_id
    has_marker_file = check_marker_exists(
        product_marker, os.path.join(cloud_dir, "data")
    )
    return product_marker and not has_marker_file


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


def recheck_markers(cloud_dir, cust_cfg):
    product_marker = cust_cfg.marker_id
    if product_marker:
        if not create_marker_file(cloud_dir, cust_cfg):
            return False
    return True


def create_marker_file(cloud_dir, cust_cfg):
    try:
        setup_marker_files(cust_cfg.marker_id, os.path.join(cloud_dir, "data"))
    except Exception as e:
        set_cust_error_status(
            "Error creating marker files",
            str(e),
            GuestCustEventEnum.GUESTCUST_EVENT_CUSTOMIZE_FAILED,
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
    logger.debug("Handle marker creation")
    marker_file = os.path.join(marker_dir, ".markerfile-" + marker_id + ".txt")
    for fname in os.listdir(marker_dir):
        if fname.startswith(".markerfile"):
            util.del_file(os.path.join(marker_dir, fname))
    open(marker_file, "w").close()


def do_special_customization(scripts_cpath, cust_cfg, cust_cfg_dir, distro):
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
    is_password_custom_successful = do_password_customization(cust_cfg, distro)
    if custom_script and is_custom_script_enabled:
        ccScriptsDir = os.path.join(scripts_cpath, "per-instance")
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


def do_pre_custom_script(cust_cfg, custom_script, cust_cfg_dir):
    try:
        precust = PreCustomScript(custom_script, cust_cfg_dir)
        precust.execute()
    except Exception as e:
        set_cust_error_status(
            "Error executing pre-customization script",
            str(e),
            GuestCustEventEnum.GUESTCUST_EVENT_CUSTOMIZE_FAILED,
            cust_cfg,
        )
        return False
    return True


def do_post_custom_script(cust_cfg, custom_script, cust_cfg_dir, ccScriptsDir):
    try:
        postcust = PostCustomScript(custom_script, cust_cfg_dir, ccScriptsDir)
        postcust.execute()
    except Exception as e:
        set_cust_error_status(
            "Error executing post-customization script",
            str(e),
            GuestCustEventEnum.GUESTCUST_EVENT_CUSTOMIZE_FAILED,
            cust_cfg,
        )
        return False
    return True


def check_custom_script_enablement(cust_cfg):
    is_custom_script_enabled = False
    default_value = "false"
    if cust_cfg.default_run_post_script:
        logger.debug(
            "Set default value to true due to customization configuration."
        )
        default_value = "true"
    custom_script_enablement = get_tools_config(
        IMC_TOOLS_CONF_GROUPNAME,
        IMC_TOOLS_CONF_ENABLE_CUST_SCRIPTS,
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


def do_password_customization(cust_cfg, distro):
    logger.debug("Applying password customization")
    pwdConfigurator = PasswordConfigurator()
    admin_pwd = cust_cfg.admin_password
    try:
        reset_pwd = cust_cfg.reset_password
        if admin_pwd or reset_pwd:
            pwdConfigurator.configure(admin_pwd, reset_pwd, distro)
        else:
            logger.debug("Changing password is not needed")
    except Exception as e:
        set_cust_error_status(
            "Error applying password configuration",
            str(e),
            GuestCustEventEnum.GUESTCUST_EVENT_CUSTOMIZE_FAILED,
            cust_cfg,
        )
        return False
    return True


def parse_cust_cfg(cfg_file):
    return Config(ConfigFile(cfg_file))


def get_cust_cfg_type(cust_cfg):
    is_vmware_cust_cfg, is_raw_data_cust_cfg = False, False
    if cust_cfg.meta_data_name:
        is_raw_data_cust_cfg = True
        logger.debug("raw cloudinit data cust cfg found")
    else:
        is_vmware_cust_cfg = True
        logger.debug("vmware cust cfg found")
    return (is_vmware_cust_cfg, is_raw_data_cust_cfg)


def is_cust_plugin_available():
    search_paths = (
        "/usr/lib/vmware-tools",
        "/usr/lib64/vmware-tools",
        "/usr/lib/open-vm-tools",
        "/usr/lib64/open-vm-tools",
        "/usr/lib/x86_64-linux-gnu/open-vm-tools",
        "/usr/lib/aarch64-linux-gnu/open-vm-tools",
        "/usr/lib/i386-linux-gnu/open-vm-tools",
    )
    cust_plugin = "libdeployPkgPlugin.so"
    for path in search_paths:
        cust_plugin_path = search_file(path, cust_plugin)
        if cust_plugin_path:
            logger.debug(
                "Found the customization plugin at %s", cust_plugin_path
            )
            return True
    return False


def search_file(dirpath, filename):
    if not dirpath or not filename:
        return None

    for root, _dirs, files in os.walk(dirpath):
        if filename in files:
            return os.path.join(root, filename)

    return None


def set_cust_error_status(prefix, error, event, cust_cfg):
    """
    Set customization status to the underlying VMware Virtualization Platform
    """
    util.logexc(logger, "%s: %s", prefix, error)
    set_customization_status(GuestCustStateEnum.GUESTCUST_STATE_RUNNING, event)
    set_gc_status(cust_cfg, prefix)
