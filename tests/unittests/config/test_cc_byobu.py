# This file is part of cloud-init. See LICENSE file for license information.

import re

import pytest

from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import skipUnlessJsonSchema


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


# vi: ts=4 expandtab
