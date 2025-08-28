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
from tests.unittests.helpers import skipUnlessJsonSchema
from tests.unittests.util import get_cloud


# ----------------------------
# LoadConfig Tests
# ----------------------------

@pytest.fixture
def basecfg():
    return {
        "config_filename": "20-cloud-config.conf",
        "config_dir": "/etc/rsyslog.d",
        "service_reload_command": "auto",
        "configs": [],
        "remotes": {},
        "check_exe": "rsyslogd",
        "packages": ["rsyslog"],
        "install_rsyslog": False,
    }

@pytest.fixture
def bsdcfg():
    return {
        "config_filename": "20-cloud-config.conf",
        "config_dir": "/usr/local/etc/rsyslog.d",
        "service_reload_command": "auto",
        "configs": [],
        "remotes": {},
        "check_exe": "rsyslogd",
        "packages": ["rsyslog"],
        "install_rsyslog": False,
    }


def test_legacy_full(basecfg):
    cloud = get_cloud(distro="ubuntu", metadata={})
    found = load_config(
        {
            "rsyslog": ["*.* @192.168.1.1"],
            "rsyslog_dir": "mydir",
            "rsyslog_filename": "myfilename",
        },
        distro=cloud.distro,
    )
    basecfg.update(
        {
            "configs": ["*.* @192.168.1.1"],
            "config_dir": "mydir",
            "config_filename": "myfilename",
            "service_reload_command": "auto",
        }
    )
    assert found == basecfg


def test_legacy_defaults(basecfg):
    cloud = get_cloud(distro="ubuntu", metadata={})
    found = load_config({"rsyslog": ["*.* @192.168.1.1"]}, distro=cloud.distro)
    basecfg.update({"configs": ["*.* @192.168.1.1"]})
    assert found == basecfg


def test_new_defaults(basecfg):
    cloud = get_cloud(distro="ubuntu", metadata={})
    assert load_config({}, distro=cloud.distro) == basecfg


def test_new_bsd_defaults(bsdcfg):
    with mock.patch("cloudinit.distros.networking.subp.subp", return_values=("", None)):
        cloud = get_cloud(distro="freebsd", metadata={})
    assert load_config({}, distro=cloud.distro) == bsdcfg


def test_new_configs(basecfg):
    cfgs = ["*.* myhost", "*.* my2host"]
    cloud = get_cloud(distro="ubuntu", metadata={})
    basecfg.update({"configs": cfgs})
    assert load_config({"rsyslog": {"configs": cfgs}}, distro=cloud.distro) == basecfg


# ----------------------------
# ApplyChanges Tests
# ----------------------------

@pytest.fixture
def tmpdir_path(tmp_path):
    return str(tmp_path)


def test_apply_simple(tmpdir_path):
    cfgline = "*.* foohost"
    changed = apply_rsyslog_changes(configs=[cfgline], def_fname="foo.cfg", cfg_dir=tmpdir_path)

    fname = os.path.join(tmpdir_path, "foo.cfg")
    assert [fname] == changed
    assert util.load_text_file(fname) == cfgline + "\n"


def test_apply_multiple_files(tmpdir_path):
    configs = [
        "*.* foohost",
        {"content": "abc", "filename": "my.cfg"},
        {"content": "filefoo-content", "filename": os.path.join(tmpdir_path, "mydir/mycfg")},
    ]

    changed = apply_rsyslog_changes(configs=configs, def_fname="default.cfg", cfg_dir=tmpdir_path)

    expected = [
        (os.path.join(tmpdir_path, "default.cfg"), "*.* foohost\n"),
        (os.path.join(tmpdir_path, "my.cfg"), "abc\n"),
        (os.path.join(tmpdir_path, "mydir/mycfg"), "filefoo-content\n"),
    ]
    assert [f[0] for f in expected] == changed

    actual = [(fname, util.load_text_file(fname)) for fname, _ in expected]
    assert expected == actual


def test_apply_repeat_def(tmpdir_path):
    configs = ["*.* foohost", "*.warn otherhost"]
    changed = apply_rsyslog_changes(configs=configs, def_fname="default.cfg", cfg_dir=tmpdir_path)

    fname = os.path.join(tmpdir_path, "default.cfg")
    assert [fname] == changed

    expected_content = "\n".join([c for c in configs]) + "\n"
    assert util.load_text_file(fname) == expected_content


def test_apply_multiline_content(tmpdir_path):
    configs = ["line1", "line2\nline3\n"]
    apply_rsyslog_changes(configs=configs, def_fname="default.cfg", cfg_dir=tmpdir_path)

    fname = os.path.join(tmpdir_path, "default.cfg")
    expected_content = "\n".join([c for c in configs])
    assert util.load_text_file(fname) == expected_content


