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
from tests.unittests.helpers import (
    SCHEMA_EMPTY_ERROR,
    mock,
    skipUnlessJsonSchema,
)
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


@pytest.mark.usefixtures("fake_filesystem")
class TestBootcmd:

    _etmpfile_path = (
        "cloudinit.config.cc_bootcmd.temp_utils.ExtendedTemporaryFile"
    )

    def test_handler_skip_if_no_bootcmd(self, caplog):
        """When the provided config doesn't contain bootcmd, skip it."""
        cfg: dict[str, object] = {}
        mycloud = get_cloud()
        handle("notimportant", cfg, mycloud, [])
        assert (
            "Skipping module named notimportant, no 'bootcmd' key"
            in caplog.text
        )

    def test_handler_invalid_command_set(self, caplog):
        """Commands which can't be converted to shell will raise errors."""
        invalid_config_value = {"bootcmd": 1}
        cc = get_cloud()
        with pytest.raises(
            TypeError,
            match="Input to shellify was type 'int'. Expected list or tuple.",
        ):
            handle("cc_bootcmd", invalid_config_value, cc, [])
        assert "Failed to shellify bootcmd" in caplog.text

        invalid_config_items = {
            "bootcmd": ["ls /", 20, ["wcurl", "http://stuff/blah"], {"a": "n"}]
        }
        cc = get_cloud()
        with pytest.raises(
            TypeError,
            match="Unable to shellify type 'int'. Expected list, string, "
            "tuple. Got: 20",
        ):
            handle("cc_bootcmd", invalid_config_items, cc, [])
        assert "Failed to shellify" in caplog.text

    @pytest.mark.allow_subp_for("/bin/sh")
    def test_handler_runs_bootcmd_script_with_error(self, caplog):
        """When a valid script generates an error, that error is raised."""
        cc = get_cloud()
        valid_config = {"bootcmd": ["exit 1"]}  # Script with error

        with mock.patch(self._etmpfile_path, FakeExtendedTempFile):
            with pytest.raises(
                subp.ProcessExecutionError,
                match=(
                    r"Unexpected error while running command.\n"
                    r"Command: \['/bin/sh',"
                ),
            ):
                handle("does-not-matter", valid_config, cc, [])
        assert "Failed to run bootcmd module does-not-matter" in caplog.text


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
            (
                {"bootcmd": []},
                re.escape("bootcmd: [] ") + SCHEMA_EMPTY_ERROR,
            ),
            (
                {"bootcmd": []},
                re.escape("Cloud config schema errors: bootcmd: [] ")
                + SCHEMA_EMPTY_ERROR,
            ),
            (
                {
                    "bootcmd": [
                        "ls /",
                        20,
                        ["wcurl", "http://stuff/blah"],
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
