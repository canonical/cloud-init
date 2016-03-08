# vi: ts=4 expandtab
#
#    Copyright (C) 2016 Canonical Ltd.
#    Copyright (C) 2016 VMware Inc.
#
#    Author: Sankar Tanguturi <stanguturi@vmware.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License version 3, as
#    published by the Free Software Foundation.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

import logging
import os

from cloudinit import util


logger = logging.getLogger(__name__)


CLOUDINIT_LOG_FILE = "/var/log/cloud-init.log"


# This will send a RPC command to the underlying
# VMware Virtualization Platform.
def send_rpc(rpc):
    if not rpc:
        return None

    rc = 1
    output = "Error sending the RPC command"

    try:
        logger.debug("Sending RPC command: %s", rpc)
        (rc, output) = util.subp(["vmware-rpctool", rpc], rcs=[0])
    except Exception as e:
        logger.debug("Failed to send RPC command")
        logger.exception(e)

    return (rc, output)


# This will send the customization status to the
# underlying VMware Virtualization Platform.
def set_customization_status(custstate, custerror, errormessage=None):
    message = ""

    if errormessage:
        message = CLOUDINIT_LOG_FILE + "@" + errormessage
    else:
        message = CLOUDINIT_LOG_FILE

    rpc = "deployPkg.update.state %d %d %s" % (custstate, custerror, message)
    (rc, output) = send_rpc(rpc)


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
