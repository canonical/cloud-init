# This file is part of cloud-init. See LICENSE file for license information.
import re

import pytest

from cloudinit import subp
from cloudinit.config.cc_wireguard import (
    enable_wg,
    handle,
    readinessprobe,
    readinessprobe_command_validation,
    write_config,
)
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

# Module path used in mocks
MPATH = "cloudinit.config.cc_wireguard"


class FakeCloud(object):
    def __init__(self, distro):
        self.distro = distro


class TestWireguardSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        [
            # Allow empty wireguard config
            ({"wireguard": None}, None),
            #        (
            #                {
            #                    "wireguard": {
            #                        "invalidkey": 1,
            #                        "interfaces": [
            #                            {
            #                                "name": "wg0",
            #                                "config_path": "/etc/wireguard/wg0.conf",
            #                                "config": "this is a test"
            #                            }
            #                        ]
            #                    }
            #                },
            #                re.escape(
            #                    "wireguard.0: Additional properties are not allowed"
            #                    " ('invalidkey'"
            #                )
            #            )
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
