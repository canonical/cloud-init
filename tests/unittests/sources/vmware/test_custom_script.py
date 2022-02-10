# Copyright (C) 2015 Canonical Ltd.
# Copyright (C) 2017-2019 VMware INC.
#
# Author: Maitreyee Saikia <msaikia@vmware.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import os
import stat

from cloudinit import util
from cloudinit.sources.helpers.vmware.imc.config_custom_script import (
    CustomScriptConstant,
    CustomScriptNotFound,
    PostCustomScript,
    PreCustomScript,
)
from tests.unittests.helpers import CiTestCase, mock


class TestVmwareCustomScript(CiTestCase):
    def setUp(self):
        self.tmpDir = self.tmp_dir()
        # Mock the tmpDir as the root dir in VM.
        self.execDir = os.path.join(self.tmpDir, ".customization")
        self.execScript = os.path.join(self.execDir, ".customize.sh")

    def test_prepare_custom_script(self):
        """
        This test is designed to verify the behavior based on the presence of
        custom script. Mainly needed for scenario where a custom script is
        expected, but was not properly copied. "CustomScriptNotFound" exception
        is raised in such cases.
        """
        # Custom script does not exist.
        preCust = PreCustomScript("random-vmw-test", self.tmpDir)
        self.assertEqual("random-vmw-test", preCust.scriptname)
        self.assertEqual(self.tmpDir, preCust.directory)
        self.assertEqual(
            self.tmp_path("random-vmw-test", self.tmpDir), preCust.scriptpath
        )
        with self.assertRaises(CustomScriptNotFound):
            preCust.prepare_script()

        # Custom script exists.
        custScript = self.tmp_path("test-cust", self.tmpDir)
        util.write_file(custScript, "test-CR-strip\r\r")
        with mock.patch.object(
            CustomScriptConstant, "CUSTOM_TMP_DIR", self.execDir
        ):
            with mock.patch.object(
                CustomScriptConstant, "CUSTOM_SCRIPT", self.execScript
            ):
                postCust = PostCustomScript(
                    "test-cust", self.tmpDir, self.tmpDir
                )
                self.assertEqual("test-cust", postCust.scriptname)
                self.assertEqual(self.tmpDir, postCust.directory)
                self.assertEqual(custScript, postCust.scriptpath)
                postCust.prepare_script()

                # Custom script is copied with exec privilege
                self.assertTrue(os.path.exists(self.execScript))
                st = os.stat(self.execScript)
                self.assertTrue(st.st_mode & stat.S_IEXEC)
                with open(self.execScript, "r") as f:
                    content = f.read()
                self.assertEqual(content, "test-CR-strip")
                # Check if all carraige returns are stripped from script.
                self.assertFalse("\r" in content)

    def test_execute_post_cust(self):
        """
        This test is designed to verify the behavior after execute post
        customization.
        """
        # Prepare the customize package
        postCustRun = self.tmp_path("post-customize-guest.sh", self.tmpDir)
        util.write_file(postCustRun, "This is the script to run post cust")
        userScript = self.tmp_path("test-cust", self.tmpDir)
        util.write_file(userScript, "This is the post cust script")

        # Mock the cc_scripts_per_instance dir and marker file.
        # Create another tmp dir for cc_scripts_per_instance.
        ccScriptDir = self.tmp_dir()
        ccScript = os.path.join(ccScriptDir, "post-customize-guest.sh")
        markerFile = os.path.join(self.tmpDir, ".markerFile")
        with mock.patch.object(
            CustomScriptConstant, "CUSTOM_TMP_DIR", self.execDir
        ):
            with mock.patch.object(
                CustomScriptConstant, "CUSTOM_SCRIPT", self.execScript
            ):
                with mock.patch.object(
                    CustomScriptConstant,
                    "POST_CUSTOM_PENDING_MARKER",
                    markerFile,
                ):
                    postCust = PostCustomScript(
                        "test-cust", self.tmpDir, ccScriptDir
                    )
                    postCust.execute()
                    # Check cc_scripts_per_instance and marker file
                    # are created.
                    self.assertTrue(os.path.exists(ccScript))
                    with open(ccScript, "r") as f:
                        content = f.read()
                    self.assertEqual(
                        content, "This is the script to run post cust"
                    )
                    self.assertTrue(os.path.exists(markerFile))


# vi: ts=4 expandtab
