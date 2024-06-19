# This file is part of cloud-init. See LICENSE file for license information.

"""Tests for handling of userdata within cloud init."""

import gzip
import logging
import os
from email import encoders
from email.mime.application import MIMEApplication
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from io import BytesIO
from pathlib import Path
from unittest import mock

import pytest
import requests
import responses

from cloudinit import handlers
from cloudinit import helpers as c_helpers
from cloudinit import safeyaml, stages
from cloudinit import user_data as ud
from cloudinit import util
from cloudinit.config.modules import Modules
from cloudinit.settings import DEFAULT_RUN_DIR, PER_INSTANCE
from tests.unittests import helpers
from tests.unittests.util import FakeDataSource

MPATH = "cloudinit.stages"


def count_messages(root):
    am = 0
    for m in root.walk():
        if ud.is_skippable(m):
            continue
        am += 1
    return am


def gzip_text(text):
    contents = BytesIO()
    f = gzip.GzipFile(fileobj=contents, mode="wb")
    f.write(util.encode_text(text))
    f.flush()
    f.close()
    return contents.getvalue()


@pytest.fixture(scope="function")
def init_tmp(request, tmpdir):
    ci = stages.Init()
    cloud_dir = tmpdir.join("cloud")
    cloud_dir.mkdir()
    run_dir = tmpdir.join("run")
    run_dir.mkdir()
    ci._cfg = {
        "system_info": {
            "default_user": {"name": "ubuntu"},
            "distro": "ubuntu",
            "paths": {
                "cloud_dir": cloud_dir.strpath,
                "run_dir": run_dir.strpath,
            },
        }
    }
    run_dir.join("instance-data-sensitive.json").write("{}")
    return ci


