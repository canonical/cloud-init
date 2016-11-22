# Copyright (C) 2016 Canonical Ltd.
# Copyright (C) 2016 VMware Inc.
#
# Author: Sankar Tanguturi <stanguturi@vmware.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import logging
import os
import time

from cloudinit import util

from .guestcust_event import GuestCustEventEnum
from .guestcust_state import GuestCustStateEnum

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
        (out, err) = util.subp(["vmware-rpctool", rpc], rcs=[0])
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


# This will read the file nics.txt in the specified directory
# and return the content
def get_nics_to_enable(dirpath):
    if not dirpath:
        return None

    NICS_SIZE = 1024
    nicsfilepath = os.path.join(dirpath, "nics.txt")
    if not os.path.exists(nicsfilepath):
        return None

    with open(nicsfilepath, 'r') as fp:
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
        (out, err) = set_customization_status(
            GuestCustStateEnum.GUESTCUST_STATE_RUNNING,
            GuestCustEventEnum.GUESTCUST_EVENT_ENABLE_NICS,
            nics)
        if not out:
            time.sleep(enableNicsWaitCount * enableNicsWaitSeconds)
            continue

        if out != QUERY_NICS_SUPPORTED:
            logger.warning("NICS connection status query is not supported")
            return

        for count in range(0, enableNicsWaitCount):
            (out, err) = set_customization_status(
                GuestCustStateEnum.GUESTCUST_STATE_RUNNING,
                GuestCustEventEnum.GUESTCUST_EVENT_QUERY_NICS,
                nics)
            if out and out == NICS_STATUS_CONNECTED:
                logger.info("NICS are connected on %d second", count)
                return

            time.sleep(enableNicsWaitSeconds)

    logger.warning("Can't connect network interfaces after %d attempts",
                   enableNicsWaitRetries)

# vi: ts=4 expandtab
