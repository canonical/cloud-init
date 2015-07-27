import os
import shutil
import tempfile

from cloudinit.config.cc_rsyslog import (
    load_config, DEF_FILENAME, DEF_DIR, DEF_RELOAD, apply_rsyslog_changes)
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
        }

    def test_legacy_full(self):
        found = load_config({
            'rsyslog': ['*.* @192.168.1.1'],
            'rsyslog_dir': "mydir",
            'rsyslog_filename': "myfilename"})
        expected = {
            'configs': ['*.* @192.168.1.1'],
            'config_dir': "mydir",
            'config_filename': 'myfilename',
            'service_reload_command': 'auto'}
        self.assertEqual(found, expected)

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

        changed = apply_rsyslog_changes(
            configs=configs, def_fname="default.cfg", cfg_dir=self.tmp)

        fname = os.path.join(self.tmp, "default.cfg")
        expected_content = '\n'.join([c for c in configs]) + '\n'
        found_content = util.load_file(fname)
        self.assertEqual(expected_content, found_content)
