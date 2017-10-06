# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.config.cc_snappy import (
    makeop, get_package_ops, render_snap_op)
from cloudinit.config.cc_snap_config import (
    add_assertions, add_snap_user, ASSERTIONS_FILE)
from cloudinit import (distros, helpers, cloud, util)
from cloudinit.config.cc_snap_config import handle as snap_handle
from cloudinit.sources import DataSourceNone
from cloudinit.tests.helpers import FilesystemMockingTestCase, mock

from cloudinit.tests import helpers as t_help

import logging
import os
import shutil
import tempfile
import textwrap
import yaml

LOG = logging.getLogger(__name__)
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
                if arg.startswith("-"):
                    continue
                if not pkg:
                    pkg = arg
                elif not config:
                    cfgfile = arg
                    if cfgfile == "-":
                        config = kwargs.get('data', '')
                    elif cfgfile:
                        with open(cfgfile, "rb") as fp:
                            config = yaml.safe_load(fp.read())
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

        # find filenames
        self.populate_tmp(
            {"pkg-ws.smoser_0.3.4_all.snap": "pkg-ws-snapdata",
             "pkg-ws.config": "pkg-ws-config",
             "pkg1.smoser_1.2.3_all.snap": "pkg1.snapdata",
             "pkg1.smoser.config": "pkg1.smoser.config-data",
             "pkg1.config": "pkg1.config-data",
             "pkg2.smoser_0.0_amd64.snap": "pkg2-snapdata",
             "pkg2.smoser_0.0_amd64.config": "pkg2.config"})

        ret = get_package_ops(
            packages=[], configs={}, installed=[], fspath=self.tmp)
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


