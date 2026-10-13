# This file is part of cloud-init. See LICENSE file for license information.

"""Tests cc_apt_pipelining handler"""

import re
from unittest import mock

import pytest

import cloudinit.config.cc_apt_pipelining as cc_apt_pipelining
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import skipUnlessJsonSchema


class TestAptPipelining:
    @mock.patch("cloudinit.config.cc_apt_pipelining.util.write_file")
    def test_not_disabled_by_default(self, m_write_file):
        """ensure that default behaviour is to not disable pipelining"""
        cc_apt_pipelining.handle("foo", {}, None, None)
        assert 0 == m_write_file.call_count

    @mock.patch("cloudinit.config.cc_apt_pipelining.util.write_file")
    def test_false_disables_pipelining(self, m_write_file):
        """ensure that pipelining can be disabled with correct config"""
        cc_apt_pipelining.handle(
            "foo", {"apt_pipelining": "false"}, None, None
        )
        assert 1 == m_write_file.call_count
        args, _ = m_write_file.call_args
        assert cc_apt_pipelining.DEFAULT_FILE == args[0]
        assert 'Pipeline-Depth "0"' in args[1]

    @pytest.mark.usefixtures("clear_deprecation_log")
    @mock.patch("cloudinit.config.cc_apt_pipelining.util.write_file")
    def test_deprecate_module_warning(self, m_write_file, caplog):
        """Assert warning is logged for deprecated module."""
        cc_apt_pipelining.handle(
            "foo", {"apt_pipelining": "false"}, None, None
        )
        assert "Module cc_apt_pipelining is deprecated in" in caplog.text
        assert "deprecat" in caplog.text

    @pytest.mark.usefixtures("clear_deprecation_log")
    @mock.patch("cloudinit.config.cc_apt_pipelining.util.write_file")
    def test_no_deprecation_without_config_key(self, m_write_file, caplog):
        """Assert no warning is logged when key is absent from config."""
        cc_apt_pipelining.handle("foo", {}, None, None)
        assert "deprecat" not in caplog.text

    @pytest.mark.parametrize(
        "config, error_msg",
        (
            # Valid schemas
            ({}, None),
            # Valid, yet deprecated schemas
            ({"apt_pipelining": 1}, "Deprecated in version"),
            ({"apt_pipelining": True}, "Deprecated in version"),
            ({"apt_pipelining": False}, "Deprecated in version"),
            ({"apt_pipelining": "os"}, "Deprecated in version"),
            (
                {"apt_pipelining": 5},
                re.escape(
                    "Cloud config schema deprecations: apt_pipelining:  "
                    "Deprecated in version 26.3. The apt_pipelining module "
                    "is deprecated and scheduled to be removed in 31.3."
                ),
            ),
            # Invalid schemas
            ({"apt_pipelining": "none"}, "Deprecated in version"),
            ({"apt_pipelining": "unchanged"}, "Deprecated in version"),
            (
                {"apt_pipelining": "bogus"},
                re.escape(
                    "Cloud config schema errors: apt_pipelining: 'bogus' is"
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
