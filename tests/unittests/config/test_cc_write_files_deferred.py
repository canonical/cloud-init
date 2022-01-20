# This file is part of cloud-init. See LICENSE file for license information.

import shutil
import tempfile

from cloudinit import log as logging
from cloudinit import util
from cloudinit.config.cc_write_files_deferred import handle
from tests.unittests.helpers import (
    CiTestCase,
    FilesystemMockingTestCase,
    mock,
    skipUnlessJsonSchema,
)

from .test_cc_write_files import VALID_SCHEMA

LOG = logging.getLogger(__name__)


@skipUnlessJsonSchema()
@mock.patch("cloudinit.config.cc_write_files_deferred.write_files")
class TestWriteFilesDeferredSchema(CiTestCase):

    with_logs = True

    def test_schema_validation_warns_invalid_value(
        self, m_write_files_deferred
    ):
        """If 'defer' is defined, it must be of type 'bool'."""

        valid_config = {
            "write_files": [
                {**VALID_SCHEMA.get("write_files")[0], "defer": True}
            ]
        }

        invalid_config = {
            "write_files": [
                {**VALID_SCHEMA.get("write_files")[0], "defer": str("no")}
            ]
        }

        cc = self.tmp_cloud("ubuntu")
        handle("cc_write_files_deferred", valid_config, cc, LOG, [])
        self.assertNotIn(
            "Invalid cloud-config provided:", self.logs.getvalue()
        )
        handle("cc_write_files_deferred", invalid_config, cc, LOG, [])
        self.assertIn("Invalid cloud-config provided:", self.logs.getvalue())
        self.assertIn(
            "defer: 'no' is not of type 'boolean'", self.logs.getvalue()
        )


class TestWriteFilesDeferred(FilesystemMockingTestCase):

    with_logs = True

    def setUp(self):
        super(TestWriteFilesDeferred, self).setUp()
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def test_filtering_deferred_files(self):
        self.patchUtils(self.tmp)
        expected = "hello world\n"
        config = {
            "write_files": [
                {
                    "path": "/tmp/deferred.file",
                    "defer": True,
                    "content": expected,
                },
                {"path": "/tmp/not_deferred.file"},
            ]
        }
        cc = self.tmp_cloud("ubuntu")
        handle("cc_write_files_deferred", config, cc, LOG, [])
        self.assertEqual(util.load_file("/tmp/deferred.file"), expected)
        with self.assertRaises(FileNotFoundError):
            util.load_file("/tmp/not_deferred.file")


# vi: ts=4 expandtab
