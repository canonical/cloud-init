import re
import pytest

from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import (
    skipUnlessJsonSchema,
)


@skipUnlessJsonSchema()
class TestHttpScriptsSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        (
            ({"http_scripts": [{"url": "http://example.com"}]}, None),
            (
                {
                    "http_scripts": [
                        {"url": "http://example.com"},
                        {"url": "http://example.com"},
                    ]
                },
                None,
            ),
            (
                {
                    "http_scripts": [
                        {
                            "url": "http://example.com",
                            "environments": {
                                "ENV1": "value1",
                                "ENV2": "value2",
                            },
                        }
                    ]
                },
                None,
            ),
            # Invalid schemas
            (
                {"http_scripts": {"url": "http://example.com"}},
                re.escape(
                    "{'url': 'http://example.com'} is not of type 'array'"
                ),
            ),
            (
                {"http_scripts": [{}]},
                re.escape("http_scripts.0: 'url' is a required property"),
            ),
            (
                {
                    "http_scripts": [
                        {"environments": {"ENV1": "value1", "ENV2": "value2"}}
                    ]
                },
                re.escape("http_scripts.0: 'url' is a required property"),
            ),
            (
                {"http_scripts": [{"invalidprop": True}]},
                re.escape(
                    "Additional properties are not allowed ('invalidprop"
                ),
            ),
        ),
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        if error_msg is None:
            validate_cloudconfig_schema(config, get_schema(), strict=True)
        else:
            with pytest.raises(SchemaValidationError, match=error_msg):
                validate_cloudconfig_schema(config, get_schema(), strict=True)
