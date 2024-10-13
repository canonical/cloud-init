# This file is part of cloud-init. See LICENSE file for license information.

import re
from unittest import mock

import pytest

from cloudinit.config import cc_byobu
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import skipUnlessJsonSchema
from tests.unittests.util import get_cloud

M_PATH = "cloudinit.config.cc_byobu."


class TestHandleByobu:
    """Validate behavior of cc_byobu.handle function."""

    def test_handle_no_cfg(self, caplog):
        """Exit early when no applicable config."""
        cloud = get_cloud(distro="ubuntu")
        cc_byobu.handle("byobu", cfg={}, cloud=cloud, args=[])
        assert "Skipping module named byobu, no 'byobu' values" in caplog.text

    @pytest.mark.parametrize(
        "cfg, which_response, expected_cmds",
        (
            pytest.param(
                {"byobu_by_default": "disable-system"},
                "",  # byobu command not installed
                [
                    mock.call(
                        [
                            "/bin/sh",
                            "-c",
                            'X=0; echo "byobu byobu/launch-by-default boolean'
                            ' false" | debconf-set-selections &&'
                            " dpkg-reconfigure byobu --frontend=noninteractive"
                            " || X=$(($X+1));  exit $X",
                        ],
                        capture=False,
                    )
                ],
                id="install_byobu_pkg_when_absent_and_setup",
            ),
            pytest.param(
                {"byobu_by_default": "disable-system"},
                "/usr/bin/byobu",  # byobu command not installed
                [
                    mock.call(
                        [
                            "/bin/sh",
                            "-c",
                            'X=0; echo "byobu byobu/launch-by-default'
                            ' boolean false" | debconf-set-selections &&'
                            " dpkg-reconfigure byobu --frontend=noninteractive"
                            " || X=$(($X+1));  exit $X",
                        ],
                        capture=False,
                    )
                ],
                id="setup_byobu_pkg_when_present",
            ),
        ),
    )
    @mock.patch(f"{M_PATH}subp.which")
    @mock.patch(f"{M_PATH}subp.subp", return_value=("", ""))
    def test_handle_install_byobu_if_needed(
        self, subp, subp_which, cfg, which_response, expected_cmds, caplog
    ):
        """Perform expected commands and install byobu on byobu user-data."""
        subp_which.return_value = which_response
        cloud = get_cloud(distro="ubuntu")
        with mock.patch.object(
            cloud.distro, "install_packages"
        ) as install_pkgs:
            cc_byobu.handle("byobu", cfg=cfg, cloud=cloud, args=[])
        assert expected_cmds == subp.call_args_list
        subp_which.assert_called_with("byobu")
        if which_response:
            install_pkgs.assert_not_called()
        else:
            install_pkgs.assert_called_once_with(["byobu"])


class TestByobuSchema:
    """Directly test schema rather than through handle."""

    @pytest.mark.parametrize(
        "config, error_msg",
        (
            # Supplement valid schemas tested by meta.examples in test_schema
            ({"byobu_by_default": "enable"}, None),
            # Invalid schemas
            (
                {"byobu_by_default": 1},
                "byobu_by_default: 1 is not of type 'string'",
            ),
            (
                {"byobu_by_default": "bogusenum"},
                re.escape(
                    "byobu_by_default: 'bogusenum' is not one of"
                    " ['enable-system', 'enable-user', 'disable-system',"
                    " 'disable-user', 'enable', 'disable',"
                    " 'user', 'system']"
                ),
            ),
        ),
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        """Assert expected schema validation and error messages."""
        # New-style schema $defs exist in config/cloud-init-schema*.json
        schema = get_schema()
        if error_msg is None:
            validate_cloudconfig_schema(config, schema, strict=True)
        else:
            with pytest.raises(SchemaValidationError, match=error_msg):
                validate_cloudconfig_schema(config, schema, strict=True)
