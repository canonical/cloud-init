# This file is part of cloud-init. See LICENSE file for license information.
import pytest

from cloudinit import helpers, util
from cloudinit.config import cc_wireguard
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import (
    CiTestCase,
    FilesystemMockingTestCase,
    mock,
    skipUnlessJsonSchema,
)


class TestSupplementalSchemaValidation(CiTestCase):
    def test_error_on_missing_keys(self):
        """ValueError raised reporting any missing required wg:interfaces keys"""
        cfg = {}
        match = (
            r"Invalid wireguard interface configuration:\\n"
            " Missing required wg:interfaces keys: config_path, content, name"
        )
        with self.assertRaisesRegex(ValueError, match):
            cc_wireguard.supplemental_schema_validation(cfg)

    def test_error_on_non_string_values(self):
        """ValueError raised for any values expected as string type."""
        cfg = {"name": 1, "config_path": 2, "content": 3}
        errors = [
            "Expected a str for wg:interfaces:config_path. Found: 2",
            "Expected a str for wg:interfaces:content. Found: 3",
            "Expected a str for wg:interfaces:name. Found: 1",
        ]
        with self.assertRaises(ValueError) as context_mgr:
            cc_wireguard.supplemental_schema_validation(cfg)
        error_msg = str(context_mgr.exception)
        for error in errors:
            self.assertIn(error, error_msg)


class TestWireguardSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        [
            # Allow empty wireguard config
            ({"wireguard": None}, None),
        ],
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        if error_msg is not None:
            with pytest.raises(SchemaValidationError, match=error_msg):
                validate_cloudconfig_schema(config, get_schema(), strict=True)
        else:
            validate_cloudconfig_schema(config, get_schema(), strict=True)


# vi: ts=4 expandtab