class TestConsumeUserData:
    def test_simple_jsonp(self, init_tmp):
        user_blob = """
#cloud-config-jsonp
[
     { "op": "add", "path": "/baz", "value": "qux" },
     { "op": "add", "path": "/bar", "value": "qux2" }
]
"""
        init_tmp.datasource = FakeDataSource(user_blob)
        init_tmp.fetch()
        with mock.patch.object(init_tmp, "_reset"):
            init_tmp.consume_data()
        cc_contents = util.load_text_file(
            init_tmp.paths.get_ipath("cloud_config")
        )
        cc = util.load_yaml(cc_contents)
        assert len(cc) == 2
        assert cc["baz"] == "qux"
        assert cc["bar"] == "qux2"

    @pytest.mark.usefixtures("fake_filesystem")
    def test_simple_jsonp_vendor_and_vendor2_and_user(self):
        # test that user-data wins over vendor
        user_blob = """
#cloud-config-jsonp
[
     { "op": "add", "path": "/baz", "value": "qux" },
     { "op": "add", "path": "/bar", "value": "qux2" },
     { "op": "add", "path": "/foobar", "value": "qux3" }
]
"""
        vendor_blob = """
#cloud-config-jsonp
[
     { "op": "add", "path": "/baz", "value": "quxA" },
     { "op": "add", "path": "/bar", "value": "quxB" },
     { "op": "add", "path": "/foo", "value": "quxC" },
     { "op": "add", "path": "/corge", "value": "quxEE" }
]
"""
        vendor2_blob = """
#cloud-config-jsonp
[
     { "op": "add", "path": "/corge", "value": "quxD" },
     { "op": "add", "path": "/grault", "value": "quxFF" },
     { "op": "add", "path": "/foobar", "value": "quxGG" }
]
"""
        initer = stages.Init()
        initer.datasource = FakeDataSource(
            user_blob, vendordata=vendor_blob, vendordata2=vendor2_blob
        )
        initer.read_cfg()
        initer.initialize()
        initer.fetch()
        initer.instancify()
        with mock.patch(
            "cloudinit.util.read_conf_from_cmdline", return_value={}
        ):
            initer.update()
        initer.cloudify().run(
            "consume_data",
            initer.consume_data,
            args=[PER_INSTANCE],
            freq=PER_INSTANCE,
        )
        mods = Modules(initer)
        (_which_ran, _failures) = mods.run_section("cloud_init_modules")
        cfg = mods.cfg
        assert "vendor_data" in cfg
        assert "vendor_data2" in cfg
        # Confirm that vendordata2 overrides vendordata, and that
        #  userdata overrides both
        assert cfg["baz"] == "qux"
        assert cfg["bar"] == "qux2"
        assert cfg["foobar"] == "qux3"
        assert cfg["foo"] == "quxC"
        assert cfg["corge"] == "quxD"
        assert cfg["grault"] == "quxFF"

    @pytest.mark.usefixtures("fake_filesystem")
    def test_simple_jsonp_no_vendor_consumed(self):
        # make sure that vendor data is not consumed
        user_blob = """
#cloud-config-jsonp
[
     { "op": "add", "path": "/baz", "value": "qux" },
     { "op": "add", "path": "/bar", "value": "qux2" },
     { "op": "add", "path": "/vendor_data", "value": {"enabled": "false"}}
]
"""
        vendor_blob = """
#cloud-config-jsonp
[
     { "op": "add", "path": "/baz", "value": "quxA" },
     { "op": "add", "path": "/bar", "value": "quxB" },
     { "op": "add", "path": "/foo", "value": "quxC" }
]
"""
        initer = stages.Init()
        initer.datasource = FakeDataSource(user_blob, vendordata=vendor_blob)
        initer.read_cfg()
        initer.initialize()
        initer.fetch()
        initer.instancify()
        initer.update()
        initer.cloudify().run(
            "consume_data",
            initer.consume_data,
            args=[PER_INSTANCE],
            freq=PER_INSTANCE,
        )
        mods = Modules(initer)
        (_which_ran, _failures) = mods.run_section("cloud_init_modules")
        cfg = mods.cfg
        assert cfg["baz"] == "qux"
        assert cfg["bar"] == "qux2"
        assert "foo" not in cfg

    def test_mixed_cloud_config(self, init_tmp):
        blob_cc = """
#cloud-config
a: b
c: d
"""
        message_cc = MIMEBase("text", "cloud-config")
        message_cc.set_payload(blob_cc)

        blob_jp = """
#cloud-config-jsonp
[
     { "op": "replace", "path": "/a", "value": "c" },
     { "op": "remove", "path": "/c" }
]
"""

        message_jp = MIMEBase("text", "cloud-config-jsonp")
        message_jp.set_payload(blob_jp)

        message = MIMEMultipart()
        message.attach(message_cc)
        message.attach(message_jp)

        init_tmp.datasource = FakeDataSource(str(message))
        init_tmp.fetch()
        with mock.patch.object(init_tmp, "_reset"):
            init_tmp.consume_data()
        cc_contents = util.load_text_file(
            init_tmp.paths.get_ipath("cloud_config")
        )
        cc = util.load_yaml(cc_contents)
        assert len(cc) == 1
        assert cc["a"] == "c"

    def test_cloud_config_as_x_shell_script(self, init_tmp):
        blob_cc = """
#cloud-config
a: b
c: d
"""
        message_cc = MIMEBase("text", "x-shellscript")
        message_cc.set_payload(blob_cc)

        blob_jp = """
#cloud-config-jsonp
[
     { "op": "replace", "path": "/a", "value": "c" },
     { "op": "remove", "path": "/c" }
]
"""

        message_jp = MIMEBase("text", "cloud-config-jsonp")
        message_jp.set_payload(blob_jp)

        message = MIMEMultipart()
        message.attach(message_cc)
        message.attach(message_jp)

        init_tmp.datasource = FakeDataSource(str(message))
        init_tmp.fetch()
        with mock.patch.object(init_tmp, "_reset"):
            init_tmp.consume_data()
        cc_contents = util.load_text_file(
            init_tmp.paths.get_ipath("cloud_config")
        )
        cc = util.load_yaml(cc_contents)
        assert len(cc) == 1
        assert cc["a"] == "c"

    @pytest.mark.usefixtures("fake_filesystem")
    def test_vendor_user_yaml_cloud_config(self):
        vendor_blob = """
#cloud-config
a: b
name: vendor
run:
 - x
 - y
"""

        user_blob = """
#cloud-config
a: c
vendor_data:
  enabled: true
  prefix: /bin/true
name: user
run:
 - z
"""
        initer = stages.Init()
        initer.datasource = FakeDataSource(user_blob, vendordata=vendor_blob)
        initer.read_cfg()
        initer.initialize()
        initer.fetch()
        initer.instancify()
        initer.update()
        initer.cloudify().run(
            "consume_data",
            initer.consume_data,
            args=[PER_INSTANCE],
            freq=PER_INSTANCE,
        )
        mods = Modules(initer)
        (_which_ran, _failures) = mods.run_section("cloud_init_modules")
        cfg = mods.cfg
        assert "vendor_data" in cfg
        assert cfg["a"] == "c"
        assert cfg["name"] == "user"
        assert "x" not in cfg["run"]
        assert "y" not in cfg["run"]
        assert "z" in cfg["run"]

    @pytest.mark.usefixtures("fake_filesystem")
    def test_vendordata_script(self):
        vendor_blob = """
#!/bin/bash
echo "test"
"""
        vendor2_blob = """
#!/bin/bash
echo "dynamic test"
"""

        user_blob = """
#cloud-config
vendor_data:
  enabled: true
  prefix: /bin/true
"""
        initer = stages.Init()
        initer.datasource = FakeDataSource(
            user_blob, vendordata=vendor_blob, vendordata2=vendor2_blob
        )
        initer.read_cfg()
        initer.initialize()
        initer.fetch()
        initer.instancify()
        initer.update()
        initer.cloudify().run(
            "consume_data",
            initer.consume_data,
            args=[PER_INSTANCE],
            freq=PER_INSTANCE,
        )
        mods = Modules(initer)
        (_which_ran, _failures) = mods.run_section("cloud_init_modules")
        vendor_script = initer.paths.get_ipath_cur("vendor_scripts")
        vendor_script_fns = "%s/part-001" % vendor_script
        assert os.path.exists(vendor_script_fns) is True

    def test_merging_cloud_config(self, tmpdir):
        blob = """
#cloud-config
a: b
e: f
run:
 - b
 - c
"""
        message1 = MIMEBase("text", "cloud-config")
        message1.set_payload(blob)

        blob2 = """
#cloud-config
a: e
e: g
run:
 - stuff
 - morestuff
"""
        message2 = MIMEBase("text", "cloud-config")
        message2[
            "X-Merge-Type"
        ] = "dict(recurse_array,recurse_str)+list(append)+str(append)"
        message2.set_payload(blob2)

        blob3 = """
#cloud-config
e:
 - 1
 - 2
 - 3
p: 1
"""
        message3 = MIMEBase("text", "cloud-config")
        message3.set_payload(blob3)

        messages = [message1, message2, message3]

        paths = c_helpers.Paths(
            {"cloud_dir": tmpdir, "run_dir": tmpdir}, ds=FakeDataSource("")
        )
        cloud_cfg = handlers.cloud_config.CloudConfigPartHandler(paths)

        cloud_cfg.handle_part(
            None, handlers.CONTENT_START, None, None, None, None
        )
        for i, m in enumerate(messages):
            headers = dict(m)
            fn = "part-%s" % (i + 1)
            payload = m.get_payload(decode=True)
            cloud_cfg.handle_part(
                None, headers["Content-Type"], fn, payload, None, headers
            )
        cloud_cfg.handle_part(
            None, handlers.CONTENT_END, None, None, None, None
        )
        contents = util.load_text_file(paths.get_ipath("cloud_config"))
        contents = util.load_yaml(contents)
        assert contents["run"], ["b", "c", "stuff", "morestuff"]
        assert contents["a"] == "be"
        assert contents["e"] == [1, 2, 3]
        assert contents["p"] == 1

    def test_unhandled_type_warning(self, init_tmp, caplog):
        """Raw text without magic is ignored but shows warning."""
        data = "arbitrary text\n"
        init_tmp.datasource = FakeDataSource(data)

        with mock.patch("cloudinit.util.write_file") as mockobj:
            with caplog.at_level(logging.WARNING):
                init_tmp.fetch()
                with mock.patch.object(init_tmp, "_reset"):
                    init_tmp.consume_data()
            assert (
                "Unhandled non-multipart (text/x-not-multipart) userdata:"
                in caplog.text
            )
        mockobj.assert_called_once_with(
            init_tmp.paths.get_ipath("cloud_config"), "", 0o600
        )

    def test_mime_gzip_compressed(self, init_tmp):
        """Tests that individual message gzip encoding works."""

        def gzip_part(text):
            return MIMEApplication(gzip_text(text), "gzip")

        base_content1 = """
#cloud-config
a: 2
"""

        base_content2 = """
#cloud-config
b: 3
c: 4
"""

        message = MIMEMultipart("test")
        message.attach(gzip_part(base_content1))
        message.attach(gzip_part(base_content2))
        init_tmp.datasource = FakeDataSource(str(message))
        init_tmp.fetch()
        with mock.patch.object(init_tmp, "_reset"):
            init_tmp.consume_data()
        contents = util.load_text_file(
            init_tmp.paths.get_ipath("cloud_config")
        )
        contents = util.load_yaml(contents)
        assert isinstance(contents, dict) is True
        assert len(contents) == 3
        assert contents["a"] == 2
        assert contents["b"] == 3
        assert contents["c"] == 4

    def test_mime_text_plain(self, init_tmp, caplog):
        """Mime message of type text/plain is ignored but shows warning."""
        message = MIMEBase("text", "plain")
        message.set_payload("Just text")
        init_tmp.datasource = FakeDataSource(message.as_string().encode())

        with mock.patch("cloudinit.util.write_file") as mockobj:
            with caplog.at_level(logging.WARNING):
                init_tmp.fetch()
                with mock.patch.object(init_tmp, "_reset"):
                    init_tmp.consume_data()
            assert "Unhandled unknown content-type (text/plain)" in caplog.text
        mockobj.assert_called_once_with(
            init_tmp.paths.get_ipath("cloud_config"), "", 0o600
        )

    # Since features are intended to be overridden downstream, mock them
    # all here so new feature flags don't require a new change to this
    # unit test.
    @mock.patch.multiple(
        "cloudinit.features",
        ERROR_ON_USER_DATA_FAILURE=True,
        ALLOW_EC2_MIRRORS_ON_NON_AWS_INSTANCE_TYPES=True,
        EXPIRE_APPLIES_TO_HASHED_USERS=False,
        NETPLAN_CONFIG_ROOT_READ_ONLY=True,
        DEPRECATION_INFO_BOUNDARY="devel",
        NOCLOUD_SEED_URL_APPEND_FORWARD_SLASH=False,
        APT_DEB822_SOURCE_LIST_FILE=True,
    )
    def test_shellscript(self, init_tmp, tmpdir, caplog):
        """Raw text starting #!/bin/sh is treated as script."""
        script = "#!/bin/sh\necho hello\n"
        init_tmp.datasource = FakeDataSource(script)

        outpath = os.path.join(
            init_tmp.paths.get_ipath_cur("scripts"), "part-001"
        )

        with mock.patch("cloudinit.util.write_file") as mockobj:
            with caplog.at_level(logging.WARNING):
                init_tmp.fetch()
                with mock.patch.object(init_tmp, "_reset"):
                    init_tmp.consume_data()
                assert caplog.records == []  # No warnings

        mockobj.assert_has_calls(
            [
                mock.call(outpath, script, 0o700),
                mock.call(init_tmp.paths.get_ipath("cloud_config"), "", 0o600),
            ]
        )
        expected = {
            "features": {
                "ERROR_ON_USER_DATA_FAILURE": True,
                "ALLOW_EC2_MIRRORS_ON_NON_AWS_INSTANCE_TYPES": True,
                "EXPIRE_APPLIES_TO_HASHED_USERS": False,
                "NETPLAN_CONFIG_ROOT_READ_ONLY": True,
                "DEPRECATION_INFO_BOUNDARY": "devel",
                "NOCLOUD_SEED_URL_APPEND_FORWARD_SLASH": False,
                "APT_DEB822_SOURCE_LIST_FILE": True,
            },
            "system_info": {
                "default_user": {"name": "ubuntu"},
                "distro": "ubuntu",
                "paths": {
                    "cloud_dir": tmpdir.join("cloud").strpath,
                    "run_dir": tmpdir.join("run").strpath,
                },
            },
        }

        loaded_json = util.load_json(
            util.load_text_file(
                init_tmp.paths.get_runpath("instance_data_sensitive")
            )
        )
        assert expected == loaded_json

        expected["_doc"] = stages.COMBINED_CLOUD_CONFIG_DOC
        assert expected == util.load_json(
            util.load_text_file(
                init_tmp.paths.get_runpath("combined_cloud_config")
            )
        )

    def test_mime_text_x_shellscript(self, init_tmp, caplog):
        """Mime message of type text/x-shellscript is treated as script."""
        script = "#!/bin/sh\necho hello\n"
        message = MIMEBase("text", "x-shellscript")
        message.set_payload(script)
        init_tmp.datasource = FakeDataSource(message.as_string())

        outpath = os.path.join(
            init_tmp.paths.get_ipath_cur("scripts"), "part-001"
        )

        with mock.patch("cloudinit.util.write_file") as mockobj:
            with caplog.at_level(logging.WARNING):
                init_tmp.fetch()
                with mock.patch.object(init_tmp, "_reset"):
                    init_tmp.consume_data()
                assert caplog.records == []  # No warnings

        mockobj.assert_has_calls(
            [
                mock.call(outpath, script, 0o700),
                mock.call(init_tmp.paths.get_ipath("cloud_config"), "", 0o600),
            ]
        )

    def test_mime_text_plain_shell(self, init_tmp, caplog):
        """Mime type text/plain starting #!/bin/sh is treated as script."""
        script = "#!/bin/sh\necho hello\n"
        message = MIMEBase("text", "plain")
        message.set_payload(script)
        init_tmp.datasource = FakeDataSource(message.as_string())

        outpath = os.path.join(
            init_tmp.paths.get_ipath_cur("scripts"), "part-001"
        )

        with mock.patch("cloudinit.util.write_file") as mockobj:
            with caplog.at_level(logging.WARNING):
                init_tmp.fetch()
                with mock.patch.object(init_tmp, "_reset"):
                    init_tmp.consume_data()
                assert caplog.records == []  # No warnings

        mockobj.assert_has_calls(
            [
                mock.call(outpath, script, 0o700),
                mock.call(init_tmp.paths.get_ipath("cloud_config"), "", 0o600),
            ]
        )

    def test_mime_application_octet_stream(self, init_tmp, caplog):
        """Mime type application/octet-stream is ignored but shows warning."""
        message = MIMEBase("application", "octet-stream")
        message.set_payload(b"\xbf\xe6\xb2\xc3\xd3\xba\x13\xa4\xd8\xa1\xcc")
        encoders.encode_base64(message)
        init_tmp.datasource = FakeDataSource(message.as_string().encode())

        with mock.patch("cloudinit.util.write_file") as mockobj:
            with caplog.at_level(logging.WARNING):
                init_tmp.fetch()
                with mock.patch.object(init_tmp, "_reset"):
                    init_tmp.consume_data()
                    assert (
                        "Unhandled unknown content-type"
                        " (application/octet-stream)" in caplog.text
                    )
        mockobj.assert_called_once_with(
            init_tmp.paths.get_ipath("cloud_config"), "", 0o600
        )

    def test_cloud_config_archive(self, init_tmp):
        non_decodable = b"\x11\xc9\xb4gTH\xee\x12"
        data = [
            {"content": "#cloud-config\npassword: gocubs\n"},
            {"content": "#cloud-config\nlocale: chicago\n"},
            {"content": non_decodable},
        ]
        message = b"#cloud-config-archive\n" + safeyaml.dumps(data).encode()

        init_tmp.datasource = FakeDataSource(message)

        fs = {}

        def fsstore(filename, content, mode=0o0644, omode="wb"):
            fs[filename] = content

        # consuming the user-data provided should write 'cloud_config' file
        # which will have our yaml in it.
        with mock.patch("cloudinit.util.write_file") as mockobj:
            mockobj.side_effect = fsstore
            init_tmp.fetch()
            with mock.patch.object(init_tmp, "_reset"):
                init_tmp.consume_data()

        cfg = util.load_yaml(fs[init_tmp.paths.get_ipath("cloud_config")])
        assert cfg.get("password") == "gocubs"
        assert cfg.get("locale") == "chicago"

    @pytest.mark.usefixtures("fake_filesystem")
    @mock.patch("cloudinit.util.read_conf_with_confd")
    def test_dont_allow_user_data(self, mock_cfg):
        mock_cfg.return_value = {"allow_userdata": False}

        # test that user-data is ignored but vendor-data is kept
        user_blob = """
#cloud-config-jsonp
[
     { "op": "add", "path": "/baz", "value": "qux" },
     { "op": "add", "path": "/bar", "value": "qux2" }
]
"""
        vendor_blob = """
#cloud-config-jsonp
[
     { "op": "add", "path": "/baz", "value": "quxA" },
     { "op": "add", "path": "/bar", "value": "quxB" },
     { "op": "add", "path": "/foo", "value": "quxC" }
]
"""
        init = stages.Init()
        init.datasource = FakeDataSource(user_blob, vendordata=vendor_blob)
        init.read_cfg()
        init.initialize()
        init.fetch()
        init.instancify()
        init.update()
        init.cloudify().run(
            "consume_data",
            init.consume_data,
            args=[PER_INSTANCE],
            freq=PER_INSTANCE,
        )
        mods = Modules(init)
        (_which_ran, _failures) = mods.run_section("cloud_init_modules")
        cfg = mods.cfg
        assert "vendor_data" in cfg
        assert cfg["baz"] == "quxA"
        assert cfg["bar"] == "quxB"
        assert cfg["foo"] == "quxC"


