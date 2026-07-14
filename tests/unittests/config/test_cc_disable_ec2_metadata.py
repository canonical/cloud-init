# This file is part of cloud-init. See LICENSE file for license information.

"""Tests cc_disable_ec2_metadata handler"""


import re
from unittest import mock

import pytest

import cloudinit.config.cc_disable_ec2_metadata as ec2_meta
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import skipUnlessJsonSchema

DISABLE_CFG = {"disable_ec2_metadata": "true"}


class TestEC2MetadataRoute:
    @mock.patch("cloudinit.config.cc_disable_ec2_metadata.subp.which")
    @mock.patch("cloudinit.config.cc_disable_ec2_metadata.subp.subp")
    def test_disable_ifconfig(self, m_subp, m_which):
        """Set the route if ifconfig command is available"""
        m_which.side_effect = lambda x: x if x == "ifconfig" else None
        ec2_meta.handle("foo", DISABLE_CFG, mock.MagicMock(), [])
        m_subp.assert_called_with(
            ["route", "add", "-host", "169.254.169.254", "reject"],
            capture=False,
        )

    @mock.patch("cloudinit.config.cc_disable_ec2_metadata.subp.which")
    @mock.patch("cloudinit.config.cc_disable_ec2_metadata.subp.subp")
    def test_disable_ip(self, m_subp, m_which):
        """Set the route if ip command is available"""
        m_which.side_effect = lambda x: x if x == "ip" else None
        ec2_meta.handle("foo", DISABLE_CFG, mock.MagicMock(), [])
        m_subp.assert_called_with(
            ["ip", "route", "add", "prohibit", "169.254.169.254"],
            capture=False,
        )

    @mock.patch("cloudinit.config.cc_disable_ec2_metadata.subp.which")
    @mock.patch("cloudinit.config.cc_disable_ec2_metadata.subp.subp")
    def test_disable_no_tool(self, m_subp, m_which):
        """Log error when neither route nor ip commands are available"""
        m_which.return_value = None  # Find neither ifconfig nor ip
        ec2_meta.handle("foo", DISABLE_CFG, mock.MagicMock(), [])
        assert [
            mock.call("ip"),
            mock.call("ifconfig"),
        ] == m_which.call_args_list
        m_subp.assert_not_called()


@pytest.mark.usefixtures("clear_deprecation_log")
@skipUnlessJsonSchema()
class TestDisableEc2MetadataSchema:
    """Directly test schema rather than through handle."""

    @pytest.mark.parametrize(
        "config, error_msg",
        (
            # Valid, yet deprecated schema
            (
                {"disable_ec2_metadata": True},
                re.escape(
                    "Cloud config schema deprecations: "
                    "disable_ec2_metadata:  Deprecated in version 26.2. "
                    "The disable_ec2_metadata module is deprecated and will "
                    "be removed in a future release."
                ),
            ),
            # Invalid schemas
            (
                {"disable_ec2_metadata": 1},
                "disable_ec2_metadata: 1 is not of type 'boolean'",
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


@pytest.mark.usefixtures("clear_deprecation_log")
class TestDisableEc2MetadataDeprecation:
    @mock.patch("cloudinit.config.cc_disable_ec2_metadata.subp.which")
    @mock.patch("cloudinit.config.cc_disable_ec2_metadata.subp.subp")
    def test_deprecate_module_warning(self, m_subp, m_which, caplog):
        """Assert warning is logged for deprecated module."""
        m_which.side_effect = lambda x: x if x == "ip" else None
        ec2_meta.handle("foo", {"disable_ec2_metadata": True}, mock.MagicMock(), [])
        assert "Module cc_disable_ec2_metadata is deprecated in" in caplog.text
        assert "deprecat" in caplog.text
