# This file is part of cloud-init. See LICENSE file for license information.
import re
import tempfile

import pytest

from cloudinit import subp, util
from cloudinit.config.cc_bootcmd import handle
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import CiTestCase, mock, skipUnlessJsonSchema
from tests.unittests.util import get_cloud


class FakeExtendedTempFile:
    def __init__(self, suffix):
        self.suffix = suffix
        self.handle = tempfile.NamedTemporaryFile(
            prefix="ci-%s." % self.__class__.__name__, delete=False
        )

    def __enter__(self):
        return self.handle

    def __exit__(self, exc_type, exc_value, traceback):
        self.handle.close()
        util.del_file(self.handle.name)


class TestBootcmd(CiTestCase):

    with_logs = True

    _etmpfile_path = (
        "cloudinit.config.cc_bootcmd.temp_utils.ExtendedTemporaryFile"
    )

    def setUp(self):
        super(TestBootcmd, self).setUp()
        self.subp = subp.subp
        self.new_root = self.tmp_dir()

    def test_handler_skip_if_no_bootcmd(self):
        """When the provided config doesn't contain bootcmd, skip it."""
        cfg = {}
        mycloud = get_cloud()
        handle("notimportant", cfg, mycloud, None)
        self.assertIn(
            "Skipping module named notimportant, no 'bootcmd' key",
            self.logs.getvalue(),
        )

    def test_handler_invalid_command_set(self):
        """Commands which can't be converted to shell will raise errors."""
        invalid_config = {"bootcmd": 1}
        cc = get_cloud()
        with self.assertRaises(TypeError) as context_manager:
            handle("cc_bootcmd", invalid_config, cc, [])
        self.assertIn("Failed to shellify bootcmd", self.logs.getvalue())
        self.assertEqual(
            "Input to shellify was type 'int'. Expected list or tuple.",
            str(context_manager.exception),
        )

        invalid_config = {
            "bootcmd": ["ls /", 20, ["wget", "http://stuff/blah"], {"a": "n"}]
        }
        cc = get_cloud()
        with self.assertRaises(TypeError) as context_manager:
            handle("cc_bootcmd", invalid_config, cc, [])
        logs = self.logs.getvalue()
        self.assertIn("Failed to shellify", logs)
        self.assertEqual(
            "Unable to shellify type 'int'. Expected list, string, tuple. "
            "Got: 20",
            str(context_manager.exception),
        )

    def test_handler_creates_and_runs_bootcmd_script_with_instance_id(self):
        """Valid schema runs a bootcmd script with INSTANCE_ID in the env."""
        cc = get_cloud()
        out_file = self.tmp_path("bootcmd.out", self.new_root)
        my_id = "b6ea0f59-e27d-49c6-9f87-79f19765a425"
        valid_config = {
            "bootcmd": ["echo {0} $INSTANCE_ID > {1}".format(my_id, out_file)]
        }

        with mock.patch(self._etmpfile_path, FakeExtendedTempFile):
            with self.allow_subp(["/bin/sh"]):
                handle("cc_bootcmd", valid_config, cc, [])
        self.assertEqual(
            my_id + " iid-datasource-none\n", util.load_text_file(out_file)
        )

    def test_handler_runs_bootcmd_script_with_error(self):
        """When a valid script generates an error, that error is raised."""
        cc = get_cloud()
        valid_config = {"bootcmd": ["exit 1"]}  # Script with error

        with mock.patch(self._etmpfile_path, FakeExtendedTempFile):
            with self.allow_subp(["/bin/sh"]):
                with self.assertRaises(subp.ProcessExecutionError) as ctxt:
                    handle("does-not-matter", valid_config, cc, [])
        self.assertIn(
            "Unexpected error while running command.\nCommand: ['/bin/sh',",
            str(ctxt.exception),
        )
        self.assertIn(
            "Failed to run bootcmd module does-not-matter",
            self.logs.getvalue(),
        )


@skipUnlessJsonSchema()
class TestBootCMDSchema:
    """Directly test schema rather than through handle."""

    @pytest.mark.parametrize(
        "config, error_msg",
        (
            # Valid schemas tested by meta.examples in test_schema
            # Invalid schemas
            (
                {"bootcmd": 1},
                "Cloud config schema errors: bootcmd: 1 is not of type"
                " 'array'",
            ),
            ({"bootcmd": []}, re.escape("bootcmd: [] is too short")),
            (
                {"bootcmd": []},
                re.escape(
                    "Cloud config schema errors: bootcmd: [] is too short"
                ),
            ),
            (
                {
                    "bootcmd": [
                        "ls /",
                        20,
                        ["wget", "http://stuff/blah"],
                        {"a": "n"},
                    ]
                },
                "Cloud config schema errors: bootcmd.1: 20 is not of type"
                " 'array', bootcmd.1: 20 is not of type 'string', bootcmd.3:"
                " {'a': 'n'} is not of type 'array'",
            ),
        ),
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        """Assert expected schema validation and error messages."""
        # New-style schema $defs exist in config/cloud-init-schema*.json
        schema = get_schema()
        with pytest.raises(SchemaValidationError, match=error_msg):
            validate_cloudconfig_schema(config, schema, strict=True)
