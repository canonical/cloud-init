# This file is part of cloud-init. See LICENSE file for license information.

import re
from unittest import mock

import pytest

from cloudinit import subp
from cloudinit.config import cc_spacewalk
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import skipUnlessJsonSchema
from tests.unittests.util import get_cloud


class TestSpacewalk:
    space_cfg = {
        "spacewalk": {
            "server": "localhost",
            "profile_name": "test",
        }
    }

    @mock.patch("cloudinit.config.cc_spacewalk.subp.subp")
    def test_not_is_registered(self, mock_subp):
        mock_subp.side_effect = subp.ProcessExecutionError(exit_code=1)
        assert cc_spacewalk.is_registered() is False

    @mock.patch("cloudinit.config.cc_spacewalk.subp.subp")
    def test_is_registered(self, mock_subp):
        mock_subp.side_effect = None
        assert cc_spacewalk.is_registered() is True

    @mock.patch("cloudinit.config.cc_spacewalk.subp.subp")
    def test_do_register(self, mock_subp):
        cc_spacewalk.do_register(**self.space_cfg["spacewalk"])
        mock_subp.assert_called_with(
            [
                "rhnreg_ks",
                "--serverUrl",
                "https://localhost/XMLRPC",
                "--profilename",
                "test",
                "--sslCACert",
                cc_spacewalk.def_ca_cert_path,
            ],
            capture=False,
        )


@pytest.mark.usefixtures("clear_deprecation_log")
class TestSpacewalkSchema:
    """Directly test schema rather than through handle."""

    @pytest.mark.parametrize(
        "config, error_msg",
        (
            # Valid, yet deprecated schema
            (
                {"spacewalk": {"server": "localhost"}},
                re.escape(
                    "Cloud config schema deprecations: spacewalk:  "
                    "Deprecated in version 26.2. The spacewalk module is "
                    "deprecated and will be removed in a future release."
                ),
            ),
        ),
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        """Assert expected schema validation and error messages."""
        schema = get_schema()
        with pytest.raises(SchemaValidationError, match=error_msg):
            validate_cloudconfig_schema(config, schema, strict=True)

    @mock.patch("cloudinit.config.cc_spacewalk.subp.subp")
    @mock.patch("cloudinit.config.cc_spacewalk.is_registered")
    def test_deprecate_module_warning(
        self, m_is_registered, m_subp, caplog
    ):
        """Assert warning is logged for deprecated module."""
        cloud = get_cloud("fedora")
        m_is_registered.return_value = True
        cc_spacewalk.handle(
            "cc_spacewalk", {"spacewalk": {"server": "localhost"}}, cloud, []
        )
        assert "Module cc_spacewalk is deprecated in" in caplog.text
        assert "deprecat" in caplog.text
