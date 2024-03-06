# This file is part of cloud-init. See LICENSE file for license information.

import os
import re
import shutil
import tempfile
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
from tests.unittests.helpers import TestCase, skipUnlessJsonSchema
from tests.unittests.util import get_cloud


class TestLoadConfig(TestCase):
    def setUp(self):
        super(TestLoadConfig, self).setUp()
        self.basecfg = {
            "config_filename": "20-cloud-config.conf",
            "config_dir": "/etc/rsyslog.d",
            "service_reload_command": "auto",
            "configs": [],
            "remotes": {},
            "check_exe": "rsyslogd",
            "packages": ["rsyslog"],
            "install_rsyslog": False,
        }
        self.bsdcfg = {
            "config_filename": "20-cloud-config.conf",
            "config_dir": "/usr/local/etc/rsyslog.d",
            "service_reload_command": "auto",
            "configs": [],
            "remotes": {},
            "check_exe": "rsyslogd",
            "packages": ["rsyslog"],
            "install_rsyslog": False,
        }

    def test_legacy_full(self, distro=None):
        cloud = get_cloud(distro="ubuntu", metadata={})
        found = load_config(
            {
                "rsyslog": ["*.* @192.168.1.1"],
                "rsyslog_dir": "mydir",
                "rsyslog_filename": "myfilename",
            },
            distro=cloud.distro,
        )
        self.basecfg.update(
            {
                "configs": ["*.* @192.168.1.1"],
                "config_dir": "mydir",
                "config_filename": "myfilename",
                "service_reload_command": "auto",
            }
        )

        self.assertEqual(found, self.basecfg)

    def test_legacy_defaults(self):
        cloud = get_cloud(distro="ubuntu", metadata={})
        found = load_config(
            {"rsyslog": ["*.* @192.168.1.1"]}, distro=cloud.distro
        )
        self.basecfg.update({"configs": ["*.* @192.168.1.1"]})
        self.assertEqual(found, self.basecfg)

    def test_new_defaults(self):
        cloud = get_cloud(distro="ubuntu", metadata={})
        self.assertEqual(load_config({}, distro=cloud.distro), self.basecfg)

    def test_new_bsd_defaults(self):
        # patch for ifconfig -a
        with mock.patch(
            "cloudinit.distros.networking.subp.subp", return_values=("", None)
        ):
            cloud = get_cloud(distro="freebsd", metadata={})
        self.assertEqual(load_config({}, distro=cloud.distro), self.bsdcfg)

    def test_new_configs(self):
        cfgs = ["*.* myhost", "*.* my2host"]
        cloud = get_cloud(distro="ubuntu", metadata={})
        self.basecfg.update({"configs": cfgs})
        self.assertEqual(
            load_config({"rsyslog": {"configs": cfgs}}, distro=cloud.distro),
            self.basecfg,
        )


class TestApplyChanges(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def test_simple(self):
        cfgline = "*.* foohost"
        changed = apply_rsyslog_changes(
            configs=[cfgline], def_fname="foo.cfg", cfg_dir=self.tmp
        )

        fname = os.path.join(self.tmp, "foo.cfg")
        self.assertEqual([fname], changed)
        self.assertEqual(util.load_text_file(fname), cfgline + "\n")

    def test_multiple_files(self):
        configs = [
            "*.* foohost",
            {"content": "abc", "filename": "my.cfg"},
            {
                "content": "filefoo-content",
                "filename": os.path.join(self.tmp, "mydir/mycfg"),
            },
        ]

        changed = apply_rsyslog_changes(
            configs=configs, def_fname="default.cfg", cfg_dir=self.tmp
        )

        expected = [
            (os.path.join(self.tmp, "default.cfg"), "*.* foohost\n"),
            (os.path.join(self.tmp, "my.cfg"), "abc\n"),
            (os.path.join(self.tmp, "mydir/mycfg"), "filefoo-content\n"),
        ]
        self.assertEqual([f[0] for f in expected], changed)
        actual = []
        for fname, _content in expected:
            util.load_text_file(fname)
            actual.append(
                (
                    fname,
                    util.load_text_file(fname),
                )
            )
        self.assertEqual(expected, actual)

    def test_repeat_def(self):
        configs = ["*.* foohost", "*.warn otherhost"]

        changed = apply_rsyslog_changes(
            configs=configs, def_fname="default.cfg", cfg_dir=self.tmp
        )

        fname = os.path.join(self.tmp, "default.cfg")
        self.assertEqual([fname], changed)

        expected_content = "\n".join([c for c in configs]) + "\n"
        found_content = util.load_text_file(fname)
        self.assertEqual(expected_content, found_content)

    def test_multiline_content(self):
        configs = ["line1", "line2\nline3\n"]

        apply_rsyslog_changes(
            configs=configs, def_fname="default.cfg", cfg_dir=self.tmp
        )

        fname = os.path.join(self.tmp, "default.cfg")
        expected_content = "\n".join([c for c in configs])
        found_content = util.load_text_file(fname)
        self.assertEqual(expected_content, found_content)


class TestParseRemotesLine(TestCase):
    def test_valid_port(self):
        r = parse_remotes_line("foo:9")
        self.assertEqual(9, r.port)

    def test_invalid_port(self):
        with self.assertRaises(ValueError):
            parse_remotes_line("*.* foo:abc")

    def test_valid_ipv6(self):
        r = parse_remotes_line("*.* [::1]")
        self.assertEqual("*.* @[::1]", str(r))

    def test_valid_ipv6_with_port(self):
        r = parse_remotes_line("*.* [::1]:100")
        self.assertEqual(r.port, 100)
        self.assertEqual(r.addr, "::1")
        self.assertEqual("*.* @[::1]:100", str(r))

    def test_invalid_multiple_colon(self):
        with self.assertRaises(ValueError):
            parse_remotes_line("*.* ::1:100")

    def test_name_in_string(self):
        r = parse_remotes_line("syslog.host", name="foobar")
        self.assertEqual("*.* @syslog.host # foobar", str(r))


class TestRemotesToSyslog(TestCase):
    def test_simple(self):
        # str rendered line must appear in remotes_to_ryslog_cfg return
        mycfg = "*.* myhost"
        myline = str(parse_remotes_line(mycfg, name="myname"))
        r = remotes_to_rsyslog_cfg({"myname": mycfg})
        lines = r.splitlines()
        self.assertEqual(1, len(lines))
        self.assertTrue(myline in r.splitlines())

    def test_header_footer(self):
        header = "#foo head"
        footer = "#foo foot"
        r = remotes_to_rsyslog_cfg(
            {"myname": "*.* myhost"}, header=header, footer=footer
        )
        lines = r.splitlines()
        self.assertTrue(header, lines[0])
        self.assertTrue(footer, lines[-1])

    def test_with_empty_or_null(self):
        mycfg = "*.* myhost"
        myline = str(parse_remotes_line(mycfg, name="myname"))
        r = remotes_to_rsyslog_cfg(
            {"myname": mycfg, "removed": None, "removed2": ""}
        )
        lines = r.splitlines()
        self.assertEqual(1, len(lines))
        self.assertTrue(myline in r.splitlines())


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


class TestInstallRsyslog(TestCase):
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
                handle("rsyslog", {"rsyslog": config}, cloud, None)
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
            handle("rsyslog", {"rsyslog": config}, cloud, None)
        m_which.assert_called_with(config["check_exe"])
        m_install.assert_not_called()
