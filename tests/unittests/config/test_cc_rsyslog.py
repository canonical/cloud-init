# This file is part of cloud-init. See LICENSE file for license information.

import copy
import re
from functools import partial
from typing import Optional
from unittest import mock

import pytest

from cloudinit import util
from cloudinit.config.cc_rsyslog import (
    apply_rsyslog_changes,
    handle,
    load_config,
    parse_remotes_line,
    remotes_to_rsyslog_cfg,
)
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import skipUnlessJsonSchema
from tests.unittests.util import get_cloud


class TestLoadConfig:
    BASECFG = {
        "config_filename": "20-cloud-config.conf",
        "config_dir": "/etc/rsyslog.d",
        "service_reload_command": "auto",
        "configs": [],
        "remotes": {},
        "check_exe": "rsyslogd",
        "packages": ["rsyslog"],
        "install_rsyslog": False,
    }

    BSDCFG = {
        "config_filename": "20-cloud-config.conf",
        "config_dir": "/usr/local/etc/rsyslog.d",
        "service_reload_command": "auto",
        "configs": [],
        "remotes": {},
        "check_exe": "rsyslogd",
        "packages": ["rsyslog"],
        "install_rsyslog": False,
    }

    def test_legacy_full(self):
        cloud = get_cloud(distro="ubuntu", metadata={})
        cfg = copy.deepcopy(self.BASECFG)

        found = load_config(
            {
                "rsyslog": ["*.* @192.168.1.1"],
                "rsyslog_dir": "mydir",
                "rsyslog_filename": "myfilename",
            },
            distro=cloud.distro,
        )
        cfg.update(
            {
                "configs": ["*.* @192.168.1.1"],
                "config_dir": "mydir",
                "config_filename": "myfilename",
                "service_reload_command": "auto",
            }
        )

        assert found == cfg

    def test_legacy_defaults(self):
        cloud = get_cloud(distro="ubuntu", metadata={})
        cfg = copy.deepcopy(self.BASECFG)

        found = load_config(
            {"rsyslog": ["*.* @192.168.1.1"]}, distro=cloud.distro
        )
        cfg.update({"configs": ["*.* @192.168.1.1"]})
        assert found == cfg

    def test_new_defaults(self):
        cloud = get_cloud(distro="ubuntu", metadata={})
        cfg = copy.deepcopy(self.BASECFG)

        assert load_config({}, distro=cloud.distro) == cfg

    def test_new_bsd_defaults(self):

        # patch for ifconfig -a
        with mock.patch(
            "cloudinit.distros.networking.subp.subp", return_values=("", None)
        ):
            cloud = get_cloud(distro="freebsd", metadata={})
        assert load_config({}, distro=cloud.distro) == self.BSDCFG

    def test_new_configs(self):
        cfg = copy.deepcopy(self.BASECFG)

        cfgs = ["*.* myhost", "*.* my2host"]
        cloud = get_cloud(distro="ubuntu", metadata={})
        cfg.update({"configs": cfgs})
        assert (
            load_config({"rsyslog": {"configs": cfgs}}, distro=cloud.distro)
            == cfg
        )


class TestApplyChanges:

    def test_simple(self, tmpdir):
        cfgline = "*.* foohost"
        changed = apply_rsyslog_changes(
            configs=[cfgline], def_fname="foo.cfg", cfg_dir=str(tmpdir)
        )

        fname = str(tmpdir.join("foo.cfg"))
        assert changed == [fname]
        assert util.load_text_file(fname) == cfgline + "\n"

    def test_multiple_files(self, tmpdir):
        configs = [
            "*.* foohost",
            {"content": "abc", "filename": "my.cfg"},
            {
                "content": "filefoo-content",
                "filename": str(tmpdir.join("mydir/mycfg")),
            },
        ]

        changed = apply_rsyslog_changes(
            configs=configs, def_fname="default.cfg", cfg_dir=str(tmpdir)
        )

        expected = [
            (tmpdir.join("default.cfg"), "*.* foohost\n"),
            (tmpdir.join("my.cfg"), "abc\n"),
            (tmpdir.join("mydir/mycfg"), "filefoo-content\n"),
        ]
        assert [str(f[0]) for f in expected] == changed
        actual = []
        for fname, _content in expected:
            util.load_text_file(fname)
            actual.append(
                (
                    fname,
                    util.load_text_file(str(fname)),
                )
            )
        assert expected == actual

    def test_repeat_def(self, tmpdir):
        configs = ["*.* foohost", "*.warn otherhost"]

        changed = apply_rsyslog_changes(
            configs=configs, def_fname="default.cfg", cfg_dir=str(tmpdir)
        )

        fname = tmpdir.join("default.cfg")
        assert changed == [str(fname)]

        expected_content = "\n".join([c for c in configs]) + "\n"
        found_content = util.load_text_file(str(fname))
        assert expected_content == found_content

    def test_multiline_content(self, tmpdir):
        configs = ["line1", "line2\nline3\n"]

        apply_rsyslog_changes(
            configs=configs, def_fname="default.cfg", cfg_dir=str(tmpdir)
        )

        fname = tmpdir.join("default.cfg")
        expected_content = "\n".join([c for c in configs])
        found_content = util.load_text_file(str(fname))
        assert expected_content == found_content


