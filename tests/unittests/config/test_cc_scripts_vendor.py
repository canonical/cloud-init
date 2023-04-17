import pytest

from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import does_not_raise, skipUnlessJsonSchema


class TestScriptsVendorSchema:
    @pytest.mark.parametrize(
        "config, expectation",
        (
            ({"vendor_data": {"enabled": True}}, does_not_raise()),
            ({"vendor_data": {"enabled": False}}, does_not_raise()),
            (
                {"vendor_data": {"enabled": "yes"}},
                pytest.raises(
                    SchemaValidationError,
                    match=(
                        "Cloud config schema deprecations: "
                        "vendor_data.enabled:  Deprecated in version "
                        "22.3. Use of type string for this value is "
                        "deprecated. Use a boolean instead."
                    ),
                ),
            ),
        ),
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, expectation):
        """Assert expected schema validation and error messages."""
        # New-style schema $defs exist in config/cloud-init-schema*.json
        schema = get_schema()
        with expectation:
            validate_cloudconfig_schema(config, schema, strict=True)
