# This file is part of cloud-init. See LICENSE file for license information.

import base64
import copy
import gzip
import io
import shutil
import tempfile

from cloudinit import log as logging
from cloudinit import util
from cloudinit.config.cc_write_files import decode_perms, handle, write_files
from tests.unittests.helpers import (
    CiTestCase,
    FilesystemMockingTestCase,
    mock,
    skipUnlessJsonSchema,
)

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

INVALID_SCHEMA = {  # Dropped required path key
    "write_files": [
        {
            "append": False,
            "content": "a",
            "encoding": "gzip",
            "owner": "jeff",
            "permissions": "0777",
        }
    ]
}


@skipUnlessJsonSchema()
@mock.patch("cloudinit.config.cc_write_files.write_files")
class TestWriteFilesSchema(CiTestCase):

    with_logs = True

    def test_schema_validation_warns_missing_path(self, m_write_files):
        """The only required file item property is 'path'."""
        cc = self.tmp_cloud("ubuntu")
        valid_config = {"write_files": [{"path": "/some/path"}]}
        handle("cc_write_file", valid_config, cc, LOG, [])
        self.assertNotIn(
            "Invalid cloud-config provided:", self.logs.getvalue()
        )
        handle("cc_write_file", INVALID_SCHEMA, cc, LOG, [])
        self.assertIn("Invalid cloud-config provided:", self.logs.getvalue())
        self.assertIn("'path' is a required property", self.logs.getvalue())

    def test_schema_validation_warns_non_string_type_for_files(
        self, m_write_files
    ):
        """Schema validation warns of non-string values for each file item."""
        cc = self.tmp_cloud("ubuntu")
        for key in VALID_SCHEMA["write_files"][0].keys():
            if key == "append":
                key_type = "boolean"
            else:
                key_type = "string"
            invalid_config = copy.deepcopy(VALID_SCHEMA)
            invalid_config["write_files"][0][key] = 1
            handle("cc_write_file", invalid_config, cc, LOG, [])
            self.assertIn(
                mock.call("cc_write_file", invalid_config["write_files"]),
                m_write_files.call_args_list,
            )
            self.assertIn(
                "write_files.0.%s: 1 is not of type '%s'" % (key, key_type),
                self.logs.getvalue(),
            )
        self.assertIn("Invalid cloud-config provided:", self.logs.getvalue())

    def test_schema_validation_warns_on_additional_undefined_propertes(
        self, m_write_files
    ):
        """Schema validation warns on additional undefined file properties."""
        cc = self.tmp_cloud("ubuntu")
        invalid_config = copy.deepcopy(VALID_SCHEMA)
        invalid_config["write_files"][0]["bogus"] = "value"
        handle("cc_write_file", invalid_config, cc, LOG, [])
        self.assertIn(
            "Invalid cloud-config provided:\nwrite_files.0: Additional"
            " properties are not allowed ('bogus' was unexpected)",
            self.logs.getvalue(),
        )


class TestWriteFiles(FilesystemMockingTestCase):

    with_logs = True

    def setUp(self):
        super(TestWriteFiles, self).setUp()
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    @skipUnlessJsonSchema()
    def test_handler_schema_validation_warns_non_array_type(self):
        """Schema validation warns of non-array value."""
        invalid_config = {"write_files": 1}
        cc = self.tmp_cloud("ubuntu")
        with self.assertRaises(TypeError):
            handle("cc_write_file", invalid_config, cc, LOG, [])
        self.assertIn(
            "Invalid cloud-config provided:\nwrite_files: 1 is not of type"
            " 'array'",
            self.logs.getvalue(),
        )

    def test_simple(self):
        self.patchUtils(self.tmp)
        expected = "hello world\n"
        filename = "/tmp/my.file"
        write_files("test_simple", [{"content": expected, "path": filename}])
        self.assertEqual(util.load_file(filename), expected)

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
        )
        self.assertEqual(util.load_file(filename), expected)

    def test_yaml_binary(self):
        self.patchUtils(self.tmp)
        data = util.load_yaml(YAML_TEXT)
        write_files("testname", data["write_files"])
        for path, content in YAML_CONTENT_EXPECTED.items():
            self.assertEqual(util.load_file(path), content)

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
                    cur = {
                        "content": content,
                        "path": "/tmp/file-%s-%s" % (name, enc),
                        "encoding": enc,
                    }
                    files.append(cur)
                    expected.append((cur["path"], data))

        write_files("test_decoding", files)

        for path, content in expected:
            self.assertEqual(util.load_file(path, decode=False), content)

        # make sure we actually wrote *some* files.
        flen_expected = len(gz_aliases + gz_b64_aliases + b64_aliases) * len(
            datum
        )
        self.assertEqual(len(expected), flen_expected)

    def test_deferred(self):
        self.patchUtils(self.tmp)
        file_path = "/tmp/deferred.file"
        config = {"write_files": [{"path": file_path, "defer": True}]}
        cc = self.tmp_cloud("ubuntu")
        handle("cc_write_file", config, cc, LOG, [])
        with self.assertRaises(FileNotFoundError):
            util.load_file(file_path)


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


# vi: ts=4 expandtab