class TestConsumeUserDataHttp:
    @responses.activate
    @mock.patch("cloudinit.url_helper.time.sleep")
    def test_include(self, mock_sleep, init_tmp):
        """Test #include."""
        included_url = "http://hostname/path"
        included_data = "#cloud-config\nincluded: true\n"
        responses.add(responses.GET, included_url, included_data)

        init_tmp.datasource = FakeDataSource("#include\nhttp://hostname/path")
        init_tmp.fetch()
        with mock.patch.object(init_tmp, "_reset") as _reset:
            init_tmp.consume_data()
            assert _reset.call_count == 1
        cc_contents = util.load_text_file(
            init_tmp.paths.get_ipath("cloud_config")
        )
        cc = util.load_yaml(cc_contents)
        assert cc.get("included") is True

    @responses.activate
    @mock.patch("cloudinit.url_helper.time.sleep")
    def test_include_bad_url(self, mock_sleep, init_tmp):
        """Test #include with a bad URL."""
        bad_url = "http://bad/forbidden"
        bad_data = "#cloud-config\nbad: true\n"
        responses.add(responses.GET, bad_url, bad_data, status=403)

        included_url = "http://hostname/path"
        included_data = "#cloud-config\nincluded: true\n"
        responses.add(responses.GET, included_url, included_data)

        init_tmp.datasource = FakeDataSource(
            "#include\nhttp://bad/forbidden\nhttp://hostname/path"
        )
        init_tmp.fetch()
        with pytest.raises(Exception, match="403"):
            with mock.patch.object(init_tmp, "_reset") as _reset:
                init_tmp.consume_data()
                assert _reset.call_count == 1

        with pytest.raises(FileNotFoundError):
            util.load_text_file(init_tmp.paths.get_ipath("cloud_config"))

    @responses.activate
    @mock.patch("cloudinit.url_helper.time.sleep")
    @mock.patch("cloudinit.util.is_container")
    @mock.patch(
        "cloudinit.user_data.features.ERROR_ON_USER_DATA_FAILURE", False
    )
    def test_include_bad_url_no_fail(
        self, is_container, mock_sleep, tmpdir, init_tmp, caplog
    ):
        """Test #include with a bad URL and failure disabled"""
        is_container.return_value = True
        bad_url = "http://bad/forbidden"
        responses.add(
            responses.GET,
            bad_url,
            body=requests.HTTPError(
                f"403 Client Error: Forbidden for url: {bad_url}"
            ),
            status=403,
        )

        included_url = "http://hostname/path"
        included_data = "#cloud-config\nincluded: true\n"
        responses.add(responses.GET, included_url, included_data)

        init_tmp.datasource = FakeDataSource(
            "#include\nhttp://bad/forbidden\nhttp://hostname/path"
        )
        init_tmp.fetch()
        with mock.patch.object(init_tmp, "_reset") as _reset:
            init_tmp.consume_data()
            assert _reset.call_count == 1

        assert (
            "403 Client Error: Forbidden for url: %s" % bad_url in caplog.text
        )

        cc_contents = util.load_text_file(
            init_tmp.paths.get_ipath("cloud_config")
        )
        cc = util.load_yaml(cc_contents)
        assert cc.get("bad") is None
        assert cc.get("included") is True


