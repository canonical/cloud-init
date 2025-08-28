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

# -------------------
# Test LoadConfig
# -------------------

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


def test_legacy_full():
    cloud = get_cloud(distro="ubuntu", metadata={})
    found = load_config(
        {
            "rsyslog": ["*.* @192.168.1.1"],
            "rsyslog_dir": "mydir",
            "rsyslog_filename": "myfilename",
        },
        distro=cloud.distro,
    )
    cfg = BASECFG.copy()
    cfg.update({
        "configs": ["*.* @192.168.1.1"],
        "config_dir": "mydir",
        "config_filename": "myfilename",
    })
    assert found == cfg


def test_legacy_defaults():
    cloud = get_cloud(distro="ubuntu", metadata={})
    found = load_config({"rsyslog": ["*.* @192.168.1.1"]}, distro=cloud.distro)
    cfg = BASECFG.copy()
    cfg.update({"configs": ["*.* @192.168.1.1"]})
    assert found == cfg


def test_new_defaults():
    cloud = get_cloud(distro="ubuntu", metadata={})
    assert load_config({}, distro=cloud.distro) == BASECFG


def test_new_bsd_defaults():
    with mock.patch("cloudinit.distros.networking.subp.subp", return_values=("", None)):
        cloud = get_cloud(distro="freebsd", metadata={})
    assert load_config({}, distro=cloud.distro) == BSDCFG


def test_new_configs():
    cfgs = ["*.* myhost", "*.* my2host"]
    cloud = get_cloud(distro="ubuntu", metadata={})
    cfg = BASECFG.copy()
    cfg.update({"configs": cfgs})
    assert load_config({"rsyslog": {"configs": cfgs}}, distro=cloud.distro) == cfg


# -------------------
# Test ApplyChanges
# -------------------

@pytest.fixture
def tmp_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d)


def test_apply_simple(tmp_dir):
    cfgline = "*.* foohost"
    changed = apply_rsyslog_changes(configs=[cfgline], def_fname="foo.cfg", cfg_dir=tmp_dir)
    fname = os.path.join(tmp_dir, "foo.cfg")
    assert changed == [fname]
    assert util.load_text_file(fname) == cfgline + "\n"


def test_apply_multiple_files(tmp_dir):
    configs = [
        "*.* foohost",
        {"content": "abc", "filename": "my.cfg"},
        {"content": "filefoo-content", "filename": os.path.join(tmp_dir, "mydir/mycfg")},
    ]
    changed = apply_rsyslog_changes(configs=configs, def_fname="default.cfg", cfg_dir=tmp_dir)
    expected = [
        (os.path.join(tmp_dir, "default.cfg"), "*.* foohost\n"),
        (os.path.join(tmp_dir, "my.cfg"), "abc\n"),
        (os.path.join(tmp_dir, "mydir/mycfg"), "filefoo-content\n"),
    ]
    assert [f[0] for f in expected] == changed
    for fname, content in expected:
        assert util.load_text_file(fname) == content


def test_apply_repeat_def(tmp_dir):
    configs = ["*.* foohost", "*.warn otherhost"]
    changed = apply_rsyslog_changes(configs=configs, def_fname="default.cfg", cfg_dir=tmp_dir)
    fname = os.path.join(tmp_dir, "default.cfg")
    assert changed == [fname]
    expected_content = "\n".join(configs) + "\n"
    assert util.load_text_file(fname) == expected_content


def test_apply_multiline_content(tmp_dir):
    configs = ["line1", "line2\nline3\n"]
    apply_rsyslog_changes(configs=configs, def_fname="default.cfg", cfg_dir=tmp_dir)
    fname = os.path.join(tmp_dir, "default.cfg")
    expected_content = "\n".join(configs)
    assert util.load_text_file(fname) == expected_content


# -------------------
# Test parse_remotes_line
# -------------------

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


# -------------------
# Test remotes_to_rsyslog_cfg
# -------------------

