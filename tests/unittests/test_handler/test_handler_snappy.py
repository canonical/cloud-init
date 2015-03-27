from cloudinit.config.cc_snappy import (
    makeop, get_package_ops, render_snap_op)
from cloudinit import util
from .. import helpers as t_help

import os
import tempfile

class TestInstallPackages(t_help.TestCase):
    def setUp(self):
        super(TestInstallPackages, self).setUp()
        self.unapply = []

        # by default 'which' has nothing in its path
        self.apply_patches([(util, 'subp', self._subp)])
        self.subp_called = []
        self.snapcmds = []
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        apply_patches([i for i in reversed(self.unapply)])

    def apply_patches(self, patches):
        ret = apply_patches(patches)
        self.unapply += ret

    def _subp(self, *args, **kwargs):
        # supports subp calling with cmd as args or kwargs
        if 'args' not in kwargs:
            kwargs['args'] = args[0]
        self.subp_called.append(kwargs)
        snap_cmds = []
        args = kwargs['args']
        if args[0:2] == ['snappy', 'config']:
            if args[3] == "-":
                config = kwargs.get('data', '')
            else:
                with open(args[3], "rb") as fp:
                    config = fp.read()
            self.snapcmds.append(['config', args[2], config])
        elif args[0:2] == ['snappy', 'install']:
            # basically parse the snappy command and add
            # to snap_installs a tuple (pkg, config)
            config = None
            pkg = None
            for arg in args[2:]:
                if arg.startswith("--config="):
                    cfgfile = arg.partition("=")[2]
                    if cfgfile == "-":
                        config = kwargs.get('data', '')
                    elif cfgfile:
                        with open(cfgfile, "rb") as fp:
                            config = fp.read()
                elif not pkg and not arg.startswith("-"):
                    pkg = arg
            self.snapcmds.append(['install', pkg, config])

    def test_package_ops_1(self):
        ret = get_package_ops(
            packages=['pkg1', 'pkg2', 'pkg3'],
            configs={'pkg2': b'mycfg2'}, installed=[])
        self.assertEqual(ret,
            [makeop('install', 'pkg1', None, None),
             makeop('install', 'pkg2', b'mycfg2', None),
             makeop('install', 'pkg3', None, None)])

    def test_package_ops_config_only(self):
        ret = get_package_ops(
            packages=None,
            configs={'pkg2': b'mycfg2'}, installed=['pkg1', 'pkg2'])
        self.assertEqual(ret,
            [makeop('config', 'pkg2', b'mycfg2')])

    def test_package_ops_install_and_config(self):
        ret = get_package_ops(
            packages=['pkg3', 'pkg2'],
            configs={'pkg2': b'mycfg2', 'xinstalled': b'xcfg'},
            installed=['xinstalled'])
        self.assertEqual(ret,
            [makeop('install', 'pkg3'),
             makeop('install', 'pkg2', b'mycfg2'),
             makeop('config', 'xinstalled', b'xcfg')])

    def test_package_ops_with_file(self):
        t_help.populate_dir(self.tmp,
            {"snapf1.snap": b"foo1", "snapf1.config": b"snapf1cfg",
             "snapf2.snap": b"foo2", "foo.bar": "ignored"})
        ret = get_package_ops(
            packages=['pkg1'], configs={}, installed=[], fspath=self.tmp)
        self.assertEqual(ret,
            [makeop_tmpd(self.tmp, 'install', 'snapf1', path="snapf1.snap",
                         cfgfile="snapf1.config"),
             makeop_tmpd(self.tmp, 'install', 'snapf2', path="snapf2.snap"),
             makeop('install', 'pkg1')])

    #def render_snap_op(op, name, path=None, cfgfile=None, config=None):
    def test_render_op_localsnap(self):
        t_help.populate_dir(self.tmp, {"snapf1.snap": b"foo1"})
        op = makeop_tmpd(self.tmp, 'install', 'snapf1',
                         path='snapf1.snap')
        render_snap_op(**op)
        self.assertEqual(self.snapcmds,
            [['install', op['path'], None]])

    def test_render_op_localsnap_localconfig(self):
        t_help.populate_dir(self.tmp,
            {"snapf1.snap": b"foo1", 'snapf1.config': b'snapf1cfg'})
        op = makeop_tmpd(self.tmp, 'install', 'snapf1',
                         path='snapf1.snap', cfgfile='snapf1.config')
        render_snap_op(**op)
        self.assertEqual(self.snapcmds,
            [['install', op['path'], b'snapf1cfg']])

    def test_render_op_localsnap_config(self):
        pass

    def test_render_op_snap(self):
        pass

    def test_render_op_snap_config(self):
        pass

    def test_render_op_config(self):
        pass


        