class TestUDProcess(helpers.ResourceUsingTestCase):
    def test_bytes_in_userdata(self):
        msg = b"#cloud-config\napt_update: True\n"
        ud_proc = ud.UserDataProcessor(self.getCloudPaths())
        message = ud_proc.process(msg)
        self.assertTrue(count_messages(message) == 1)

    def test_string_in_userdata(self):
        msg = "#cloud-config\napt_update: True\n"

        ud_proc = ud.UserDataProcessor(self.getCloudPaths())
        message = ud_proc.process(msg)
        self.assertTrue(count_messages(message) == 1)

    def test_compressed_in_userdata(self):
        msg = gzip_text("#cloud-config\napt_update: True\n")

        ud_proc = ud.UserDataProcessor(self.getCloudPaths())
        message = ud_proc.process(msg)
        self.assertTrue(count_messages(message) == 1)


class TestConvertString(helpers.TestCase):
    def test_handles_binary_non_utf8_decodable(self):
        """Printable unicode (not utf8-decodable) is safely converted."""
        blob = b"#!/bin/bash\necho \xc3\x84\n"
        msg = ud.convert_string(blob)
        self.assertEqual(blob, msg.get_payload(decode=True))

    def test_handles_binary_utf8_decodable(self):
        blob = b"\x32\x32"
        msg = ud.convert_string(blob)
        self.assertEqual(blob, msg.get_payload(decode=True))

    def test_handle_headers(self):
        text = "hi mom"
        msg = ud.convert_string(text)
        self.assertEqual(text, msg.get_payload(decode=False))

    def test_handle_mime_parts(self):
        """Mime parts are properly returned as a mime message."""
        message = MIMEBase("text", "plain")
        message.set_payload("Just text")
        msg = ud.convert_string(str(message))
        self.assertEqual("Just text", msg.get_payload(decode=False))


