# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.config.cc_write_files import write_files
from cloudinit import log as logging
from cloudinit import util

from ..helpers import FilesystemMockingTestCase

import base64
import gzip
import shutil
import six
import tempfile

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
            "test_simple", [{"content": expected, "path": filename}], LOG)
        self.assertEqual(util.load_file(filename), expected)

    def test_yaml_binary(self):
        self.patchUtils(self.tmp)
        data = util.load_yaml(YAML_TEXT)
        write_files("testname", data['write_files'], LOG)
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

        write_files("test_decoding", files, LOG)

        for path, content in expected:
            self.assertEqual(util.load_file(path, decode=False), content)

        # make sure we actually wrote *some* files.
        flen_expected = (
            len(gz_aliases + gz_b64_aliases + b64_aliases) * len(datum))
        self.assertEqual(len(expected), flen_expected)


def _gzip_bytes(data):
    buf = six.BytesIO()
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
