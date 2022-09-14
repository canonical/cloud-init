# Copyright (C) 2017 Canonical Ltd.
# Copyright (C) 2017-2019 VMware Inc.
#
# Author: Maitreyee Saikia <msaikia@vmware.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import logging
import os
import stat

from cloudinit import subp, util

LOG = logging.getLogger(__name__)


class CustomScriptNotFound(Exception):
    pass


class CustomScriptConstant:
    CUSTOM_TMP_DIR = "/root/.customization"

    # The user defined custom script
    CUSTOM_SCRIPT_NAME = "customize.sh"
    CUSTOM_SCRIPT = os.path.join(CUSTOM_TMP_DIR, CUSTOM_SCRIPT_NAME)
    POST_CUSTOM_PENDING_MARKER = "/.guest-customization-post-reboot-pending"
    # The cc_scripts_per_instance script to launch custom script
    POST_CUSTOM_SCRIPT_NAME = "post-customize-guest.sh"


class RunCustomScript:
    def __init__(self, scriptname, directory):
        self.scriptname = scriptname
        self.directory = directory
        self.scriptpath = os.path.join(directory, scriptname)

    def prepare_script(self):
        if not os.path.exists(self.scriptpath):
            raise CustomScriptNotFound(
                "Script %s not found!! Cannot execute custom script!"
                % self.scriptpath
            )

        util.ensure_dir(CustomScriptConstant.CUSTOM_TMP_DIR)

        LOG.debug(
            "Copying custom script to %s", CustomScriptConstant.CUSTOM_SCRIPT
        )
        util.copy(self.scriptpath, CustomScriptConstant.CUSTOM_SCRIPT)

        # Strip any CR characters from the decoded script
        content = util.load_file(CustomScriptConstant.CUSTOM_SCRIPT).replace(
            "\r", ""
        )
        util.write_file(
            CustomScriptConstant.CUSTOM_SCRIPT, content, mode=0o544
        )


class PreCustomScript(RunCustomScript):
    def execute(self):
        """Executing custom script with precustomization argument."""
        LOG.debug("Executing pre-customization script")
        self.prepare_script()
        subp.subp([CustomScriptConstant.CUSTOM_SCRIPT, "precustomization"])


class PostCustomScript(RunCustomScript):
    def __init__(self, scriptname, directory, ccScriptsDir):
        super(PostCustomScript, self).__init__(scriptname, directory)
        self.ccScriptsDir = ccScriptsDir
        self.ccScriptPath = os.path.join(
            ccScriptsDir, CustomScriptConstant.POST_CUSTOM_SCRIPT_NAME
        )

    def execute(self):
        """
        This method copy the post customize run script to
        cc_scripts_per_instance directory and let this
        module to run post custom script.
        """
        self.prepare_script()

        LOG.debug("Copying post customize run script to %s", self.ccScriptPath)
        util.copy(
            os.path.join(
                self.directory, CustomScriptConstant.POST_CUSTOM_SCRIPT_NAME
            ),
            self.ccScriptPath,
        )
        st = os.stat(self.ccScriptPath)
        os.chmod(self.ccScriptPath, st.st_mode | stat.S_IEXEC)
        LOG.info("Creating post customization pending marker")
        util.ensure_file(CustomScriptConstant.POST_CUSTOM_PENDING_MARKER)


# vi: ts=4 expandtab
