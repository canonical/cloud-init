# This file is part of cloud-init. See LICENSE file for license information.
import logging
import os
import stat
from unittest.mock import patch

import pytest

from cloudinit import helpers, subp, util
from cloudinit.config.cc_runcmd import handle
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import (
    FilesystemMockingTestCase,
    skipUnlessJsonSchema,
)
from tests.unittests.util import get_cloud

LOG = logging.getLogger(__name__)


@patch("cloudinit.util.wait_for_snap_seeded")
class TestRuncmd(FilesystemMockingTestCase):

    with_logs = True

    def setUp(self):
        super(TestRuncmd, self).setUp()
        self.subp = subp.subp
        self.new_root = self.tmp_dir()
        self.patchUtils(self.new_root)
        self.paths = helpers.Paths({"scripts": self.new_root})

    def test_handler_skip_if_no_runcmd(self, wait_for_snap_seeded):
        """When the provided config doesn't contain runcmd, skip it."""
        cfg = {}
        mycloud = get_cloud(paths=self.paths)
        handle("notimportant", cfg, mycloud, None)
        self.assertIn(
            "Skipping module named notimportant, no 'runcmd' key",
            self.logs.getvalue(),
        )
        wait_for_snap_seeded.assert_not_called()

    @patch("cloudinit.util.shellify")
    def test_runcmd_shellify_fails(self, cls, wait_for_snap_seeded):
        """When shellify fails throw exception"""
        cls.side_effect = TypeError("patched shellify")
        valid_config = {"runcmd": ["echo 42"]}
        cc = get_cloud(paths=self.paths)
        with self.assertRaises(TypeError) as cm:
            with self.allow_subp(["/bin/sh"]):
                handle("cc_runcmd", valid_config, cc, None)
        self.assertIn("Failed to shellify", str(cm.exception))
        wait_for_snap_seeded.assert_called_once_with()

    def test_handler_invalid_command_set(self, wait_for_snap_seeded):
        """Commands which can't be converted to shell will raise errors."""
        invalid_config = {"runcmd": 1}
        cc = get_cloud(paths=self.paths)
        with self.assertRaises(TypeError) as cm:
            handle("cc_runcmd", invalid_config, cc, [])
        self.assertIn(
            "Failed to shellify 1 into file"
            " /var/lib/cloud/instances/iid-datasource-none/scripts/runcmd",
            str(cm.exception),
        )
        wait_for_snap_seeded.assert_called_once_with()

    def test_handler_write_valid_runcmd_schema_to_file(
        self, wait_for_snap_seeded
    ):
        """Valid runcmd schema is written to a runcmd shell script."""
        valid_config = {"runcmd": [["ls", "/"]]}
        cc = get_cloud(paths=self.paths)
        handle("cc_runcmd", valid_config, cc, [])
        runcmd_file = os.path.join(
            self.new_root,
            "var/lib/cloud/instances/iid-datasource-none/scripts/runcmd",
        )
        self.assertEqual("#!/bin/sh\n'ls' '/'\n", util.load_file(runcmd_file))
        file_stat = os.stat(runcmd_file)
        self.assertEqual(0o700, stat.S_IMODE(file_stat.st_mode))
        wait_for_snap_seeded.assert_called_once_with()


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
            ({"runcmd": []}, r"runcmd: \[\] is too short"),
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
