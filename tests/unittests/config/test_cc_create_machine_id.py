# This file is part of cloud-init. See LICENSE file for license information.
import pytest

from cloudinit import subp
from cloudinit.config import cc_create_machine_id
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import CiTestCase, mock, skipUnlessJsonSchema

NL = "\n"
# Module path used in mocks
MPATH = "cloudinit.config.cc_create_machine_id"


class FakeCloud(object):
    def __init__(self, distro):
        self.distro = distro


class TestCreateMachineID(CiTestCase):
    with_logs = True
    allowed_subp = [CiTestCase.SUBP_SHELL_TRUE]

    def setUp(self):
        super(TestCreateMachineID, self).setUp()
        self.tmp = self.tmp_dir()

#    def test_remove_machine_id_failed(self):
#        """OSError when machine-id gets removed"""
#        machine_id_files = frozenset(["/etc/machine-id"])
#
#        with self.assertRaises(RuntimeError) as context_mgr:
#            cc_create_machine_id.remove_machine_id(machine_id_files)
#        self.assertIn(
#            "Failed to remove file '/etc/machine-id'",
#            str(context_mgr.exception),
#        )

    @mock.patch("%s.subp.subp" % MPATH)
    def test_create_machine_id_failed(self, m_subp):
        """"""
        m_subp.side_effect = subp.ProcessExecutionError("some exec error")
        with self.assertRaises(subp.ProcessExecutionError) as context_manager:
            cc_create_machine_id.create_machine_id()
        self.assertEqual(
            "Unexpected error while running command.\n"
            "Command: -\nExit code: -\nReason: -\n"
            "Stdout: some exec error\n"
            "Stderr: -",
            str(context_manager.exception),
        )
        self.assertIn(
            "WARNING: Could not create machine-id:\n", self.logs.getvalue()
        )


class TestCreateMachineIDSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        [
            # Valid schemas
            (
                {"create_machine_id": True},
                None,
            ),
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
