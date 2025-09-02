# Copyright (C) 2015 Canonical Ltd.
# Copyright (C) 2017-2019 VMware INC.
#
# Author: Maitreyee Saikia <msaikia@vmware.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import os
import stat
from unittest import mock

import pytest

from cloudinit import util
from cloudinit.sources.helpers.vmware.imc.config_custom_script import (
    CustomScriptConstant,
    CustomScriptNotFound,
    PostCustomScript,
    PreCustomScript,
)


@pytest.fixture
def fake_exec_dir(mocker, tmp_path):
    exec_dir = tmp_path / ".customization"
    mocker.patch.object(CustomScriptConstant, "CUSTOM_TMP_DIR", str(exec_dir))
    return exec_dir


@pytest.fixture
def fake_exec_script(fake_exec_dir, mocker):
    ex_script = fake_exec_dir / ".customize.sh"
    mocker.patch.object(CustomScriptConstant, "CUSTOM_SCRIPT", str(ex_script))
    return ex_script


class TestVmwareCustomScript:
    def test_prepare_custom_script(self, fake_exec_script, tmp_path):
        """
        This test is designed to verify the behavior based on the presence of
        custom script. Mainly needed for scenario where a custom script is
        expected, but was not properly copied. "CustomScriptNotFound" exception
        is raised in such cases.
        """
        # Custom script does not exist.
        preCust = PreCustomScript("random-vmw-test", str(tmp_path))
        assert "random-vmw-test" == preCust.scriptname
        assert str(tmp_path) == preCust.directory
        assert str(tmp_path / "random-vmw-test") == preCust.scriptpath
        with pytest.raises(CustomScriptNotFound):
            preCust.prepare_script()

        # Custom script exists.
        custScript = str(tmp_path / "test-cust")
        util.write_file(custScript, "test-CR-strip\r\r")

        postCust = PostCustomScript("test-cust", str(tmp_path), str(tmp_path))
        assert "test-cust" == postCust.scriptname
        assert str(tmp_path) == preCust.directory
        assert custScript == postCust.scriptpath
        postCust.prepare_script()

        # Custom script is copied with exec privilege
        assert fake_exec_script.exists()
        st = os.stat(fake_exec_script)
        assert st.st_mode & stat.S_IEXEC
        assert "test-CR-strip" == fake_exec_script.read_text()

    def test_execute_post_cust(self, fake_exec_script, tmp_path):
        """
        This test is designed to verify the behavior after execute post
        customization.
        """
        # Prepare the customize package
        postCustRun = str(tmp_path / "post-customize-guest.sh")
        util.write_file(postCustRun, "This is the script to run post cust")
        userScript = str(tmp_path / "test-cust")
        util.write_file(userScript, "This is the post cust script")

        # Mock the cc_scripts_per_instance dir and marker file.
        # Create another tmp dir for cc_scripts_per_instance.
        ccScriptDir = tmp_path / "out"
        ccScriptDir.mkdir()
        ccScript = ccScriptDir / "post-customize-guest.sh"
        markerFile = tmp_path / ".markerFile"

        with mock.patch.object(
            CustomScriptConstant,
            "POST_CUSTOM_PENDING_MARKER",
            str(markerFile),
        ):
            postCust = PostCustomScript(
                "test-cust", str(tmp_path), ccScriptDir
            )
            postCust.execute()
            # Check cc_scripts_per_instance and marker file
            # are created.
            assert ccScript.exists()
            assert (
                "This is the script to run post cust" == ccScript.read_text()
            )
            assert markerFile.exists()
