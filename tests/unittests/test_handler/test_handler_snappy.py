from cloudinit.config.cc_snappy import (
    makeop, get_package_ops, render_snap_op)
from cloudinit import util
from .. import helpers as t_help

import os
import shutil
import tempfile
import yaml

ALLOWED = (dict, list, int, str)


class TestInstallPackages(t_help.TestCase):
    def setUp(self):
        super(TestInstallPackages, self).setUp()
        self.unapply = []

        # by default 'which' has nothing in its path
        self.apply_patches([(util, 'subp', self._subp)])
        self.subp_called = []
        self.snapcmds = []
        self.tmp = tempfile.mkdtemp(prefix="TestInstallPackages")

    def tearDown(self):
        apply_patches([i for i in reversed(self.unapply)])
        shutil.rmtree(self.tmp)

    def apply_patches(self, patches):
        ret = apply_patches(patches)
        self.unapply += ret

    def populate_tmp(self, files):
        return t_help.populate_dir(self.tmp, files)

    def _subp(self, *args, **kwargs):
        # supports subp calling with cmd as args or kwargs
        if 'args' not in kwargs:
            kwargs['args'] = args[0]
        self.subp_called.append(kwargs)
        snap_cmds = []
        args = kwargs['args']
        # here we basically parse the snappy command invoked
        # and append to snapcmds a list of (mode, pkg, config)
        if args[0:2] == ['snappy', 'config']:
            if args[3] == "-":
                config = kwargs.get('data', '')
            else:
                with open(args[3], "rb") as fp:
                    config = yaml.safe_load(fp.read())
            self.snapcmds.append(['config', args[2], config])
        elif args[0:2] == ['snappy', 'install']:
            config = None
            pkg = None
            for arg in args[2:]:
                if arg.startswith("--config="):
                    cfgfile = arg.partition("=")[2]
                    if cfgfile == "-":
                        config = kwargs.get('data', '')
                    elif cfgfile:
                        with open(cfgfile, "rb") as fp:
                            config = yaml.safe_load(fp.read())
                elif not pkg and not arg.startswith("-"):
                    pkg = arg
            self.snapcmds.append(['install', pkg, config])

    def test_package_ops_1(self):
        ret = get_package_ops(
            packages=['pkg1', 'pkg2', 'pkg3'],
            configs={'pkg2': b'mycfg2'}, installed=[])
        self.assertEqual(
            ret, [makeop('install', 'pkg1', None, None),
                  makeop('install', 'pkg2', b'mycfg2', None),
                  makeop('install', 'pkg3', None, None)])

    def test_package_ops_config_only(self):
        ret = get_package_ops(
            packages=None,
            configs={'pkg2': b'mycfg2'}, installed=['pkg1', 'pkg2'])
        self.assertEqual(
            ret, [makeop('config', 'pkg2', b'mycfg2')])

    def test_package_ops_install_and_config(self):
        ret = get_package_ops(
            packages=['pkg3', 'pkg2'],
            configs={'pkg2': b'mycfg2', 'xinstalled': b'xcfg'},
            installed=['xinstalled'])
        self.assertEqual(
            ret, [makeop('install', 'pkg3'),
                  makeop('install', 'pkg2', b'mycfg2'),
                  makeop('config', 'xinstalled', b'xcfg')])

    def test_package_ops_install_long_config_short(self):
        # a package can be installed by full name, but have config by short
        cfg = {'k1': 'k2'}
        ret = get_package_ops(
            packages=['config-example.canonical'],
            configs={'config-example': cfg}, installed=[])
        self.assertEqual(
            ret, [makeop('install', 'config-example.canonical', cfg)])

    def test_package_ops_with_file(self):
        self.populate_tmp(
            {"snapf1.snap": b"foo1", "snapf1.config": b"snapf1cfg",
             "snapf2.snap": b"foo2", "foo.bar": "ignored"})
        ret = get_package_ops(
            packages=['pkg1'], configs={}, installed=[], fspath=self.tmp)
        self.assertEqual(
            ret,
            [makeop_tmpd(self.tmp, 'install', 'snapf1', path="snapf1.snap",
                         cfgfile="snapf1.config"),
             makeop_tmpd(self.tmp, 'install', 'snapf2', path="snapf2.snap"),
             makeop('install', 'pkg1')])

    def test_package_ops_common_filename(self):
        # fish package name from filename
        # package names likely look like: pkgname.namespace_version_arch.snap
        fname = "xkcd-webserver.canonical_0.3.4_all.snap"
        name = "xkcd-webserver.canonical"
        shortname = "xkcd-webserver"

        # find filenames
        self.populate_tmp(
            {"pkg-ws.smoser_0.3.4_all.snap": "pkg-ws-snapdata",
             "pkg-ws.config": "pkg-ws-config",
             "pkg1.smoser_1.2.3_all.snap": "pkg1.snapdata",
             "pkg1.smoser.config": "pkg1.smoser.config-data",
             "pkg1.config": "pkg1.config-data",
             "pkg2.smoser_0.0_amd64.snap": "pkg2-snapdata",
             "pkg2.smoser_0.0_amd64.config": "pkg2.config",
            })

        ret = get_package_ops(
            packages=[], configs={}, installed=[], fspath=self.tmp)
        raise Exception("ret: %s" % ret)
        self.assertEqual(
            ret,
            [makeop_tmpd(self.tmp, 'install', 'pkg-ws.smoser',
                         path="pkg-ws.smoser_0.3.4_all.snap",
                         cfgfile="pkg-ws.config"),
             makeop_tmpd(self.tmp, 'install', 'pkg1.smoser',
                         path="pkg1.smoser_1.2.3_all.snap",
                         cfgfile="pkg1.smoser.config"),
             makeop_tmpd(self.tmp, 'install', 'pkg2.smoser',
                         path="pkg2.smoser_0.0_amd64.snap",
                         cfgfile="pkg2.smoser_0.0_amd64.config"),
             ])

    def test_package_ops_config_overrides_file(self):
        # config data overrides local file .config
        self.populate_tmp(
            {"snapf1.snap": b"foo1", "snapf1.config": b"snapf1cfg"})
        ret = get_package_ops(
            packages=[], configs={'snapf1': 'snapf1cfg-config'},
            installed=[], fspath=self.tmp)
        self.assertEqual(
            ret, [makeop_tmpd(self.tmp, 'install', 'snapf1',
                              path="snapf1.snap", config="snapf1cfg-config")])

    def test_package_ops_namespacing(self):
        cfgs = {
            'config-example': {'k1': 'v1'},
            'pkg1': {'p1': 'p2'},
            'ubuntu-core': {'c1': 'c2'},
            'notinstalled.smoser': {'s1': 's2'},
        }
        cfg = {'config-example-k1': 'config-example-k2'}
        ret = get_package_ops(
            packages=['config-example.canonical'], configs=cfgs,
            installed=['config-example.smoser', 'pkg1.canonical',
                       'ubuntu-core'])

        expected_configs = [
            makeop('config', 'pkg1', config=cfgs['pkg1']),
            makeop('config', 'ubuntu-core', config=cfgs['ubuntu-core'])]
        expected_installs = [
            makeop('install', 'config-example.canonical',
                   config=cfgs['config-example'])]

        installs = [i for i in ret if i['op'] == 'install']
        configs = [c for c in ret if c['op'] == 'config']

        self.assertEqual(installs, expected_installs)
        # configs are not ordered
        self.assertEqual(len(configs), len(expected_configs))
        self.assertTrue(all(found in expected_configs for found in configs))

    def test_render_op_localsnap(self):
        self.populate_tmp({"snapf1.snap": b"foo1"})
        op = makeop_tmpd(self.tmp, 'install', 'snapf1',
                         path='snapf1.snap')
        render_snap_op(**op)
        self.assertEqual(
            self.snapcmds, [['install', op['path'], None]])

    def test_render_op_localsnap_localconfig(self):
        self.populate_tmp(
            {"snapf1.snap": b"foo1", 'snapf1.config': b'snapf1cfg'})
        op = makeop_tmpd(self.tmp, 'install', 'snapf1',
                         path='snapf1.snap', cfgfile='snapf1.config')
        render_snap_op(**op)
        self.assertEqual(
            self.snapcmds, [['install', op['path'], 'snapf1cfg']])

    def test_render_op_snap(self):
        op = makeop('install', 'snapf1')
        render_snap_op(**op)
        self.assertEqual(
            self.snapcmds, [['install', 'snapf1', None]])

    def test_render_op_snap_config(self):
        mycfg = {'key1': 'value1'}
        name = "snapf1"
        op = makeop('install', name, config=mycfg)
        render_snap_op(**op)
        self.assertEqual(
            self.snapcmds, [['install', name, {'config': {name: mycfg}}]])

    def test_render_op_config_bytes(self):
        name = "snapf1"
        mycfg = b'myconfig'
        op = makeop('config', name, config=mycfg)
        render_snap_op(**op)
        self.assertEqual(
            self.snapcmds, [['config', 'snapf1', {'config': {name: mycfg}}]])

    def test_render_op_config_string(self):
        name = 'snapf1'
        mycfg = 'myconfig: foo\nhisconfig: bar\n'
        op = makeop('config', name, config=mycfg)
        render_snap_op(**op)
        self.assertEqual(
            self.snapcmds, [['config', 'snapf1', {'config': {name: mycfg}}]])

    def test_render_op_config_dict(self):
        # config entry for package can be a dict, not a string blob
        mycfg = {'foo': 'bar'}
        name = 'snapf1'
        op = makeop('config', name, config=mycfg)
        render_snap_op(**op)
        # snapcmds is a list of 3-entry lists. data_found will be the
        # blob of data in the file in 'snappy install --config=<file>'
        data_found = self.snapcmds[0][2]
        self.assertEqual(mycfg, data_found['config'][name])

    def test_render_op_config_list(self):
        # config entry for package can be a list, not a string blob
        mycfg = ['foo', 'bar', 'wark', {'f1': 'b1'}]
        name = "snapf1"
        op = makeop('config', name, config=mycfg)
        render_snap_op(**op)
        data_found = self.snapcmds[0][2]
        self.assertEqual(mycfg, data_found['config'][name])

    def test_render_op_config_int(self):
        # config entry for package can be a list, not a string blob
        mycfg = 1
        name = 'snapf1'
        op = makeop('config', name, config=mycfg)
        render_snap_op(**op)
        data_found = self.snapcmds[0][2]
        self.assertEqual(mycfg, data_found['config'][name])

    def test_render_long_configs_short(self):
        # install a namespaced package should have un-namespaced config
        mycfg = {'k1': 'k2'}
        name = 'snapf1'
        op = makeop('install', name + ".smoser", config=mycfg)
        render_snap_op(**op)
        data_found = self.snapcmds[0][2]
        self.assertEqual(mycfg, data_found['config'][name])

    def test_render_does_not_pad_cfgfile(self):
        # package_ops with cfgfile should not modify --file= content.
        mydata = "foo1: bar1\nk: [l1, l2, l3]\n"
        self.populate_tmp(
            {"snapf1.snap": b"foo1", "snapf1.config": mydata.encode()})
        ret = get_package_ops(
            packages=[], configs={}, installed=[], fspath=self.tmp)
        self.assertEqual(
            ret,
            [makeop_tmpd(self.tmp, 'install', 'snapf1', path="snapf1.snap",
                         cfgfile="snapf1.config")])

        # now the op was ok, but test that render didn't mess it up.
        render_snap_op(**ret[0])
        data_found = self.snapcmds[0][2]
        # the data found gets loaded in the snapcmd interpretation
        # so this comparison is a bit lossy, but input to snappy config
        # is expected to be yaml loadable, so it should be OK.
        self.assertEqual(yaml.safe_load(mydata), data_found)


def makeop_tmpd(tmpd, op, name, config=None, path=None, cfgfile=None):
    if cfgfile:
        cfgfile = os.path.sep.join([tmpd, cfgfile])
    if path:
        path = os.path.sep.join([tmpd, path])
    return(makeop(op=op, name=name, config=config, path=path, cfgfile=cfgfile))


def apply_patches(patches):
    ret = []
    for (ref, name, replace) in patches:
        if replace is None:
            continue
        orig = getattr(ref, name)
        setattr(ref, name, replace)
        ret.append((ref, name, orig))
    return ret
