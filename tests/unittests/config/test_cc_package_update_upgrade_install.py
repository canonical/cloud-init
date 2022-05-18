import pytest

from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import skipUnlessJsonSchema


class TestPackageUpdateUpgradeSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        [
            # packages list with single entry (2 required)
            ({"packages": ["p1", ["p2"]]}, ""),
            # packages list with three entries (2 required)
            ({"packages": ["p1", ["p2", "p3", "p4"]]}, ""),
            # empty packages list
            ({"packages": []}, "is too short"),
        ],
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        with pytest.raises(SchemaValidationError, match=error_msg):
            validate_cloudconfig_schema(config, get_schema(), strict=True)
