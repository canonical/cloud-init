# Copyright (C) 2017 Canonical Ltd.
# Copyright (C) 2017 VMware Inc.
#
# Author: Maitreyee Saikia <msaikia@vmware.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import logging
import os
import stat
from textwrap import dedent

from cloudinit import util

LOG = logging.getLogger(__name__)


class CustomScriptNotFound(Exception):
    pass


class CustomScriptConstant(object):
    RC_LOCAL = "/etc/rc.local"
    POST_CUST_TMP_DIR = "/root/.customization"
    POST_CUST_RUN_SCRIPT_NAME = "post-customize-guest.sh"
    POST_CUST_RUN_SCRIPT = os.path.join(POST_CUST_TMP_DIR,
                                        POST_CUST_RUN_SCRIPT_NAME)
    POST_REBOOT_PENDING_MARKER = "/.guest-customization-post-reboot-pending"


class RunCustomScript(object):
    def __init__(self, scriptname, directory):
        self.scriptname = scriptname
        self.directory = directory
        self.scriptpath = os.path.join(directory, scriptname)

    def prepare_script(self):
        if not os.path.exists(self.scriptpath):
            raise CustomScriptNotFound("Script %s not found!! "
                                       "Cannot execute custom script!"
                                       % self.scriptpath)
        # Strip any CR characters from the decoded script
        util.load_file(self.scriptpath).replace("\r", "")
        st = os.stat(self.scriptpath)
        os.chmod(self.scriptpath, st.st_mode | stat.S_IEXEC)


class PreCustomScript(RunCustomScript):
    def execute(self):
        """Executing custom script with precustomization argument."""
        LOG.debug("Executing pre-customization script")
        self.prepare_script()
        util.subp(["/bin/sh", self.scriptpath, "precustomization"])


class PostCustomScript(RunCustomScript):
    def __init__(self, scriptname, directory):
        super(PostCustomScript, self).__init__(scriptname, directory)
        # Determine when to run custom script. When postreboot is True,
        # the user uploaded script will run as part of rc.local after
        # the machine reboots. This is determined by presence of rclocal.
        # When postreboot is False, script will run as part of cloud-init.
        self.postreboot = False

    def _install_post_reboot_agent(self, rclocal):
        """
        Install post-reboot agent for running custom script after reboot.
        As part of this process, we are editing the rclocal file to run a
        VMware script, which in turn is resposible for handling the user
        script.
        @param: path to rc local.
        """
        LOG.debug("Installing post-reboot customization from %s to %s",
                  self.directory, rclocal)
        if not self.has_previous_agent(rclocal):
            LOG.info("Adding post-reboot customization agent to rc.local")
            new_content = dedent("""
                # Run post-reboot guest customization
                /bin/sh %s
                exit 0
                """) % CustomScriptConstant.POST_CUST_RUN_SCRIPT
            existing_rclocal = util.load_file(rclocal).replace('exit 0\n', '')
            st = os.stat(rclocal)
            # "x" flag should be set
            mode = st.st_mode | stat.S_IEXEC
            util.write_file(rclocal, existing_rclocal + new_content, mode)

        else:
            # We don't need to update rclocal file everytime a customization
            # is requested. It just needs to be done for the first time.
            LOG.info("Post-reboot guest customization agent is already "
                     "registered in rc.local")
        LOG.debug("Installing post-reboot customization agent finished: %s",
                  self.postreboot)

    def has_previous_agent(self, rclocal):
        searchstring = "# Run post-reboot guest customization"
        if searchstring in open(rclocal).read():
            return True
        return False

    def find_rc_local(self):
        """
        Determine if rc local is present.
        """
        rclocal = ""
        if os.path.exists(CustomScriptConstant.RC_LOCAL):
            LOG.debug("rc.local detected.")
            # resolving in case of symlink
            rclocal = os.path.realpath(CustomScriptConstant.RC_LOCAL)
            LOG.debug("rc.local resolved to %s", rclocal)
        else:
            LOG.warning("Can't find rc.local, post-customization "
                        "will be run before reboot")
        return rclocal

    def install_agent(self):
        rclocal = self.find_rc_local()
        if rclocal:
            self._install_post_reboot_agent(rclocal)
            self.postreboot = True

    def execute(self):
        """
        This method executes post-customization script before or after reboot
        based on the presence of rc local.
        """
        self.prepare_script()
        self.install_agent()
        if not self.postreboot:
            LOG.warning("Executing post-customization script inline")
            util.subp(["/bin/sh", self.scriptpath, "postcustomization"])
        else:
            LOG.debug("Scheduling custom script to run post reboot")
            if not os.path.isdir(CustomScriptConstant.POST_CUST_TMP_DIR):
                os.mkdir(CustomScriptConstant.POST_CUST_TMP_DIR)
            # Script "post-customize-guest.sh" and user uploaded script are
            # are present in the same directory and needs to copied to a temp
            # directory to be executed post reboot. User uploaded script is
            # saved as customize.sh in the temp directory.
            # post-customize-guest.sh excutes customize.sh after reboot.
            LOG.debug("Copying post-customization script")
            util.copy(self.scriptpath,
                      CustomScriptConstant.POST_CUST_TMP_DIR + "/customize.sh")
            LOG.debug("Copying script to run post-customization script")
            util.copy(
                os.path.join(self.directory,
                             CustomScriptConstant.POST_CUST_RUN_SCRIPT_NAME),
                CustomScriptConstant.POST_CUST_RUN_SCRIPT)
            LOG.info("Creating post-reboot pending marker")
            util.ensure_file(CustomScriptConstant.POST_REBOOT_PENDING_MARKER)

# vi: ts=4 expandtab