# ----------------------------
# ParseRemotesLine Tests
# ----------------------------

def test_valid_port():
    r = parse_remotes_line("foo:9")
    assert r.port == 9


def test_invalid_port():
    with pytest.raises(ValueError):
        parse_remotes_line("*.* foo:abc")


def test_valid_ipv6():
    r = parse_remotes_line("*.* [::1]")
    assert str(r) == "*.* @[::1]"


def test_valid_ipv6_with_port():
    r = parse_remotes_line("*.* [::1]:100")
    assert r.port == 100
    assert r.addr == "::1"
    assert str(r) == "*.* @[::1]:100"


def test_invalid_multiple_colon():
    with pytest.raises(ValueError):
        parse_remotes_line("*.* ::1:100")


def test_name_in_string():
    r = parse_remotes_line("syslog.host", name="foobar")
    assert str(r) == "*.* @syslog.host # foobar"


# ----------------------------
# RemotesToSyslog Tests
# ----------------------------

def test_remotes_to_syslog_simple():
    mycfg = "*.* myhost"
    myline = str(parse_remotes_line(mycfg, name="myname"))
    r = remotes_to_rsyslog_cfg({"myname": mycfg})
    lines = r.splitlines()
    assert 1 == len(lines)
    assert myline in lines


def test_remotes_to_syslog_header_footer():
    header = "#foo head"
    footer = "#foo foot"
    r = remotes_to_rsyslog_cfg({"myname": "*.* myhost"}, header=header, footer=footer)
    lines = r.splitlines()
    assert header == lines[0]
    assert footer == lines[-1]


def test_remotes_to_syslog_with_empty_or_null():
    mycfg = "*.* myhost"
    myline = str(parse_remotes_line(mycfg, name="myname"))
    r = remotes_to_rsyslog_cfg({"myname": mycfg, "removed": None, "removed2": ""})
    lines = r.splitlines()
    assert 1 == len(lines)
    assert myline in lines


# ----------------------------
# Schema Tests
# ----------------------------

@pytest.mark.parametrize(
    "config, error_msg",
    [
        ({"rsyslog": {"remotes": {"any": "string"}}}, None),
        ({"rsyslog": {"unknown": "a"}}, "Additional properties are not allowed"),
        ({"rsyslog": {"configs": [{"filename": "a"}]}}, ""),
        ({"rsyslog": {"configs": [{"filename": "a", "content": "a", "a": "a"}]}}, ""),
        ({"rsyslog": {"remotes": ["a"]}}, r"\['a'\] is not of type 'object'"),
        ({"rsyslog": {"remotes": "a"}}, "'a' is not of type 'object"),
        ({"rsyslog": {"service_reload_command": "a"}}, ""),
    ],
)
@skipUnlessJsonSchema()
def test_schema_validation(config, error_msg):
    if error_msg is None:
        validate_cloudconfig_schema(config, get_schema(), strict=True)
    else:
        with pytest.raises(SchemaValidationError, match=error_msg):
            validate_cloudconfig_schema(config, get_schema(), strict=True)


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
def test_invalid_key_types(config: dict, error_msg: Optional[str]):
    cloud = get_cloud(distro="ubuntu", metadata={})
    callable_ = partial(load_config, config, cloud.distro)
    if error_msg is None:
        callable_()
    else:
        with pytest.raises(ValueError, match=re.escape(error_msg)):
            callable_()


# ----------------------------
# InstallRsyslog Tests
# ----------------------------

@mock.patch("cloudinit.config.cc_rsyslog.subp.which")
def test_install_rsyslog_on_freebsd(m_which):
    config = {
        "install_rsyslog": True,
        "packages": ["rsyslog"],
        "check_exe": "rsyslogd",
    }
    with mock.patch("cloudinit.distros.networking.subp.subp", return_values=("", None)):
        cloud = get_cloud(distro="freebsd", metadata={})
        m_which.return_value = None
        with mock.patch.object(cloud.distro, "install_packages") as m_install:
            handle("rsyslog", {"rsyslog": config}, cloud, [])
        m_which.assert_called_with(config["check_exe"])
        m_install.assert_called_with(config["packages"])


@mock.patch("cloudinit.config.cc_rsyslog.util.is_BSD")
@mock.patch("cloudinit.config.cc_rsyslog.subp.which")
def test_no_install_rsyslog_with_check_exe(m_which, m_isbsd):
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
