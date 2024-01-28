"""Tests for cc_keys_to_console."""

import re

import pytest

from cloudinit.config import cc_keys_to_console
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import mock, skipUnlessJsonSchema


class TestHandle:
    """Tests for cloudinit.config.cc_keys_to_console.handle.

    TODO: These tests only cover the emit_keys_to_console config option, they
    should be expanded to cover the full functionality.
    """

    @mock.patch("cloudinit.config.cc_keys_to_console.util.multi_log")
    @mock.patch("cloudinit.config.cc_keys_to_console.os.path.exists")
    @mock.patch("cloudinit.config.cc_keys_to_console.subp.subp")
    @pytest.mark.parametrize(
        "cfg,subp_called",
        [
            ({}, True),  # Default to emitting keys
            ({"ssh": {}}, True),  # Default even if we have the parent key
            (
                {"ssh": {"emit_keys_to_console": True}},
                True,
            ),  # Explicitly enabled
            ({"ssh": {"emit_keys_to_console": False}}, False),  # Disabled
        ],
    )
    def test_emit_keys_to_console_config(
        self, m_subp, m_path_exists, _m_multi_log, cfg, subp_called
    ):
        # Ensure we always find the helper
        m_path_exists.return_value = True
        m_subp.return_value = ("", "")

        cc_keys_to_console.handle("name", cfg, mock.Mock(), ())

        assert subp_called == (m_subp.call_count == 1)


class TestKeysToConsoleSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        (
            # Valid schemas are covered by meta examples tests in test_schema
            # Invalid schemas
            (
                {"ssh": {}},
                "Cloud config schema errors: ssh: 'emit_keys_to_console' is"
                " a required property",
            ),
            (  # Avoid common failure giving a string 'false' instead of false
                {"ssh": {"emit_keys_to_console": "false"}},
                "Cloud config schema errors: ssh.emit_keys_to_console: 'false'"
                " is not of type 'boolean'",
            ),
            (
                {"ssh": {"noextraprop": False, "emit_keys_to_console": False}},
                re.escape(
                    "Cloud config schema errors: ssh: Additional properties"
                    " are not allowed ('noextraprop' was unexpected)"
                ),
            ),
            (  # Avoid common failure giving a string 'false' instead of false
                {"ssh": {"emit_keys_to_console": "false"}},
                "Cloud config schema errors: ssh.emit_keys_to_console: 'false'"
                " is not of type 'boolean'",
            ),
            (  # Avoid common failure giving a string 'false' instead of false
                {"ssh_key_console_blacklist": False},
                "Cloud config schema errors: ssh_key_console_blacklist: False"
                " is not of type 'array'",
            ),
            (  # Avoid common failure giving a string 'false' instead of false
                {"ssh_key_console_blacklist": [1]},
                "Cloud config schema errors: ssh_key_console_blacklist.0: 1 is"
                " not of type 'string'",
            ),
            (  # Avoid common failure giving a string 'false' instead of false
                {"ssh_key_console_blacklist": [1]},
                "Cloud config schema errors: ssh_key_console_blacklist.0: 1 is"
                " not of type 'string'",
            ),
            (  # Avoid common failure giving a string 'false' instead of false
                {"ssh_fp_console_blacklist": None},
                "Cloud config schema errors: ssh_fp_console_blacklist: None"
                " is not of type 'array'",
            ),
            (  # Avoid common failure giving a string 'false' instead of false
                {"ssh_fp_console_blacklist": [1]},
                "Cloud config schema errors: ssh_fp_console_blacklist.0: 1 is"
                " not of type 'string'",
            ),
            (  # Avoid common failure giving a string 'false' instead of false
                {"ssh_fp_console_blacklist": [1]},
                "Cloud config schema errors: ssh_fp_console_blacklist.0: 1 is"
                " not of type 'string'",
            ),
        ),
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        """Assert expected schema validation and error messages."""
        # New-style schema $defs exist in config/cloud-init-schema*.json
        schema = get_schema()
        with pytest.raises(SchemaValidationError, match=error_msg):
            validate_cloudconfig_schema(config, schema, strict=True)
