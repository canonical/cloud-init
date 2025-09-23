# This file is part of cloud-init. See LICENSE file for license information.

import base64
import gzip
import io
import logging
import re
from unittest import mock

import pytest
import responses

from cloudinit import util
from cloudinit.config.cc_write_files import decode_perms, handle, write_files
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import SCHEMA_EMPTY_ERROR, skipUnlessJsonSchema
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


OWNER = "root:root"
USER = "root"
GROUP = "root"


@pytest.fixture
def cloud():
    cc = get_cloud("ubuntu")
    with mock.patch.object(cc.distro, "default_owner", OWNER):
        yield cc


@pytest.mark.usefixtures("fake_filesystem")
@mock.patch("cloudinit.config.cc_write_files.util.chownbyname")
class TestWriteFiles:
    def test_simple(self, m_chownbyname):
        expected = "hello world\n"
        filename = str("/tmp/my.file")
        write_files(
            "test_simple",
            [{"content": expected, "path": filename}],
            OWNER,
        )
        assert util.load_text_file(filename) == expected
        assert [
            mock.call(mock.ANY, USER, GROUP)
        ] == m_chownbyname.call_args_list

    def test_empty(self, m_chownbyname):
        filename = str("/tmp/my.file")
        write_files(
            "test_empty",
            [{"path": filename}],
            OWNER,
        )
        assert util.load_text_file(filename) == ""
        assert [
            mock.call(mock.ANY, USER, GROUP)
        ] == m_chownbyname.call_args_list

    def test_append(self, m_chownbyname):
        existing = "hello "
        added = "world\n"
        expected = existing + added
        filename = "/tmp/append.file"
        util.write_file(filename, existing)
        write_files(
            "test_append",
            [{"content": added, "path": filename, "append": "true"}],
            OWNER,
        )
        assert util.load_text_file(filename) == expected
        assert [
            mock.call(mock.ANY, USER, GROUP)
        ] == m_chownbyname.call_args_list

    def test_special_permission_bits(self, m_chownbyname, tmp_path):
        expected = "hello world\n"
        filename = str(tmp_path / "special.file")
        permissions = 0o4711
        write_files(
            "test_permission",
            [
                {
                    "content": expected,
                    "path": filename,
                    "permissions": permissions,
                }
            ],
            OWNER,
        )
        assert util.load_text_file(filename) == expected
        assert [
            mock.call(mock.ANY, USER, GROUP)
        ] == m_chownbyname.call_args_list
        assert util.get_permissions(filename) == decode_perms(
            permissions, None
        )

    def test_yaml_binary(self, m_chownbyname):
        data_wrong_paths = util.load_yaml(YAML_TEXT)
        data = []
        for content in data_wrong_paths["write_files"]:
            content["path"] = content["path"]
            data.append(content)

        write_files("testname", data, OWNER)
        for path, content in YAML_CONTENT_EXPECTED.items():
            assert util.load_text_file(path) == content
        assert 5 == m_chownbyname.call_count

    def test_all_decodings(self, m_chownbyname):
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

        write_files("test_decoding", files, OWNER)

        for path, content in expected:
            assert util.load_binary_file(path) == content

        # make sure we actually wrote *some* files.
        flen_expected = len(gz_aliases + gz_b64_aliases + b64_aliases) * len(
            datum
        )
        assert len(expected) == flen_expected
        assert len(expected) == m_chownbyname.call_count

    def test_handle_plain_text(self, m_chownbyname, caplog, cloud):
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
        handle("ignored", cfg, cloud, [])
        assert content == util.load_text_file(file_path)
        assert "Unknown encoding type text/plain" not in caplog.text
        assert [
            mock.call(mock.ANY, USER, GROUP)
        ] == m_chownbyname.call_args_list

    def test_file_uri(self, m_chownbyname, cloud):
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
        handle("ignored", cfg, cloud, [])
        assert util.load_text_file(src_path) == util.load_text_file(dst_path)
        assert m_chownbyname.call_count

    @responses.activate
    def test_http_uri(self, m_chownbyname, cloud):
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
        handle("ignored", cfg, cloud, [])
        assert content == util.load_text_file(path)
        assert [
            mock.call(mock.ANY, USER, GROUP)
        ] == m_chownbyname.call_args_list

    def test_uri_fallback(self, m_chownbyname, cloud):
        src_path = "tmp/INVALID"
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
        handle("ignored", cfg, cloud, [])
        assert content == util.load_text_file(dst_path)
        assert [
            mock.call(mock.ANY, USER, GROUP)
        ] == m_chownbyname.call_args_list

    def test_deferred(self, m_chownbyname, cloud):
        file_path = "/tmp/deferred.file"
        config = {"write_files": [{"path": file_path, "defer": True}]}
        handle("cc_write_file", config, cloud, [])
        with pytest.raises(FileNotFoundError):
            util.load_text_file(file_path)
        assert [] == m_chownbyname.call_args_list


class TestDecodePerms:
    def test_none_returns_default(self):
        """If None is passed as perms, then default should be returned."""
        default = object()
        found = decode_perms(None, default)
        assert default == found

    def test_integer(self):
        """A valid integer should return itself."""
        found = decode_perms(0o755, None)
        assert 0o755 == found

    def test_valid_octal_string(self):
        """A string should be read as octal."""
        found = decode_perms("644", None)
        assert 0o644 == found

    def test_invalid_octal_string_returns_default_and_warns(self, caplog):
        """A string with invalid octal should warn and return default."""
        found = decode_perms("999", None)
        assert found is None
        assert (
            mock.ANY,
            logging.WARNING,
            "Undecodable permissions '999', returning default None",
        ) in caplog.record_tuples


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
