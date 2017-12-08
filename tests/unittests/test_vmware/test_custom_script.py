# Copyright (C) 2015 Canonical Ltd.
# Copyright (C) 2017 VMware INC.
#
# Author: Maitreyee Saikia <msaikia@vmware.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import util
from cloudinit.sources.helpers.vmware.imc.config_custom_script import (
    CustomScriptConstant,
    CustomScriptNotFound,
    PreCustomScript,
    PostCustomScript,
)
from cloudinit.tests.helpers import CiTestCase, mock


class TestVmwareCustomScript(CiTestCase):
    def setUp(self):
        self.tmpDir = self.tmp_dir()

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
        self.assertEqual(self.tmp_path("random-vmw-test", self.tmpDir),
                         preCust.scriptpath)
        with self.assertRaises(CustomScriptNotFound):
            preCust.prepare_script()

        # Custom script exists.
        custScript = self.tmp_path("test-cust", self.tmpDir)
        util.write_file(custScript, "test-CR-strip/r/r")
        postCust = PostCustomScript("test-cust", self.tmpDir)
        self.assertEqual("test-cust", postCust.scriptname)
        self.assertEqual(self.tmpDir, postCust.directory)
        self.assertEqual(custScript, postCust.scriptpath)
        self.assertFalse(postCust.postreboot)
        postCust.prepare_script()
        # Check if all carraige returns are stripped from script.
        self.assertFalse("/r" in custScript)

    def test_rc_local_exists(self):
        """
        This test is designed to verify the different scenarios associated
        with the presence of rclocal.
        """
        # test when rc local does not exist
        postCust = PostCustomScript("test-cust", self.tmpDir)
        with mock.patch.object(CustomScriptConstant, "RC_LOCAL", "/no/path"):
            rclocal = postCust.find_rc_local()
            self.assertEqual("", rclocal)

        # test when rc local exists
        rclocalFile = self.tmp_path("vmware-rclocal", self.tmpDir)
        util.write_file(rclocalFile, "# Run post-reboot guest customization",
                        omode="w")
        with mock.patch.object(CustomScriptConstant, "RC_LOCAL", rclocalFile):
            rclocal = postCust.find_rc_local()
            self.assertEqual(rclocalFile, rclocal)
            self.assertTrue(postCust.has_previous_agent, rclocal)

        # test when rc local is a symlink
        rclocalLink = self.tmp_path("dummy-rclocal-link", self.tmpDir)
        util.sym_link(rclocalFile, rclocalLink, True)
        with mock.patch.object(CustomScriptConstant, "RC_LOCAL", rclocalLink):
            rclocal = postCust.find_rc_local()
            self.assertEqual(rclocalFile, rclocal)

    def test_execute_post_cust(self):
        """
        This test is to identify if rclocal was properly populated to be
        run after reboot.
        """
        customscript = self.tmp_path("vmware-post-cust-script", self.tmpDir)
        rclocal = self.tmp_path("vmware-rclocal", self.tmpDir)
        # Create a temporary rclocal file
        open(customscript, "w")
        util.write_file(rclocal, "tests\nexit 0", omode="w")
        postCust = PostCustomScript("vmware-post-cust-script", self.tmpDir)
        with mock.patch.object(CustomScriptConstant, "RC_LOCAL", rclocal):
            # Test that guest customization agent is not installed initially.
            self.assertFalse(postCust.postreboot)
            self.assertIs(postCust.has_previous_agent(rclocal), False)
            postCust.install_agent()

            # Assert rclocal has been modified to have guest customization
            # agent.
            self.assertTrue(postCust.postreboot)
            self.assertTrue(postCust.has_previous_agent, rclocal)

# vi: ts=4 expandtab
