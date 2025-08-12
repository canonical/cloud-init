# This file is part of cloud-init. See LICENSE file for license information.
import logging
import os
import stat
from typing import Any, Dict
from unittest.mock import patch

import pytest

from cloudinit import helpers, util
from cloudinit.config.cc_runcmd import handle
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import SCHEMA_EMPTY_ERROR, skipUnlessJsonSchema
from tests.unittests.util import get_cloud

LOG = logging.getLogger(__name__)


@pytest.fixture
def cloud(tmp_path):
    paths = helpers.Paths({"scripts": str(tmp_path)})
    return get_cloud(paths=paths)


@pytest.mark.usefixtures("fake_filesystem")
class TestRuncmd:
    # self.paths = helpers.Paths({"scripts": self.new_root})

    def test_handler_skip_if_no_runcmd(self, caplog, cloud):
        """When the provided config doesn't contain runcmd, skip it."""
        cfg: Dict[str, Any] = {}
        handle("notimportant", cfg, cloud, [])
        assert (
            "Skipping module named notimportant, no 'runcmd' key"
            in caplog.text
        )

    @pytest.mark.allow_subp_for("/bin/sh")
    @patch("cloudinit.util.shellify")
    def test_runcmd_shellify_fails(self, cls, cloud):
        """When shellify fails throw exception"""
        cls.side_effect = TypeError("patched shellify")
        valid_config = {"runcmd": ["echo 42"]}
        with pytest.raises(TypeError, match="Failed to shellify"):
            handle("cc_runcmd", valid_config, cloud, [])

    def test_handler_invalid_command_set(self, cloud):
        """Commands which can't be converted to shell will raise errors."""
        invalid_config = {"runcmd": 1}
        with pytest.raises(
            TypeError,
            match="Failed to shellify 1 into file"
            " /var/lib/cloud/instances/iid-datasource-none/scripts/runcmd",
        ):
            handle("cc_runcmd", invalid_config, cloud, [])

    def test_handler_write_valid_runcmd_schema_to_file(self, cloud, tmp_path):
        """Valid runcmd schema is written to a runcmd shell script."""
        valid_config = {"runcmd": [["ls", "/"]]}
        handle("cc_runcmd", valid_config, cloud, [])
        runcmd_file = os.path.join(
            tmp_path,
            "var/lib/cloud/instances/iid-datasource-none/scripts/runcmd",
        )
        assert "#!/bin/sh\n'ls' '/'\n" == util.load_text_file(runcmd_file)
        file_stat = os.stat(runcmd_file)
        assert 0o700 == stat.S_IMODE(file_stat.st_mode)


@skipUnlessJsonSchema()
class TestRunCmdSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        (
            # Ensure duplicate commands are valid
            ({"runcmd": [["echo", "bye"], ["echo", "bye"]]}, None),
            ({"runcmd": ["echo bye", "echo bye"]}, None),
            # Invalid schemas
            ({"runcmd": 1}, "1 is not of type 'array'"),
            ({"runcmd": []}, rf"runcmd: \[\] {SCHEMA_EMPTY_ERROR}"),
            (
                {
                    "runcmd": [
                        "ls /",
                        20,
                        ["wget", "http://stuff/blah"],
                        {"a": "n"},
                    ]
                },
                "",
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
