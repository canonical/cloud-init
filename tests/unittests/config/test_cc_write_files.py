# This file is part of cloud-init. See LICENSE file for license information.

import base64
import gzip
import io
import logging
import re
import shutil
import tempfile

import pytest
import responses

from cloudinit import util
from cloudinit.config.cc_write_files import decode_perms, handle, write_files
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import (
    SCHEMA_EMPTY_ERROR,
    CiTestCase,
    FilesystemMockingTestCase,
    skipUnlessJsonSchema,
)
from tests.unittests.util import get_cloud

LOG = logging.getLogger(__name__)

YAML_TEXT = """
write_files:
 - encoding: gzip
   content: !!binary |
     H4sIAIDb/U8C/1NW1E/KzNMvzuBKTc7IV8hIzcnJVyjPL8pJ4QIA6N+MVxsAAAA=
   path: /usr/bin/hello
   permissions: '0755'
 - content: !!binary |
     Zm9vYmFyCg==
   path: /wark
   permissions: '0755'
 - content: |
    hi mom line 1
    hi mom line 2
   path: /tmp/message
"""

YAML_CONTENT_EXPECTED = {
    "/usr/bin/hello": "#!/bin/sh\necho hello world\n",
    "/wark": "foobar\n",
    "/tmp/message": "hi mom line 1\nhi mom line 2\n",
}

VALID_SCHEMA = {
    "write_files": [
        {
            "append": False,
            "content": "a",
            "encoding": "gzip",
            "owner": "jeff",
            "path": "/some",
            "permissions": "0777",
        }
    ]
}


class TestWriteFiles(FilesystemMockingTestCase):

    with_logs = True
    owner = "root:root"

    def setUp(self):
        super(TestWriteFiles, self).setUp()
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def test_simple(self):
        self.patchUtils(self.tmp)
        expected = "hello world\n"
        filename = "/tmp/my.file"
        write_files(
            "test_simple",
            [{"content": expected, "path": filename}],
            self.owner,
        )
        self.assertEqual(util.load_text_file(filename), expected)

    def test_empty(self):
        self.patchUtils(self.tmp)
        filename = "/tmp/my.file"
        write_files(
            "test_empty",
            [{"path": filename}],
            self.owner,
        )
        self.assertEqual(util.load_text_file(filename), "")

    def test_append(self):
        self.patchUtils(self.tmp)
        existing = "hello "
        added = "world\n"
        expected = existing + added
        filename = "/tmp/append.file"
        util.write_file(filename, existing)
        write_files(
            "test_append",
            [{"content": added, "path": filename, "append": "true"}],
            self.owner,
        )
        self.assertEqual(util.load_text_file(filename), expected)

    def test_yaml_binary(self):
        self.patchUtils(self.tmp)
        data = util.load_yaml(YAML_TEXT)
        write_files("testname", data["write_files"], self.owner)
        for path, content in YAML_CONTENT_EXPECTED.items():
            self.assertEqual(util.load_text_file(path), content)

    def test_all_decodings(self):
        self.patchUtils(self.tmp)

        # build a 'files' array that has a dictionary of encodings
        # for 'gz', 'gzip', 'gz+base64' ...
        data = b"foobzr"
        utf8_valid = b"foobzr"
        utf8_invalid = b"ab\xaadef"
        files = []
        expected = []

        gz_aliases = ("gz", "gzip")
        gz_b64_aliases = ("gz+base64", "gzip+base64", "gz+b64", "gzip+b64")
        b64_aliases = ("base64", "b64")

        datum = (("utf8", utf8_valid), ("no-utf8", utf8_invalid))
        for name, data in datum:
            gz = (_gzip_bytes(data), gz_aliases)
            gz_b64 = (base64.b64encode(_gzip_bytes(data)), gz_b64_aliases)
            b64 = (base64.b64encode(data), b64_aliases)
            for content, aliases in (gz, gz_b64, b64):
                for enc in aliases:
                    path = "/tmp/file-%s-%s" % (name, enc)
                    cur = {
                        "content": content,
                        "path": path,
                        "encoding": enc,
                    }
                    files.append(cur)
                    expected.append((path, data))

        write_files("test_decoding", files, self.owner)

        for path, content in expected:
            self.assertEqual(util.load_binary_file(path), content)

        # make sure we actually wrote *some* files.
        flen_expected = len(gz_aliases + gz_b64_aliases + b64_aliases) * len(
            datum
        )
        self.assertEqual(len(expected), flen_expected)

    def test_handle_plain_text(self):
        self.patchUtils(self.tmp)
        file_path = "/tmp/file-text-plain"
        content = "asdf"
        cfg = {
            "write_files": [
                {
                    "content": content,
                    "path": file_path,
                    "encoding": "text/plain",
                    "defer": False,
                }
            ]
        }
        cc = get_cloud("ubuntu")
        handle("ignored", cfg, cc, [])
        assert content == util.load_text_file(file_path)
        self.assertNotIn(
            "Unknown encoding type text/plain", self.logs.getvalue()
        )

    def test_file_uri(self):
        self.patchUtils(self.tmp)
        src_path = "/tmp/file-uri"
        dst_path = "/tmp/file-uri-target"
        content = "asdf"
        util.write_file(src_path, content)
        cfg = {
            "write_files": [
                {
                    "source": {"uri": "file://" + src_path},
                    "path": dst_path,
                }
            ]
        }
        cc = get_cloud("ubuntu")
        handle("ignored", cfg, cc, [])
        self.assertEqual(
            util.load_text_file(src_path), util.load_text_file(dst_path)
        )

    @responses.activate
    def test_http_uri(self):
        self.patchUtils(self.tmp)
        path = "/tmp/http-uri-target"
        url = "http://hostname/path"
        content = "more asdf"
        responses.add(responses.GET, url, content)
        cfg = {
            "write_files": [
                {
                    "source": {
                        "uri": url,
                        "headers": {
                            "foo": "bar",
                            "blah": "blah",
                        },
                    },
                    "path": path,
                }
            ]
        }
        cc = get_cloud("ubuntu")
        handle("ignored", cfg, cc, [])
        self.assertEqual(content, util.load_text_file(path))

    def test_uri_fallback(self):
        self.patchUtils(self.tmp)
        src_path = "/tmp/INVALID"
        dst_path = "/tmp/uri-fallback-target"
        content = "asdf"
        util.del_file(src_path)
        cfg = {
            "write_files": [
                {
                    "source": {"uri": "file://" + src_path},
                    "content": content,
                    "encoding": "text/plain",
                    "path": dst_path,
                }
            ]
        }
        cc = get_cloud("ubuntu")
        handle("ignored", cfg, cc, [])
        self.assertEqual(content, util.load_text_file(dst_path))

    def test_deferred(self):
        self.patchUtils(self.tmp)
        file_path = "/tmp/deferred.file"
        config = {"write_files": [{"path": file_path, "defer": True}]}
        cc = get_cloud("ubuntu")
        handle("cc_write_file", config, cc, [])
        with self.assertRaises(FileNotFoundError):
            util.load_text_file(file_path)


