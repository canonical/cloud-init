# This file is part of cloud-init. See LICENSE file for license information.

import logging
from unittest import mock

import pytest

from cloudinit.config import cc_ubuntu_autoinstall
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from cloudinit.helpers import Paths
from tests.unittests.helpers import skipUnlessJsonSchema
from tests.unittests.util import get_cloud

LOG = logging.getLogger(__name__)

MODPATH = "cloudinit.config.cc_ubuntu_autoinstall."

SAMPLE_SNAP_LIST_OUTPUT = """
Name                     Version                     Rev    Tracking      ...
core20                   20220527                    1518   latest/stable ...
lxd                      git-69dc707                 23315  latest/edge   ...
"""
SAMPLE_SNAP_LIST_SUBIQUITY = (
    SAMPLE_SNAP_LIST_OUTPUT
    + """
subiquity                22.06.01                 23315  latest/stable   ...
"""
)
SAMPLE_SNAP_LIST_DESKTOP_INSTALLER = (
    SAMPLE_SNAP_LIST_OUTPUT
    + """
ubuntu-desktop-installer 22.06.01                 23315  latest/stable   ...
"""
)


@mock.patch(MODPATH + "util.wait_for_snap_seeded")
@mock.patch(MODPATH + "subp.subp")
class TestHandleAutoinstall:
    """Test cc_ubuntu_autoinstall handling of config."""

    @pytest.mark.parametrize(
        "cfg,snap_list,subp_calls,logs,snap_wait_called",
        [
            pytest.param(
                {"autoinstall": {"version": 1}},
                SAMPLE_SNAP_LIST_OUTPUT,
                [mock.call(["snap", "list"])],
                [
                    "Skipping autoinstall module. Expected one of the Ubuntu"
                    " installer snap packages to be present: subiquity,"
                    " ubuntu-desktop-installer"
                ],
                True,
                id="valid_autoinstall_schema_checks_snaps",
            ),
            pytest.param(
                {"autoinstall": {"version": 1}},
                SAMPLE_SNAP_LIST_SUBIQUITY,
                [mock.call(["snap", "list"])],
                [
                    "Valid autoinstall schema. Config will be processed by"
                    " subiquity"
                ],
                True,
                id="valid_autoinstall_schema_sees_subiquity",
            ),
            pytest.param(
                {"autoinstall": {"version": 1}},
                SAMPLE_SNAP_LIST_DESKTOP_INSTALLER,
                [mock.call(["snap", "list"])],
                [
                    "Valid autoinstall schema. Config will be processed by"
                    " ubuntu-desktop-installer"
                ],
                True,
                id="valid_autoinstall_schema_sees_desktop_installer",
            ),
        ],
    )
    def test_handle_autoinstall_cfg(
        self,
        subp,
        wait_for_snap_seeded,
        cfg,
        snap_list,
        subp_calls,
        logs,
        snap_wait_called,
        caplog,
        tmpdir,
    ):
        subp.return_value = snap_list, ""
        cloud = get_cloud(distro="ubuntu", paths=Paths({"cloud_dir": tmpdir}))
        cc_ubuntu_autoinstall.handle("name", cfg, cloud, None)
        assert subp_calls == subp.call_args_list
        for log in logs:
            assert log in caplog.text
        if snap_wait_called:
            wait_for_snap_seeded.assert_called_once_with(cloud)
        else:
            wait_for_snap_seeded.assert_not_called()


class TestAutoInstallSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        (
            (
                {"autoinstall": {}},
                "autoinstall: 'version' is a required property",
            ),
            ({"autoinstall": {"version": 1}}, None),
            ({"autoinstall": {"version": "v1"}}, "is not of type 'integer'"),
        ),
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        if error_msg is None:
            validate_cloudconfig_schema(config, get_schema(), strict=True)
        else:
            with pytest.raises(SchemaValidationError, match=error_msg):
                validate_cloudconfig_schema(config, get_schema(), strict=True)
