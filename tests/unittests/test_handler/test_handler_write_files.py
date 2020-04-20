# This file is part of cloud-init. See LICENSE file for license information.

import base64
import gzip
import io
import shutil
import tempfile

from cloudinit import log as logging
from cloudinit import util
from cloudinit.config.cc_write_files import write_files, decode_perms
from cloudinit.tests.helpers import CiTestCase, FilesystemMockingTestCase

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
    '/usr/bin/hello': "#!/bin/sh\necho hello world\n",
    '/wark': "foobar\n",
    '/tmp/message': "hi mom line 1\nhi mom line 2\n",
}


class TestWriteFiles(FilesystemMockingTestCase):
    def setUp(self):
        super(TestWriteFiles, self).setUp()
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def test_simple(self):
        self.patchUtils(self.tmp)
        expected = "hello world\n"
        filename = "/tmp/my.file"
        write_files(
            "test_simple", [{"content": expected, "path": filename}])
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
            [{"content": added, "path": filename, "append": "true"}])
        self.assertEqual(util.load_file(filename), expected)

    def test_yaml_binary(self):
        self.patchUtils(self.tmp)
        data = util.load_yaml(YAML_TEXT)
        write_files("testname", data['write_files'])
        for path, content in YAML_CONTENT_EXPECTED.items():
            self.assertEqual(util.load_file(path), content)

    def test_all_decodings(self):
        self.patchUtils(self.tmp)

        # build a 'files' array that has a dictionary of encodings
        # for 'gz', 'gzip', 'gz+base64' ...
        data = b"foobzr"
        utf8_valid = b"foobzr"
        utf8_invalid = b'ab\xaadef'
        files = []
        expected = []

        gz_aliases = ('gz', 'gzip')
        gz_b64_aliases = ('gz+base64', 'gzip+base64', 'gz+b64', 'gzip+b64')
        b64_aliases = ('base64', 'b64')

        datum = (("utf8", utf8_valid), ("no-utf8", utf8_invalid))
        for name, data in datum:
            gz = (_gzip_bytes(data), gz_aliases)
            gz_b64 = (base64.b64encode(_gzip_bytes(data)), gz_b64_aliases)
            b64 = (base64.b64encode(data), b64_aliases)
            for content, aliases in (gz, gz_b64, b64):
                for enc in aliases:
                    cur = {'content': content,
                           'path': '/tmp/file-%s-%s' % (name, enc),
                           'encoding': enc}
                    files.append(cur)
                    expected.append((cur['path'], data))

        write_files("test_decoding", files)

        for path, content in expected:
            self.assertEqual(util.load_file(path, decode=False), content)

        # make sure we actually wrote *some* files.
        flen_expected = (
            len(gz_aliases + gz_b64_aliases + b64_aliases) * len(datum))
        self.assertEqual(len(expected), flen_expected)


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