class TestDecodePerms(CiTestCase):

    with_logs = True

    def test_none_returns_default(self):
        """If None is passed as perms, then default should be returned."""
        default = object()
        found = decode_perms(None, default)
        self.assertEqual(default, found)

    def test_integer(self):
        """A valid integer should return itself."""
        found = decode_perms(0o755, None)
        self.assertEqual(0o755, found)

    def test_valid_octal_string(self):
        """A string should be read as octal."""
        found = decode_perms("644", None)
        self.assertEqual(0o644, found)

    def test_invalid_octal_string_returns_default_and_warns(self):
        """A string with invalid octal should warn and return default."""
        found = decode_perms("999", None)
        self.assertIsNone(found)
        self.assertIn("WARNING: Undecodable", self.logs.getvalue())


def _gzip_bytes(data):
    buf = io.BytesIO()
    fp = None
    try:
        fp = gzip.GzipFile(fileobj=buf, mode="wb")
        fp.write(data)
        fp.close()
        return buf.getvalue()
    finally:
        if fp:
            fp.close()


class TestWriteFilesSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        [
            # Top-level write_files type validation
            ({"write_files": 1}, "write_files: 1 is not of type 'array'"),
            (
                {"write_files": []},
                re.escape("write_files: [] ") + SCHEMA_EMPTY_ERROR,
            ),
            (
                {"write_files": [{}]},
                "write_files.0: 'path' is a required property",
            ),
            (
                {"write_files": [{"path": "/some", "bogus": True}]},
                re.escape(
                    "write_files.0: Additional properties are not allowed"
                    " ('bogus'"
                ),
            ),
            (  # Strict encoding choices
                {"write_files": [{"path": "/some", "encoding": "g"}]},
                re.escape(
                    "write_files.0.encoding: 'g' is not one of ['gz', 'gzip',"
                ),
            ),
            (
                {
                    "write_files": [
                        {
                            "append": False,
                            "source": {
                                "uri": "http://a.com/a",
                                "headers": {
                                    "Authorization": "Bearer SOME_TOKEN"
                                },
                            },
                            "content": "a",
                            "encoding": "text/plain",
                            "owner": "jeff",
                            "path": "/some",
                            "permissions": "0777",
                        }
                    ]
                },
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