class TestParseRemotesLine:
    def test_valid_port(self):
        r = parse_remotes_line("foo:9")
        assert r.port == 9

    def test_invalid_port(self):
        with pytest.raises(ValueError):
            parse_remotes_line("*.* foo:abc")

    def test_valid_ipv6(self):
        r = parse_remotes_line("*.* [::1]")
        assert str(r) == "*.* @[::1]"

    def test_valid_ipv6_with_port(self):
        r = parse_remotes_line("*.* [::1]:100")
        assert r.port == 100
        assert r.addr == "::1"
        assert str(r) == "*.* @[::1]:100"

    def test_invalid_multiple_colon(self):
        with pytest.raises(ValueError):
            parse_remotes_line("*.* ::1:100")

    def test_name_in_string(self):
        r = parse_remotes_line("syslog.host", name="foobar")
        assert str(r) == "*.* @syslog.host # foobar"


class TestRemotesToSyslog:
    def test_simple(self):
        # str rendered line must appear in remotes_to_ryslog_cfg return
        mycfg = "*.* myhost"
        myline = str(parse_remotes_line(mycfg, name="myname"))
        r = remotes_to_rsyslog_cfg({"myname": mycfg})
        lines = r.splitlines()
        assert len(lines) == 1
        assert myline in lines

    def test_header_footer(self):
        header = "#foo head"
        footer = "#foo foot"
        r = remotes_to_rsyslog_cfg(
            {"myname": "*.* myhost"}, header=header, footer=footer
        )
        lines = r.splitlines()
        assert lines[0] == header
        assert lines[-1] == footer

    def test_with_empty_or_null(self):
        mycfg = "*.* myhost"
        myline = str(parse_remotes_line(mycfg, name="myname"))
        r = remotes_to_rsyslog_cfg(
            {"myname": mycfg, "removed": None, "removed2": ""}
        )
        lines = r.splitlines()
        assert len(lines) == 1
        assert myline in lines


class TestRsyslogSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        [
            ({"rsyslog": {"remotes": {"any": "string"}}}, None),
            (
                {"rsyslog": {"unknown": "a"}},
                "Additional properties are not allowed",
            ),
            ({"rsyslog": {"configs": [{"filename": "a"}]}}, ""),
            (
                {
                    "rsyslog": {
                        "configs": [
                            {"filename": "a", "content": "a", "a": "a"}
                        ]
                    }
                },
                "",
            ),
            (
                {"rsyslog": {"remotes": ["a"]}},
                r"\['a'\] is not of type 'object'",
            ),
            ({"rsyslog": {"remotes": "a"}}, "'a' is not of type 'object"),
            ({"rsyslog": {"service_reload_command": "a"}}, ""),
        ],
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        if error_msg is None:
            validate_cloudconfig_schema(config, get_schema(), strict=True)
        else:
            with pytest.raises(SchemaValidationError, match=error_msg):
                validate_cloudconfig_schema(config, get_schema(), strict=True)


class TestInvalidKeyType:
    @pytest.mark.parametrize(
        "config, error_msg",
        [
            (
                {"rsyslog": {"configs": 1}},
                (
                    "Invalid type for key `configs`. Expected type(s): "
                    "<class 'list'>. Current type: <class 'int'>"
                ),
            ),
            (
                {"rsyslog": {"configs": [], "config_dir": 1}},
                (
                    "Invalid type for key `config_dir`. Expected type(s): "
                    "<class 'str'>. Current type: <class 'int'>"
                ),
            ),
            (
                {"rsyslog": {"configs": [], "config_filename": True}},
                (
                    "Invalid type for key `config_filename`. Expected type(s):"
                    " <class 'str'>. Current type: <class 'bool'>"
                ),
            ),
            (
                {"rsyslog": {"service_reload_command": 3.14}},
                (
                    "Invalid type for key `service_reload_command`. "
                    "Expected type(s): (<class 'str'>, <class 'list'>). "
                    "Current type: <class 'float'>"
                ),
            ),
            (
                {"rsyslog": {"remotes": ["1", 2, 3.14]}},
                (
                    "Invalid type for key `remotes`. Expected type(s): "
                    "<class 'dict'>. Current type: <class 'list'>"
                ),
            ),
        ],
    )
    def test_invalid_key_types(self, config: dict, error_msg: Optional[str]):
        cloud = get_cloud(distro="ubuntu", metadata={})
        callable_ = partial(load_config, config, cloud.distro)
        if error_msg is None:
            callable_()
        else:
            with pytest.raises(ValueError, match=re.escape(error_msg)):
                callable_()


class TestInstallRsyslog:
    @mock.patch("cloudinit.config.cc_rsyslog.subp.which")
    def test_install_rsyslog_on_freebsd(self, m_which):
        config = {
            "install_rsyslog": True,
            "packages": ["rsyslog"],
            "check_exe": "rsyslogd",
        }
        # patch for ifconfig -a
        with mock.patch(
            "cloudinit.distros.networking.subp.subp", return_values=("", None)
        ):
            cloud = get_cloud(distro="freebsd", metadata={})
            m_which.return_value = None
            with mock.patch.object(
                cloud.distro, "install_packages"
            ) as m_install:
                handle("rsyslog", {"rsyslog": config}, cloud, [])
            m_which.assert_called_with(config["check_exe"])
            m_install.assert_called_with(config["packages"])

    @mock.patch("cloudinit.config.cc_rsyslog.util.is_BSD")
    @mock.patch("cloudinit.config.cc_rsyslog.subp.which")
    def test_no_install_rsyslog_with_check_exe(self, m_which, m_isbsd):
        config = {
            "install_rsyslog": True,
            "packages": ["rsyslog"],
            "check_exe": "rsyslogd",
        }
        cloud = get_cloud(distro="ubuntu", metadata={})
        m_isbsd.return_value = False
        m_which.return_value = "/usr/sbin/rsyslogd"
        with mock.patch.object(cloud.distro, "install_packages") as m_install:
            handle("rsyslog", {"rsyslog": config}, cloud, [])
        m_which.assert_called_with(config["check_exe"])
        m_install.assert_not_called()