def test_remotes_to_syslog_simple():
    mycfg = "*.* myhost"
    myline = str(parse_remotes_line(mycfg, name="myname"))
    r = remotes_to_rsyslog_cfg({"myname": mycfg})
    lines = r.splitlines()
    assert len(lines) == 1
    assert myline in lines


def test_remotes_to_syslog_header_footer():
    header = "#foo head"
    footer = "#foo foot"
    r = remotes_to_rsyslog_cfg({"myname": "*.* myhost"}, header=header, footer=footer)
    lines = r.splitlines()
    assert lines[0] == header
    assert lines[-1] == footer


def test_remotes_to_syslog_with_empty_or_null():
    mycfg = "*.* myhost"
    myline = str(parse_remotes_line(mycfg, name="myname"))
    r = remotes_to_rsyslog_cfg({"myname": mycfg, "removed": None, "removed2": ""})
    lines = r.splitlines()
    assert len(lines) == 1
    assert myline in lines


# -------------------
# Test schema validation
# -------------------

class TestRsyslogSchema:
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
    def test_schema_validation(self, config, error_msg):
        if error_msg is None:
            validate_cloudconfig_schema(config, get_schema(), strict=True)
        else:
            with pytest.raises(SchemaValidationError, match=error_msg):
                validate_cloudconfig_schema(config, get_schema(), strict=True)


# -------------------
# Test invalid key types
# -------------------

@pytest.mark.parametrize(
    "config,error_msg",
    [
        ({"rsyslog": {"configs": 1}},
         "Invalid type for key `configs`. Expected type(s): <class 'list'>. Current type: <class 'int'>"),
        ({"rsyslog": {"configs": [], "config_dir": 1}},
         "Invalid type for key `config_dir`. Expected type(s): <class 'str'>. Current type: <class 'int'>"),
        ({"rsyslog": {"configs": [], "config_filename": True}},
         "Invalid type for key `config_filename`. Expected type(s): <class 'str'>. Current type: <class 'bool'>"),
        ({"rsyslog": {"service_reload_command": 3.14}},
         "Invalid type for key `service_reload_command`. Expected type(s): (<class 'str'>, <class 'list'>). Current type: <class 'float'>"),
        ({"rsyslog": {"remotes": ["1", 2, 3.14]}},
         "Invalid type for key `remotes`. Expected type(s): <class 'dict'>. Current type: <class 'list'>"),
    ],
)
def test_invalid_key_types(config, error_msg):
    cloud = get_cloud(distro="ubuntu", metadata={})
    callable_ = partial(load_config, config, cloud.distro)
    if error_msg is None:
        callable_()
    else:
        with pytest.raises(ValueError, match=re.escape(error_msg)):
            callable_()


# -------------------
# Test install rsyslog
# -------------------

def test_install_rsyslog_on_freebsd():
    config = {"install_rsyslog": True, "packages": ["rsyslog"], "check_exe": "rsyslogd"}
    with mock.patch("cloudinit.distros.networking.subp.subp", return_values=("", None)):
        cloud = get_cloud(distro="freebsd", metadata={})
        with mock.patch("cloudinit.config.cc_rsyslog.subp.which", return_value=None) as m_which:
            with mock.patch.object(cloud.distro, "install_packages") as m_install:
                handle("rsyslog", {"rsyslog": config}, cloud, [])
            m_which.assert_called_with(config["check_exe"])
            m_install.assert_called_with(config["packages"])


def test_no_install_rsyslog_with_check_exe():
    config = {"install_rsyslog": True, "packages": ["rsyslog"], "check_exe": "rsyslogd"}
    cloud = get_cloud(distro="ubuntu", metadata={})
    with mock.patch("cloudinit.config.cc_rsyslog.util.is_BSD", return_value=False), \
         mock.patch("cloudinit.config.cc_rsyslog.subp.which", return_value="/usr/sbin/rsyslogd") as m_which, \
         mock.patch.object(cloud.distro, "install_packages") as m_install:
        handle("rsyslog", {"rsyslog": config}, cloud, [])
    m_which.assert_called_with(config["check_exe"])
    m_install.assert_not_called()