class TestFetchBaseConfig:
    @pytest.fixture(autouse=True)
    def mocks(self, mocker):
        mocker.patch(f"{MPATH}.util.read_conf_from_cmdline")
        mocker.patch(f"{MPATH}.read_runtime_config")

    def test_only_builtin_gets_builtin(self, mocker):
        mocker.patch(f"{MPATH}.read_runtime_config", return_value={})
        mocker.patch(f"{MPATH}.util.read_conf_with_confd")
        config = stages.fetch_base_config(DEFAULT_RUN_DIR)
        assert util.get_builtin_cfg() == config

    def test_conf_d_overrides_defaults(self, mocker):
        builtin = util.get_builtin_cfg()
        test_key = sorted(builtin)[0]
        test_value = "test"

        mocker.patch(
            f"{MPATH}.util.read_conf_with_confd",
            return_value={test_key: test_value},
        )
        mocker.patch(f"{MPATH}.read_runtime_config", return_value={})
        config = stages.fetch_base_config(DEFAULT_RUN_DIR)
        assert config.get(test_key) == test_value
        builtin[test_key] = test_value
        assert config == builtin

    def test_confd_with_template(self, mocker, tmp_path: Path):
        instance_data_path = tmp_path / "test_confd_with_template.json"
        instance_data_path.write_text('{"template_var": "template_value"}')
        cfg_path = tmp_path / "test_conf_with_template.cfg"
        cfg_path.write_text('## template:jinja\n{"key": "{{template_var}}"}')

        mocker.patch("cloudinit.stages.CLOUD_CONFIG", cfg_path)
        mocker.patch(f"{MPATH}.util.get_builtin_cfg", return_value={})
        config = stages.fetch_base_config(
            DEFAULT_RUN_DIR, instance_data_file=instance_data_path
        )
        assert config == {"key": "template_value"}

    def test_cmdline_overrides_defaults(self, mocker):
        builtin = util.get_builtin_cfg()
        test_key = sorted(builtin)[0]
        test_value = "test"
        cmdline = {test_key: test_value}

        mocker.patch(f"{MPATH}.util.read_conf_with_confd")
        mocker.patch(
            f"{MPATH}.util.read_conf_from_cmdline",
            return_value=cmdline,
        )
        mocker.patch(f"{MPATH}.read_runtime_config")
        config = stages.fetch_base_config(DEFAULT_RUN_DIR)
        assert config.get(test_key) == test_value
        builtin[test_key] = test_value
        assert config == builtin

    def test_cmdline_overrides_confd_runtime_and_defaults(self, mocker):
        builtin = {"key1": "value0", "key3": "other2"}
        conf_d = {"key1": "value1", "key2": "other1"}
        cmdline = {"key3": "other3", "key2": "other2"}
        runtime = {"key3": "runtime3"}

        mocker.patch(f"{MPATH}.util.read_conf_with_confd", return_value=conf_d)
        mocker.patch(f"{MPATH}.util.get_builtin_cfg", return_value=builtin)
        mocker.patch(f"{MPATH}.read_runtime_config", return_value=runtime)
        mocker.patch(
            f"{MPATH}.util.read_conf_from_cmdline",
            return_value=cmdline,
        )

        config = stages.fetch_base_config(DEFAULT_RUN_DIR)
        assert config == {"key1": "value1", "key2": "other2", "key3": "other3"}

    def test_order_precedence_is_builtin_system_runtime_cmdline(self, mocker):
        builtin = {"key1": "builtin0", "key3": "builtin3"}
        conf_d = {"key1": "confd1", "key2": "confd2", "keyconfd1": "kconfd1"}
        runtime = {"key1": "runtime1", "key2": "runtime2"}
        cmdline = {"key1": "cmdline1"}

        mocker.patch(f"{MPATH}.util.read_conf_with_confd", return_value=conf_d)
        mocker.patch(f"{MPATH}.util.get_builtin_cfg", return_value=builtin)
        mocker.patch(
            f"{MPATH}.util.read_conf_from_cmdline",
            return_value=cmdline,
        )
        mocker.patch(f"{MPATH}.read_runtime_config", return_value=runtime)

        config = stages.fetch_base_config(DEFAULT_RUN_DIR)

        assert config == {
            "key1": "cmdline1",
            "key2": "runtime2",
            "key3": "builtin3",
            "keyconfd1": "kconfd1",
        }
