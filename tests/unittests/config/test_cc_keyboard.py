# This file is part of cloud-init. See LICENSE file for license information.

"""Tests cc_keyboard module"""

import re

import pytest

from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import skipUnlessJsonSchema


class TestKeyboard:
    @pytest.mark.parametrize(
        "config, error_msg",
        (
            # Valid schemas
            ({"keyboard": {"layout": "somestring"}}, None),
            # Invalid schemas
            (
                {"keyboard": {}},
                "Cloud config schema errors: keyboard: 'layout' is a"
                " required property",
            ),
            (
                {"keyboard": "bogus"},
                "Cloud config schema errors: keyboard: 'bogus' is not"
                " of type 'object'",
            ),
            (
                {"keyboard": {"layout": 1}},
                "Cloud config schema errors: keyboard.layout: 1 is not"
                " of type 'string'",
            ),
            (
                {"keyboard": {"layout": "somestr", "model": None}},
                "Cloud config schema errors: keyboard.model: None is not"
                " of type 'string'",
            ),
            (
                {"keyboard": {"layout": "somestr", "variant": [1]}},
                re.escape(
                    "Cloud config schema errors: keyboard.variant: [1] is"
                    " not of type 'string'"
                ),
            ),
            (
                {"keyboard": {"layout": "somestr", "options": {}}},
                "Cloud config schema errors: keyboard.options: {} is not"
                " of type 'string'",
            ),
            (
                {"keyboard": {"layout": "somestr", "extraprop": "somestr"}},
                re.escape(
                    "Cloud config schema errors: keyboard: Additional"
                    " properties are not allowed ('extraprop' was unexpected)"
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


# vi: ts=4 expandtab
