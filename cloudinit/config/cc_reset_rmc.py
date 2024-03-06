# (c) Copyright IBM Corp. 2020 All Rights Reserved
#
# Author: Aman Kumar Sinha <amansi26@in.ibm.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
"""Reset RMC: Reset rsct node id"""
import logging
import os

from cloudinit import subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.distros import ALL_DISTROS
from cloudinit.settings import PER_INSTANCE

MODULE_DESCRIPTION = """\
Reset RMC module is IBM PowerVM Hypervisor specific

Reliable Scalable Cluster Technology (RSCT) is a set of software components,
that  together provide a comprehensive clustering environment (RAS features)
for IBM PowerVM based virtual machines. RSCT includes the Resource monitoring
and control (RMC) subsystem. RMC is a generalized framework used for managing,
monitoring, and manipulating resources. RMC runs as a daemon process on
individual machines and needs creation of unique node id and restarts
during VM boot.
More details refer
https://www.ibm.com/support/knowledgecenter/en/SGVKBA_3.2/admin/bl503_ovrv.htm

This module handles
- creation of the unique RSCT node id to every instance/virtual machine
  and ensure once set, it isn't changed subsequently by cloud-init.
  In order to do so, it restarts RSCT service.

Prerequisite of using this module is to install RSCT packages.
"""

meta: MetaSchema = {
    "id": "cc_reset_rmc",
    "name": "Reset RMC",
    "title": "reset rsct node id",
    "description": MODULE_DESCRIPTION,
    "distros": [ALL_DISTROS],
    "frequency": PER_INSTANCE,
    "examples": [],
    "activate_by_schema_keys": [],
}

# This module is undocumented in our schema docs
__doc__ = ""

# RMCCTRL is expected to be in system PATH (/opt/rsct/bin)
# The symlink for RMCCTRL and RECFGCT are
# /usr/sbin/rsct/bin/rmcctrl and
# /usr/sbin/rsct/install/bin/recfgct respectively.
RSCT_PATH = "/opt/rsct/install/bin"
RMCCTRL = "rmcctrl"
RECFGCT = "recfgct"

LOG = logging.getLogger(__name__)

NODE_ID_FILE = "/etc/ct_node_id"


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    # Ensuring node id has to be generated only once during first boot
    if cloud.datasource.platform_type == "none":
        LOG.debug("Skipping creation of new ct_node_id node")
        return

    if not os.path.isdir(RSCT_PATH):
        LOG.debug("module disabled, RSCT_PATH not present")
        return

    orig_path = os.environ.get("PATH")
    try:
        add_path(orig_path)
        reset_rmc()
    finally:
        if orig_path:
            os.environ["PATH"] = orig_path
        else:
            del os.environ["PATH"]


def reconfigure_rsct_subsystems():
    # Reconfigure the RSCT subsystems, which includes removing all RSCT data
    # under the /var/ct directory, generating a new node ID, and making it
    # appear as if the RSCT components were just installed
    try:
        out = subp.subp([RECFGCT])[0]
        LOG.debug(out.strip())
        return out
    except subp.ProcessExecutionError:
        util.logexc(LOG, "Failed to reconfigure the RSCT subsystems.")
        raise


def get_node_id():
    try:
        fp = util.load_text_file(NODE_ID_FILE)
        node_id = fp.split("\n")[0]
        return node_id
    except Exception:
        util.logexc(LOG, "Failed to get node ID from file %s." % NODE_ID_FILE)
        raise


def add_path(orig_path):
    # Adding the RSCT_PATH to env standard path
    # So thet cloud init automatically find and
    # run RECFGCT to create new node_id.
    suff = ":" + orig_path if orig_path else ""
    os.environ["PATH"] = RSCT_PATH + suff
    return os.environ["PATH"]


def rmcctrl():
    # Stop the RMC subsystem and all resource managers so that we can make
    # some changes to it
    try:
        return subp.subp([RMCCTRL, "-z"])
    except Exception:
        util.logexc(LOG, "Failed to stop the RMC subsystem.")
        raise


def reset_rmc():
    LOG.debug("Attempting to reset RMC.")

    node_id_before = get_node_id()
    LOG.debug("Node ID at beginning of module: %s", node_id_before)

    # Stop the RMC subsystem and all resource managers so that we can make
    # some changes to it
    rmcctrl()
    reconfigure_rsct_subsystems()

    node_id_after = get_node_id()
    LOG.debug("Node ID at end of module: %s", node_id_after)

    # Check if new node ID is generated or not
    # by comparing old and new node ID
    if node_id_after == node_id_before:
        msg = "New node ID did not get generated."
        LOG.error(msg)
        raise RuntimeError(msg)
