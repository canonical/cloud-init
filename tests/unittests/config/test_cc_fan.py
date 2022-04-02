# This file is part of cloud-init. See LICENSE file for license information.
"""Tests cc_fan module"""

import pytest

from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import skipUnlessJsonSchema


class TestFanSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        (
            ({"fan": {"config": ["a", "b"]}}, "is not of type 'string'"),
            (
                {"fan": {"config_path": "/a/b"}},
                "'config' is a required property",
            ),
        ),
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        """Assert expected schema validation and error messages."""
        schema = get_schema()
        if error_msg is None:
            validate_cloudconfig_schema(config, schema, strict=True)
        else:
            with pytest.raises(SchemaValidationError, match=error_msg):
                validate_cloudconfig_schema(config, schema, strict=True)