def makeop_tmpd(tmpd, op, name, config=None, path=None, cfgfile=None):
    if cfgfile:
        cfgfile = os.path.sep.join([tmpd, cfgfile])
    if path:
        path = os.path.sep.join([tmpd, path])
    return(makeop(op=op, name=name, config=config, path=path, cfgfile=cfgfile))

#    def test_local_snaps_no_config(self):
#        t_help.populate_dir(self.tmp,
#            {"snap1.snap": b"foo", "snap2.snap": b"foo", "foosnap.txt": b"foo"})
#        cc_snappy.install_packages(self.tmp, None)
#        self.assertEqual(self.snap_installs,
#            [("snap1.snap", None), ("snap2.snap", None)])
#
#    def test_local_snaps_mixed_config(self):
#        t_help.populate_dir(self.tmp,
#            {"snap1.snap": b"foo", "snap2.snap": b"snap2",
#             "snap1.config": b"snap1config"})
#        cc_snappy.install_packages(self.tmp, None)
#        self.assertEqual(self.snap_installs,
#            [("snap1.snap", b"snap1config"), ("snap2.snap", None)])
#
#    def test_local_snaps_all_config(self):
#        t_help.populate_dir(self.tmp,
#            {"snap1.snap": "foo", "snap1.config": b"snap1config",
#             "snap2.snap": "snap2", "snap2.config": b"snap2config"})
#        cc_snappy.install_packages(self.tmp, None)
#        self.assertEqual(self.snap_installs,
#            [("snap1.snap", b"snap1config"), ("snap2.snap", b"snap2config")])
#
#    def test_local_snaps_and_packages(self):
#        t_help.populate_dir(self.tmp,
#            {"snap1.snap": "foo", "snap1.config": b"snap1config"})
#        cc_snappy.install_packages(self.tmp, ["snap-in-store"])
#        self.assertEqual(self.snap_installs,
#            [("snap1.snap", b"snap1config"), ("snap-in-store", None)])
#
#    def test_packages_no_config(self):
#        cc_snappy.install_packages(self.tmp, ["snap-in-store"])
#        self.assertEqual(self.snap_installs,
#            [("snap-in-store", None)])
#
#    def test_packages_mixed_config(self):
#        cc_snappy.install_packages(self.tmp,
#            ["snap-in-store",
#             {'name': 'snap2-in-store', 'config': b"foo"}])
#        self.assertEqual(self.snap_installs,
#            [("snap-in-store", None), ("snap2-in-store", b"foo")])
#
#    def test_packages_all_config(self):
#        cc_snappy.install_packages(self.tmp,
#            [{'name': 'snap1-in-store', 'config': b"boo"},
#             {'name': 'snap2-in-store', 'config': b"wark"}])
#        self.assertEqual(self.snap_installs,
#            [("snap1-in-store", b"boo"), ("snap2-in-store", b"wark")])
#
#

def apply_patches(patches):
    ret = []
    for (ref, name, replace) in patches:
        if replace is None:
            continue
        orig = getattr(ref, name)
        setattr(ref, name, replace)
        ret.append((ref, name, orig))
    return ret

