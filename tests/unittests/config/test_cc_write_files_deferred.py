# This file is part of cloud-init. See LICENSE file for license information.

import logging
from unittest import mock

import pytest

from cloudinit import util
from cloudinit.config.cc_write_files_deferred import handle
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import skipUnlessJsonSchema
from tests.unittests.util import get_cloud

LOG = logging.getLogger(__name__)


@pytest.mark.usefixtures("fake_filesystem")
class TestWriteFilesDeferred:

    USER = "root"

    @mock.patch("cloudinit.config.cc_write_files.util.chownbyname")
    def test_filtering_deferred_files(self, m_chownbyname):
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
        cc = get_cloud("ubuntu")
        # fake_filesytem's tree is owned by $USER:$USER
        with mock.patch.object(
            cc.distro, "default_owner", f"{self.USER}:{self.USER}"
        ):
            handle("cc_write_files_deferred", config, cc, [])
        assert util.load_text_file("/tmp/deferred.file") == expected
        with pytest.raises(FileNotFoundError):
            util.load_text_file("/tmp/not_deferred.file")
        assert [
            mock.call(mock.ANY, self.USER, self.USER)
        ] == m_chownbyname.call_args_list


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
