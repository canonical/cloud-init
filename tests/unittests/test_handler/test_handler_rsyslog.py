# This file is part of cloud-init. See LICENSE file for license information.

import os
import shutil
import tempfile

from cloudinit.config.cc_rsyslog import (
    apply_rsyslog_changes, DEF_DIR, DEF_FILENAME, DEF_RELOAD, load_config,
    parse_remotes_line, remotes_to_rsyslog_cfg)
from cloudinit import util

from .. import helpers as t_help


class TestLoadConfig(t_help.TestCase):
    def setUp(self):
        super(TestLoadConfig, self).setUp()
        self.basecfg = {
            'config_filename': DEF_FILENAME,
            'config_dir': DEF_DIR,
            'service_reload_command': DEF_RELOAD,
            'configs': [],
            'remotes': {},
        }

    def test_legacy_full(self):
        found = load_config({
            'rsyslog': ['*.* @192.168.1.1'],
            'rsyslog_dir': "mydir",
            'rsyslog_filename': "myfilename"})
        self.basecfg.update({
            'configs': ['*.* @192.168.1.1'],
            'config_dir': "mydir",
            'config_filename': 'myfilename',
            'service_reload_command': 'auto'}
        )

        self.assertEqual(found, self.basecfg)

    def test_legacy_defaults(self):
        found = load_config({
            'rsyslog': ['*.* @192.168.1.1']})
        self.basecfg.update({
            'configs': ['*.* @192.168.1.1']})
        self.assertEqual(found, self.basecfg)

    def test_new_defaults(self):
        self.assertEqual(load_config({}), self.basecfg)

    def test_new_configs(self):
        cfgs = ['*.* myhost', '*.* my2host']
        self.basecfg.update({'configs': cfgs})
        self.assertEqual(
            load_config({'rsyslog': {'configs': cfgs}}),
            self.basecfg)


class TestApplyChanges(t_help.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def test_simple(self):
        cfgline = "*.* foohost"
        changed = apply_rsyslog_changes(
            configs=[cfgline], def_fname="foo.cfg", cfg_dir=self.tmp)

        fname = os.path.join(self.tmp, "foo.cfg")
        self.assertEqual([fname], changed)
        self.assertEqual(
            util.load_file(fname), cfgline + "\n")

    def test_multiple_files(self):
        configs = [
            '*.* foohost',
            {'content': 'abc', 'filename': 'my.cfg'},
            {'content': 'filefoo-content',
             'filename': os.path.join(self.tmp, 'mydir/mycfg')},
        ]

        changed = apply_rsyslog_changes(
            configs=configs, def_fname="default.cfg", cfg_dir=self.tmp)

        expected = [
            (os.path.join(self.tmp, "default.cfg"),
             "*.* foohost\n"),
            (os.path.join(self.tmp, "my.cfg"), "abc\n"),
            (os.path.join(self.tmp, "mydir/mycfg"), "filefoo-content\n"),
        ]
        self.assertEqual([f[0] for f in expected], changed)
        actual = []
        for fname, _content in expected:
            util.load_file(fname)
            actual.append((fname, util.load_file(fname),))
        self.assertEqual(expected, actual)

    def test_repeat_def(self):
        configs = ['*.* foohost', "*.warn otherhost"]

        changed = apply_rsyslog_changes(
            configs=configs, def_fname="default.cfg", cfg_dir=self.tmp)

        fname = os.path.join(self.tmp, "default.cfg")
        self.assertEqual([fname], changed)

        expected_content = '\n'.join([c for c in configs]) + '\n'
        found_content = util.load_file(fname)
        self.assertEqual(expected_content, found_content)

    def test_multiline_content(self):
        configs = ['line1', 'line2\nline3\n']

        apply_rsyslog_changes(
            configs=configs, def_fname="default.cfg", cfg_dir=self.tmp)

        fname = os.path.join(self.tmp, "default.cfg")
        expected_content = '\n'.join([c for c in configs])
        found_content = util.load_file(fname)
        self.assertEqual(expected_content, found_content)


class TestParseRemotesLine(t_help.TestCase):
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


class TestRemotesToSyslog(t_help.TestCase):
    def test_simple(self):
        # str rendered line must appear in remotes_to_ryslog_cfg return
        mycfg = "*.* myhost"
        myline = str(parse_remotes_line(mycfg, name="myname"))
        r = remotes_to_rsyslog_cfg({'myname': mycfg})
        lines = r.splitlines()
        self.assertEqual(1, len(lines))
        self.assertTrue(myline in r.splitlines())

    def test_header_footer(self):
        header = "#foo head"
        footer = "#foo foot"
        r = remotes_to_rsyslog_cfg(
            {'myname': "*.* myhost"}, header=header, footer=footer)
        lines = r.splitlines()
        self.assertTrue(header, lines[0])
        self.assertTrue(footer, lines[-1])

    def test_with_empty_or_null(self):
        mycfg = "*.* myhost"
        myline = str(parse_remotes_line(mycfg, name="myname"))
        r = remotes_to_rsyslog_cfg(
            {'myname': mycfg, 'removed': None, 'removed2': ""})
        lines = r.splitlines()
        self.assertEqual(1, len(lines))
        self.assertTrue(myline in r.splitlines())

# vi: ts=4 expandtab
