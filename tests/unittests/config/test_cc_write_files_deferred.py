# This file is part of cloud-init. See LICENSE file for license information.

import logging
import shutil
import tempfile

import pytest

from cloudinit import util
from cloudinit.config.cc_write_files_deferred import handle
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import (
    FilesystemMockingTestCase,
    skipUnlessJsonSchema,
)

LOG = logging.getLogger(__name__)


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
        handle("cc_write_files_deferred", config, cc, [])
        self.assertEqual(util.load_text_file("/tmp/deferred.file"), expected)
        with self.assertRaises(FileNotFoundError):
            util.load_text_file("/tmp/not_deferred.file")


class TestWriteFilesDeferredSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        [
            # Allow undocumented keys client keys without error
            (
                {"write_files": [{"defer": "no"}]},
                "write_files.0.defer: 'no' is not of type 'boolean'",
            ),
        ],
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        with pytest.raises(SchemaValidationError, match=error_msg):
            validate_cloudconfig_schema(config, get_schema(), strict=True)
