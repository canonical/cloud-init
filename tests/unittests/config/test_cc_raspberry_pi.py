# This file is part of cloud-init. See LICENSE file for license information.

import pytest

from cloudinit.config.cc_raspberry_pi import (
    ENABLE_RPI_CONNECT_KEY,
    RPI_BASE_KEY,
    RPI_INTERFACES_KEY,
)
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import skipUnlessJsonSchema


@skipUnlessJsonSchema()
class TestCCRPiSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        [
            (
                {
                    RPI_BASE_KEY: {
                        RPI_INTERFACES_KEY: {"spi": True, "i2c": False}
                    }
                },
                None,
            ),
            (
                {RPI_BASE_KEY: {RPI_INTERFACES_KEY: {"spi": "true"}}},
                "'true' is not of type 'boolean'",
            ),
            (
                {
                    RPI_BASE_KEY: {
                        RPI_INTERFACES_KEY: {
                            "serial": {"console": True, "hardware": False}
                        }
                    }
                },
                None,
            ),
            (
                {
                    RPI_BASE_KEY: {
                        RPI_INTERFACES_KEY: {"serial": {"console": 123}}
                    }
                },
                "123 is not of type 'boolean'",
            ),
            ({RPI_BASE_KEY: {ENABLE_RPI_CONNECT_KEY: True}}, None),
            (
                {RPI_BASE_KEY: {ENABLE_RPI_CONNECT_KEY: "true"}},
                "'true' is not of type 'boolean'",
            ),
        ],
    )
    def test_schema_validation(self, config, error_msg):
        if error_msg is None:
            validate_cloudconfig_schema(config, get_schema(), strict=True)
        else:
            with pytest.raises(SchemaValidationError, match=error_msg):
                validate_cloudconfig_schema(config, get_schema(), strict=True)
