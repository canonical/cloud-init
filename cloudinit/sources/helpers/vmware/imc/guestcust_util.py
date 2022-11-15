# Copyright (C) 2016 Canonical Ltd.
# Copyright (C) 2016 VMware Inc.
#
# Author: Sankar Tanguturi <stanguturi@vmware.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import logging
import os
import re
import time

from cloudinit import subp
from cloudinit.sources.helpers.vmware.imc.guestcust_event import (
    GuestCustEventEnum,
)
from cloudinit.sources.helpers.vmware.imc.guestcust_state import (
    GuestCustStateEnum,
)

logger = logging.getLogger(__name__)


CLOUDINIT_LOG_FILE = "/var/log/cloud-init.log"
QUERY_NICS_SUPPORTED = "queryNicsSupported"
NICS_STATUS_CONNECTED = "connected"


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

    for attempt in range(0, enableNicsWaitRetries):
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

        for count in range(0, enableNicsWaitCount):
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


# vi: ts=4 expandtab