class TestSnapConfig(FilesystemMockingTestCase):

    SYSTEM_USER_ASSERTION = textwrap.dedent("""
    type: system-user
    authority-id: LqvZQdfyfGlYvtep4W6Oj6pFXP9t1Ksp
    brand-id: LqvZQdfyfGlYvtep4W6Oj6pFXP9t1Ksp
    email: foo@bar.com
    password: $6$E5YiAuMIPAwX58jG$miomhVNui/vf7f/3ctB/f0RWSKFxG0YXzrJ9rtJ1ikvzt
    series:
      - 16
    since: 2016-09-10T16:34:00+03:00
    until: 2017-11-10T16:34:00+03:00
    username: baz
    sign-key-sha3-384: RuVvnp4n52GilycjfbbTCI3_L8Y6QlIE75wxMc0KzGV3AUQqVd9GuXoj

    AcLBXAQAAQoABgUCV/UU1wAKCRBKnlMoJQLkZVeLD/9/+hIeVywtzsDA3oxl+P+u9D13y9s6svP
    Jd6Wnf4FTw6sq1GjBE4ZA7lrwSaRCUJ9Vcsvf2q9OGPY7mOb2TBxaDe0PbUMjrSrqllSSQwhpNI
    zG+NxkkKuxsUmLzFa+k9m6cyojNbw5LFhQZBQCGlr3JYqC0tIREq/UsZxj+90TUC87lDJwkU8GF
    s4CR+rejZj4itIcDcVxCSnJH6hv6j2JrJskJmvObqTnoOlcab+JXdamXqbldSP3UIhWoyVjqzkj
    +to7mXgx+cCUA9+ngNCcfUG+1huGGTWXPCYkZ78HvErcRlIdeo4d3xwtz1cl/w3vYnq9og1XwsP
    Yfetr3boig2qs1Y+j/LpsfYBYncgWjeDfAB9ZZaqQz/oc8n87tIPZDJHrusTlBfop8CqcM4xsKS
    d+wnEY8e/F24mdSOYmS1vQCIDiRU3MKb6x138Ud6oHXFlRBbBJqMMctPqWDunWzb5QJ7YR0I39q
    BrnEqv5NE0G7w6HOJ1LSPG5Hae3P4T2ea+ATgkb03RPr3KnXnzXg4TtBbW1nytdlgoNc/BafE1H
    f3NThcq9gwX4xWZ2PAWnqVPYdDMyCtzW3Ck+o6sIzx+dh4gDLPHIi/6TPe/pUuMop9CBpWwez7V
    v1z+1+URx6Xlq3Jq18y5pZ6fY3IDJ6km2nQPMzcm4Q==""")

    ACCOUNT_ASSERTION = textwrap.dedent("""
    type: account-key
    authority-id: canonical
    revision: 2
    public-key-sha3-384: BWDEoaqyr25nF5SNCvEv2v7QnM9QsfCc0PBMYD_i2NGSQ32EF2d4D0
    account-id: canonical
    name: store
    since: 2016-04-01T00:00:00.0Z
    body-length: 717
    sign-key-sha3-384: -CvQKAwRQ5h3Ffn10FILJoEZUXOv6km9FwA80-Rcj-f-6jadQ89VRswH

    AcbBTQRWhcGAARAA0KKYYQWuHOrsFVi4p4l7ZzSvX7kLgJFFeFgOkzdWKBTHEnsMKjl5mefFe9j
    qe8NlmJdfY7BenP7XeBtwKp700H/t9lLrZbpTNAPHXYxEWFJp5bPqIcJYBZ+29oLVLN1Tc5X482
    vCiDqL8+pPYqBrK2fNlyPlNNSum9wI70rDDL4r6FVvr+osTnGejibdV8JphWX+lrSQDnRSdM8KJ
    UM43vTgLGTi9W54oRhsA2OFexRfRksTrnqGoonCjqX5wO3OFSaMDzMsO2MJ/hPfLgDqw53qjzuK
    Iec9OL3k5basvu2cj5u9tKwVFDsCKK2GbKUsWWpx2KTpOifmhmiAbzkTHbH9KaoMS7p0kJwhTQG
    o9aJ9VMTWHJc/NCBx7eu451u6d46sBPCXS/OMUh2766fQmoRtO1OwCTxsRKG2kkjbMn54UdFULl
    VfzvyghMNRKIezsEkmM8wueTqGUGZWa6CEZqZKwhe/PROxOPYzqtDH18XZknbU1n5lNb7vNfem9
    2ai+3+JyFnW9UhfvpVF7gzAgdyCqNli4C6BIN43uwoS8HkykocZS/+Gv52aUQ/NZ8BKOHLw+7an
    Q0o8W9ltSLZbEMxFIPSN0stiZlkXAp6DLyvh1Y4wXSynDjUondTpej2fSvSlCz/W5v5V7qA4nIc
    vUvV7RjVzv17ut0AEQEAAQ==

    AcLDXAQAAQoABgUCV83k9QAKCRDUpVvql9g3IBT8IACKZ7XpiBZ3W4lqbPssY6On81WmxQLtvsM
    WTp6zZpl/wWOSt2vMNUk9pvcmrNq1jG9CuhDfWFLGXEjcrrmVkN3YuCOajMSPFCGrxsIBLSRt/b
    nrKykdLAAzMfG8rP1d82bjFFiIieE+urQ0Kcv09Jtdvavq3JT1Tek5mFyyfhHNlQEKOzWqmRWiL
    3c3VOZUs1ZD8TSlnuq/x+5T0X0YtOyGjSlVxk7UybbyMNd6MZfNaMpIG4x+mxD3KHFtBAC7O6kL
    eX3i6j5nCY5UABfA3DZEAkWP4zlmdBEOvZ9t293NaDdOpzsUHRkoi0Zez/9BHQ/kwx/uNc2WqrY
    inCmu16JGNeXqsyinnLl7Ghn2RwhvDMlLxF6RTx8xdx1yk6p3PBTwhZMUvuZGjUtN/AG8BmVJQ1
    rsGSRkkSywvnhVJRB2sudnrMBmNS2goJbzSbmJnOlBrd2WsV0T9SgNMWZBiov3LvU4o2SmAb6b+
    rYwh8H5QHcuuYJuxDjFhPswIp6Wes5T6hUicf3SWtObcDS4HSkVS4ImBjjX9YgCuFy7QdnooOWE
    aPvkRw3XCVeYq0K6w9GRsk1YFErD4XmXXZjDYY650MX9v42Sz5MmphHV8jdIY5ssbadwFSe2rCQ
    6UX08zy7RsIb19hTndE6ncvSNDChUR9eEnCm73eYaWTWTnq1cxdVP/s52r8uss++OYOkPWqh5nO
    haRn7INjH/yZX4qXjNXlTjo0PnHH0q08vNKDwLhxS+D9du+70FeacXFyLIbcWllSbJ7DmbumGpF
    yYbtj3FDDPzachFQdIG3lSt+cSUGeyfSs6wVtc3cIPka/2Urx7RprfmoWSI6+a5NcLdj0u2z8O9
    HxeIgxDpg/3gT8ZIuFKePMcLDM19Fh/p0ysCsX+84B9chNWtsMSmIaE57V+959MVtsLu7SLb9gi
    skrju0pQCwsu2wHMLTNd1f3PTHmrr49hxetTus07HSQUApMtAGKzQilF5zqFjbyaTd4xgQbd+PK
    CjFyzQTDOcUhXpuUGt/IzlqiFfsCsmbj2K4KdSNYMlqIgZ3Azu8KvZLIhsyN7v5vNIZSPfEbjde
    ClU9r0VRiJmtYBUjcSghD9LWn+yRLwOxhfQVjm0cBwIt5R/yPF/qC76yIVuWUtM5Y2/zJR1J8OF
    qWchvlImHtvDzS9FQeLyzJAOjvZ2CnWp2gILgUz0WQdOk1Dq8ax7KS9BQ42zxw9EZAEPw3PEFqR
    IQsRTONp+iVS8YxSmoYZjDlCgRMWUmawez/Fv5b9Fb/XkO5Eq4e+KfrpUujXItaipb+tV8h5v3t
    oG3Ie3WOHrVjCLXIdYslpL1O4nadqR6Xv58pHj6k""")

    test_assertions = [ACCOUNT_ASSERTION, SYSTEM_USER_ASSERTION]

    def setUp(self):
        super(TestSnapConfig, self).setUp()
        self.subp = util.subp
        self.new_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.new_root)

    def _get_cloud(self, distro, metadata=None):
        self.patchUtils(self.new_root)
        paths = helpers.Paths({})
        cls = distros.fetch(distro)
        mydist = cls(distro, {}, paths)
        myds = DataSourceNone.DataSourceNone({}, mydist, paths)
        if metadata:
            myds.metadata.update(metadata)
        return cloud.Cloud(myds, paths, {}, mydist, None)

    @mock.patch('cloudinit.util.write_file')
    @mock.patch('cloudinit.util.subp')
    def test_snap_config_add_assertions(self, msubp, mwrite):
        add_assertions(self.test_assertions)

        combined = "\n".join(self.test_assertions)
        mwrite.assert_any_call(ASSERTIONS_FILE, combined.encode('utf-8'))
        msubp.assert_called_with(['snap', 'ack', ASSERTIONS_FILE],
                                 capture=True)

    def test_snap_config_add_assertions_empty(self):
        self.assertRaises(ValueError, add_assertions, [])

    def test_add_assertions_nonlist(self):
        self.assertRaises(ValueError, add_assertions, {})

    @mock.patch('cloudinit.util.write_file')
    @mock.patch('cloudinit.util.subp')
    def test_snap_config_add_assertions_ack_fails(self, msubp, mwrite):
        msubp.side_effect = [util.ProcessExecutionError("Invalid assertion")]
        self.assertRaises(util.ProcessExecutionError, add_assertions,
                          self.test_assertions)

    @mock.patch('cloudinit.config.cc_snap_config.add_assertions')
    @mock.patch('cloudinit.config.cc_snap_config.util')
    def test_snap_config_handle_no_config(self, mock_util, mock_add):
        cfg = {}
        cc = self._get_cloud('ubuntu')
        cc.distro = mock.MagicMock()
        cc.distro.name = 'ubuntu'
        mock_util.which.return_value = None
        snap_handle('snap_config', cfg, cc, LOG, None)
        mock_add.assert_not_called()

    def test_snap_config_add_snap_user_no_config(self):
        usercfg = add_snap_user(cfg=None)
        self.assertIsNone(usercfg)

    def test_snap_config_add_snap_user_not_dict(self):
        cfg = ['foobar']
        self.assertRaises(ValueError, add_snap_user, cfg)

    def test_snap_config_add_snap_user_no_email(self):
        cfg = {'assertions': [], 'known': True}
        usercfg = add_snap_user(cfg=cfg)
        self.assertIsNone(usercfg)

    @mock.patch('cloudinit.config.cc_snap_config.util')
    def test_snap_config_add_snap_user_email_only(self, mock_util):
        email = 'janet@planetjanet.org'
        cfg = {'email': email}
        mock_util.which.return_value = None
        mock_util.system_is_snappy.return_value = True
        mock_util.subp.side_effect = [
            ("false\n", ""),  # snap managed
        ]

        usercfg = add_snap_user(cfg=cfg)

        self.assertEqual(usercfg, {'snapuser': email, 'known': False})

    @mock.patch('cloudinit.config.cc_snap_config.util')
    def test_snap_config_add_snap_user_email_known(self, mock_util):
        email = 'janet@planetjanet.org'
        known = True
        cfg = {'email': email, 'known': known}
        mock_util.which.return_value = None
        mock_util.system_is_snappy.return_value = True
        mock_util.subp.side_effect = [
            ("false\n", ""),  # snap managed
            (self.SYSTEM_USER_ASSERTION, ""),  # snap known system-user
        ]

        usercfg = add_snap_user(cfg=cfg)

        self.assertEqual(usercfg, {'snapuser': email, 'known': known})

    @mock.patch('cloudinit.config.cc_snap_config.add_assertions')
    @mock.patch('cloudinit.config.cc_snap_config.util')
    def test_snap_config_handle_system_not_snappy(self, mock_util, mock_add):
        cfg = {'snappy': {'assertions': self.test_assertions}}
        cc = self._get_cloud('ubuntu')
        cc.distro = mock.MagicMock()
        cc.distro.name = 'ubuntu'
        mock_util.which.return_value = None
        mock_util.system_is_snappy.return_value = False

        snap_handle('snap_config', cfg, cc, LOG, None)

        mock_add.assert_not_called()

    @mock.patch('cloudinit.config.cc_snap_config.add_assertions')
    @mock.patch('cloudinit.config.cc_snap_config.util')
    def test_snap_config_handle_snapuser(self, mock_util, mock_add):
        email = 'janet@planetjanet.org'
        cfg = {
            'snappy': {
                'assertions': self.test_assertions,
                'email': email,
            }
        }
        cc = self._get_cloud('ubuntu')
        cc.distro = mock.MagicMock()
        cc.distro.name = 'ubuntu'
        mock_util.which.return_value = None
        mock_util.system_is_snappy.return_value = True
        mock_util.subp.side_effect = [
            ("false\n", ""),  # snap managed
        ]

        snap_handle('snap_config', cfg, cc, LOG, None)

        mock_add.assert_called_with(self.test_assertions)
        usercfg = {'snapuser': email, 'known': False}
        cc.distro.create_user.assert_called_with(email, **usercfg)

    @mock.patch('cloudinit.config.cc_snap_config.add_assertions')
    @mock.patch('cloudinit.config.cc_snap_config.util')
    def test_snap_config_handle_snapuser_known(self, mock_util, mock_add):
        email = 'janet@planetjanet.org'
        cfg = {
            'snappy': {
                'assertions': self.test_assertions,
                'email': email,
                'known': True,
            }
        }
        cc = self._get_cloud('ubuntu')
        cc.distro = mock.MagicMock()
        cc.distro.name = 'ubuntu'
        mock_util.which.return_value = None
        mock_util.system_is_snappy.return_value = True
        mock_util.subp.side_effect = [
            ("false\n", ""),  # snap managed
            (self.SYSTEM_USER_ASSERTION, ""),  # snap known system-user
        ]

        snap_handle('snap_config', cfg, cc, LOG, None)

        mock_add.assert_called_with(self.test_assertions)
        usercfg = {'snapuser': email, 'known': True}
        cc.distro.create_user.assert_called_with(email, **usercfg)

    @mock.patch('cloudinit.config.cc_snap_config.add_assertions')
    @mock.patch('cloudinit.config.cc_snap_config.util')
    def test_snap_config_handle_snapuser_known_managed(self, mock_util,
                                                       mock_add):
        email = 'janet@planetjanet.org'
        cfg = {
            'snappy': {
                'assertions': self.test_assertions,
                'email': email,
                'known': True,
            }
        }
        cc = self._get_cloud('ubuntu')
        cc.distro = mock.MagicMock()
        cc.distro.name = 'ubuntu'
        mock_util.which.return_value = None
        mock_util.system_is_snappy.return_value = True
        mock_util.subp.side_effect = [
            ("true\n", ""),  # snap managed
        ]

        snap_handle('snap_config', cfg, cc, LOG, None)

        mock_add.assert_called_with(self.test_assertions)
        cc.distro.create_user.assert_not_called()

    @mock.patch('cloudinit.config.cc_snap_config.add_assertions')
    @mock.patch('cloudinit.config.cc_snap_config.util')
    def test_snap_config_handle_snapuser_known_no_assertion(self, mock_util,
                                                            mock_add):
        email = 'janet@planetjanet.org'
        cfg = {
            'snappy': {
                'assertions': [self.ACCOUNT_ASSERTION],
                'email': email,
                'known': True,
            }
        }
        cc = self._get_cloud('ubuntu')
        cc.distro = mock.MagicMock()
        cc.distro.name = 'ubuntu'
        mock_util.which.return_value = None
        mock_util.system_is_snappy.return_value = True
        mock_util.subp.side_effect = [
            ("true\n", ""),  # snap managed
            ("", ""),        # snap known system-user
        ]

        snap_handle('snap_config', cfg, cc, LOG, None)

        mock_add.assert_called_with([self.ACCOUNT_ASSERTION])
        cc.distro.create_user.assert_not_called()


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

# vi: ts=4 expandtab
