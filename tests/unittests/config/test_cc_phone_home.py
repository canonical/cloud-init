import pytest

from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import skipUnlessJsonSchema


class TestPhoneHomeSchema:
    @pytest.mark.parametrize(
        "config",
        [
            # phone_home definition with url
            {"phone_home": {"post": ["pub_key_dsa"]}},
            # post using string other than "all"
            {"phone_home": {"url": "test_url", "post": "pub_key_dsa"}},
            # post using list with misspelled entry
            {"phone_home": {"url": "test_url", "post": ["pub_kye_dsa"]}},
        ],
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config):
        with pytest.raises(SchemaValidationError):
            validate_cloudconfig_schema(config, get_schema(), strict=True)
