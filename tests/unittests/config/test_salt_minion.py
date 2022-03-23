# This file is part of cloud-init. See LICENSE file for license information.
import pytest

from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import skipUnlessJsonSchema


@skipUnlessJsonSchema()
class TestSaltMinionSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        (
            ({"salt_minion": {"conf": {"any": "thing"}}}, None),
            ({"salt_minion": {"grains": {"any": "thing"}}}, None),
            (
                {"salt_minion": {"invalid": "key"}},
                "Additional properties are not allowed",
            ),
            ({"salt_minion": {"conf": "a"}}, "'a' is not of type 'object'"),
            ({"salt_minion": {"grains": "a"}}, "'a' is not of type 'object'"),
        ),
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        if error_msg is None:
            validate_cloudconfig_schema(config, get_schema(), strict=True)
        else:
            with pytest.raises(SchemaValidationError, match=error_msg):
                validate_cloudconfig_schema(config, get_schema(), strict=True)
