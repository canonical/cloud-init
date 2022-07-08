# This file is part of cloud-init. See LICENSE file for license information.

import logging
from unittest import mock

import pytest

from cloudinit.config import cc_autoinstall
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import skipUnlessJsonSchema
from tests.unittests.util import get_cloud

LOG = logging.getLogger(__name__)

MODPATH = "cloudinit.config.cc_autoinstall."

SAMPLE_SNAP_LIST_OUTPUT = """
Name                     Version                     Rev    Tracking      ...
core20                   20220527                    1518   latest/stable ...
lxd                      git-69dc707                 23315  latest/edge   ...
"""


class TestvalidateConfigSchema:
    @pytest.mark.parametrize(
        "src_cfg,error_msg",
        [
            pytest.param(
                {"autoinstall": 1},
                "autoinstall: Expected dict type but found: int",
                id="err_non_dict",
            ),
            pytest.param(
                {"autoinstall": {}},
                "autoinstall: Missing required 'version' key",
                id="err_require_version_key",
            ),
            pytest.param(
                {"autoinstall": {"version": "v1"}},
                "autoinstall.version: Expected int type but found: str",
                id="err_version_non_int",
            ),
        ],
    )
    def test_runtime_validation_errors(self, src_cfg, error_msg):
        """cloud-init raises errors at runtime on invalid autoinstall config"""
        with pytest.raises(SchemaValidationError, match=error_msg):
            cc_autoinstall.validate_config_schema(src_cfg)


@mock.patch(MODPATH + "subp")
class TestHandleAutoinstall:
    """Test cc_autoinstall handling of config."""

    @pytest.mark.parametrize(
        "cfg,subp_calls,logs",
        [
            pytest.param(
                {},
                [],
                ["Skipping module named name, no 'autoinstall' key"],
                id="skip_no_cfg",
            ),
            pytest.param(
                {"autoinstall": {"version": 1}},
                [mock.call(["snap", "list"])],
                [
                    "Skipping autoinstall module. Expected one of the Ubuntu"
                    " installer snap packages to be present: subiquity,"
                    " ubuntu-desktop-installer"
                ],
                id="valid_autoinstall_schema_checks_snaps",
            ),
        ],
    )
    def test_handle_autoinstall_cfg(self, subp, cfg, subp_calls, logs, caplog):
        subp.return_value = SAMPLE_SNAP_LIST_OUTPUT, ""
        cloud = get_cloud(distro="ubuntu")
        cc_autoinstall.handle("name", cfg, cloud, LOG, None)
        assert subp_calls == subp.call_args_list
        for log in logs:
            assert log in caplog.text


class TestAutoInstallSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        (
            (
                {"autoinstall": {}},
                "autoinstall: 'version' is a required property",
            ),
        ),
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        if error_msg is None:
            validate_cloudconfig_schema(config, get_schema(), strict=True)
        else:
            with pytest.raises(SchemaValidationError, match=error_msg):
                validate_cloudconfig_schema(config, get_schema(), strict=True)
