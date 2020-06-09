# This file is part of cloud-init. See LICENSE file for license information.

import functools
import httpretty
import io
import logging
import os
import random
import shutil
import string
import sys
import tempfile
import time
import unittest
from contextlib import ExitStack, contextmanager
from unittest import mock
from unittest.util import strclass

from cloudinit.config.schema import (
    SchemaValidationError, validate_cloudconfig_schema)
from cloudinit import cloud
from cloudinit import distros
from cloudinit import helpers as ch
from cloudinit.sources import DataSourceNone
from cloudinit.templater import JINJA_AVAILABLE
from cloudinit import subp
from cloudinit import util

_real_subp = subp.subp

# Used for skipping tests
SkipTest = unittest.SkipTest
skipIf = unittest.skipIf


# Makes the old path start
# with new base instead of whatever
# it previously had
def rebase_path(old_path, new_base):
    if old_path.startswith(new_base):
        # Already handled...
        return old_path
    # Retarget the base of that path
    # to the new base instead of the
    # old one...
    path = os.path.join(new_base, old_path.lstrip("/"))
    path = os.path.abspath(path)
    return path


# Can work on anything that takes a path as arguments
def retarget_many_wrapper(new_base, am, old_func):
    def wrapper(*args, **kwds):
        n_args = list(args)
        nam = am
        if am == -1:
            nam = len(n_args)
        for i in range(0, nam):
            path = args[i]
            # patchOS() wraps various os and os.path functions, however in
            # Python 3 some of these now accept file-descriptors (integers).
            # That breaks rebase_path() so in lieu of a better solution, just
            # don't rebase if we get a fd.
            if isinstance(path, str):
                n_args[i] = rebase_path(path, new_base)
        return old_func(*n_args, **kwds)
    return wrapper


class TestCase(unittest.TestCase):

    def reset_global_state(self):
        """Reset any global state to its original settings.

        cloudinit caches some values in cloudinit.util.  Unit tests that
        involved those cached paths were then subject to failure if the order
        of invocation changed (LP: #1703697).

        This function resets any of these global state variables to their
        initial state.

        In the future this should really be done with some registry that
        can then be cleaned in a more obvious way.
        """
        util.PROC_CMDLINE = None
        util._DNS_REDIRECT_IP = None
        util._LSB_RELEASE = {}

    def setUp(self):
        super(TestCase, self).setUp()
        self.reset_global_state()

    def shortDescription(self):
        return strclass(self.__class__) + '.' + self._testMethodName

    def add_patch(self, target, attr, *args, **kwargs):
        """Patches specified target object and sets it as attr on test
        instance also schedules cleanup"""
        if 'autospec' not in kwargs:
            kwargs['autospec'] = True
        m = mock.patch(target, *args, **kwargs)
        p = m.start()
        self.addCleanup(m.stop)
        setattr(self, attr, p)


class CiTestCase(TestCase):
    """This is the preferred test case base class unless user
       needs other test case classes below."""

    # Subclass overrides for specific test behavior
    # Whether or not a unit test needs logfile setup
    with_logs = False
    allowed_subp = False
    SUBP_SHELL_TRUE = "shell=true"

    @contextmanager
    def allow_subp(self, allowed_subp):
        orig = self.allowed_subp
        try:
            self.allowed_subp = allowed_subp
            yield
        finally:
            self.allowed_subp = orig

    def setUp(self):
        super(CiTestCase, self).setUp()
        if self.with_logs:
            # Create a log handler so unit tests can search expected logs.
            self.logger = logging.getLogger()
            self.logs = io.StringIO()
            formatter = logging.Formatter('%(levelname)s: %(message)s')
            handler = logging.StreamHandler(self.logs)
            handler.setFormatter(formatter)
            self.old_handlers = self.logger.handlers
            self.logger.handlers = [handler]
        if self.allowed_subp is True:
            subp.subp = _real_subp
        else:
            subp.subp = self._fake_subp

    def _fake_subp(self, *args, **kwargs):
        if 'args' in kwargs:
            cmd = kwargs['args']
        else:
            if not args:
                raise TypeError(
                    "subp() missing 1 required positional argument: 'args'")
            cmd = args[0]

        if not isinstance(cmd, str):
            cmd = cmd[0]
        pass_through = False
        if not isinstance(self.allowed_subp, (list, bool)):
            raise TypeError("self.allowed_subp supports list or bool.")
        if isinstance(self.allowed_subp, bool):
            pass_through = self.allowed_subp
        else:
            pass_through = (
                (cmd in self.allowed_subp) or
                (self.SUBP_SHELL_TRUE in self.allowed_subp and
                 kwargs.get('shell')))
        if pass_through:
            return _real_subp(*args, **kwargs)
        raise Exception(
            "called subp. set self.allowed_subp=True to allow\n subp(%s)" %
            ', '.join([str(repr(a)) for a in args] +
                      ["%s=%s" % (k, repr(v)) for k, v in kwargs.items()]))

    def tearDown(self):
        if self.with_logs:
            # Remove the handler we setup
            logging.getLogger().handlers = self.old_handlers
            logging.getLogger().level = None
        subp.subp = _real_subp
        super(CiTestCase, self).tearDown()

    def tmp_dir(self, dir=None, cleanup=True):
        # return a full path to a temporary directory that will be cleaned up.
        if dir is None:
            tmpd = tempfile.mkdtemp(
                prefix="ci-%s." % self.__class__.__name__)
        else:
            tmpd = tempfile.mkdtemp(dir=dir)
        self.addCleanup(
            functools.partial(shutil.rmtree, tmpd, ignore_errors=True))
        return tmpd

    def tmp_path(self, path, dir=None):
        # return an absolute path to 'path' under dir.
        # if dir is None, one will be created with tmp_dir()
        # the file is not created or modified.
        if dir is None:
            dir = self.tmp_dir()
        return os.path.normpath(os.path.abspath(os.path.join(dir, path)))

    def tmp_cloud(self, distro, sys_cfg=None, metadata=None):
        """Create a cloud with tmp working directory paths.

        @param distro: Name of the distro to attach to the cloud.
        @param metadata: Optional metadata to set on the datasource.

        @return: The built cloud instance.
        """
        self.new_root = self.tmp_dir()
        if not sys_cfg:
            sys_cfg = {}
        tmp_paths = {}
        for var in ['templates_dir', 'run_dir', 'cloud_dir']:
            tmp_paths[var] = self.tmp_path(var, dir=self.new_root)
            util.ensure_dir(tmp_paths[var])
        self.paths = ch.Paths(tmp_paths)
        cls = distros.fetch(distro)
        mydist = cls(distro, sys_cfg, self.paths)
        myds = DataSourceNone.DataSourceNone(sys_cfg, mydist, self.paths)
        if metadata:
            myds.metadata.update(metadata)
        return cloud.Cloud(myds, self.paths, sys_cfg, mydist, None)

    @classmethod
    def random_string(cls, length=8):
        """ return a random lowercase string with default length of 8"""
        return ''.join(
            random.choice(string.ascii_lowercase) for _ in range(length))


class ResourceUsingTestCase(CiTestCase):

    def setUp(self):
        super(ResourceUsingTestCase, self).setUp()
        self.resource_path = None

    def getCloudPaths(self, ds=None):
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir)
        cp = ch.Paths({'cloud_dir': tmpdir,
                       'templates_dir': resourceLocation()},
                      ds=ds)
        return cp


class FilesystemMockingTestCase(ResourceUsingTestCase):

    def setUp(self):
        super(FilesystemMockingTestCase, self).setUp()
        self.patched_funcs = ExitStack()

    def tearDown(self):
        self.patched_funcs.close()
        ResourceUsingTestCase.tearDown(self)

    def replicateTestRoot(self, example_root, target_root):
        real_root = resourceLocation()
        real_root = os.path.join(real_root, 'roots', example_root)
        for (dir_path, _dirnames, filenames) in os.walk(real_root):
            real_path = dir_path
            make_path = rebase_path(real_path[len(real_root):], target_root)
            util.ensure_dir(make_path)
            for f in filenames:
                real_path = util.abs_join(real_path, f)
                make_path = util.abs_join(make_path, f)
                shutil.copy(real_path, make_path)

    def patchUtils(self, new_root):
        patch_funcs = {
            util: [('write_file', 1),
                   ('append_file', 1),
                   ('load_file', 1),
                   ('ensure_dir', 1),
                   ('chmod', 1),
                   ('delete_dir_contents', 1),
                   ('del_file', 1),
                   ('sym_link', -1),
                   ('copy', -1)],
        }
        for (mod, funcs) in patch_funcs.items():
            for (f, am) in funcs:
                func = getattr(mod, f)
                trap_func = retarget_many_wrapper(new_root, am, func)
                self.patched_funcs.enter_context(
                    mock.patch.object(mod, f, trap_func))

        # Handle subprocess calls
        func = getattr(subp, 'subp')

        def nsubp(*_args, **_kwargs):
            return ('', '')

        self.patched_funcs.enter_context(
            mock.patch.object(subp, 'subp', nsubp))

        def null_func(*_args, **_kwargs):
            return None

        for f in ['chownbyid', 'chownbyname']:
            self.patched_funcs.enter_context(
                mock.patch.object(util, f, null_func))

    def patchOS(self, new_root):
        patch_funcs = {
            os.path: [('isfile', 1), ('exists', 1),
                      ('islink', 1), ('isdir', 1), ('lexists', 1)],
            os: [('listdir', 1), ('mkdir', 1),
                 ('lstat', 1), ('symlink', 2),
                 ('stat', 1)]
        }

        if hasattr(os, 'scandir'):
            # py27 does not have scandir
            patch_funcs[os].append(('scandir', 1))

        for (mod, funcs) in patch_funcs.items():
            for f, nargs in funcs:
                func = getattr(mod, f)
                trap_func = retarget_many_wrapper(new_root, nargs, func)
                self.patched_funcs.enter_context(
                    mock.patch.object(mod, f, trap_func))

    def patchOpen(self, new_root):
        trap_func = retarget_many_wrapper(new_root, 1, open)
        self.patched_funcs.enter_context(
            mock.patch('builtins.open', trap_func)
        )

    def patchStdoutAndStderr(self, stdout=None, stderr=None):
        if stdout is not None:
            self.patched_funcs.enter_context(
                mock.patch.object(sys, 'stdout', stdout))
        if stderr is not None:
            self.patched_funcs.enter_context(
                mock.patch.object(sys, 'stderr', stderr))

    def reRoot(self, root=None):
        if root is None:
            root = self.tmp_dir()
        self.patchUtils(root)
        self.patchOS(root)
        self.patchOpen(root)
        return root

    @contextmanager
    def reRooted(self, root=None):
        try:
            yield self.reRoot(root)
        finally:
            self.patched_funcs.close()


class HttprettyTestCase(CiTestCase):
    # necessary as http_proxy gets in the way of httpretty
    # https://github.com/gabrielfalcao/HTTPretty/issues/122
    # Also make sure that allow_net_connect is set to False.
    # And make sure reset and enable/disable are done.

    def setUp(self):
        self.restore_proxy = os.environ.get('http_proxy')
        if self.restore_proxy is not None:
            del os.environ['http_proxy']
        super(HttprettyTestCase, self).setUp()
        httpretty.HTTPretty.allow_net_connect = False
        httpretty.reset()
        httpretty.enable()

    def tearDown(self):
        httpretty.disable()
        httpretty.reset()
        if self.restore_proxy:
            os.environ['http_proxy'] = self.restore_proxy
        super(HttprettyTestCase, self).tearDown()


class SchemaTestCaseMixin(unittest.TestCase):

    def assertSchemaValid(self, cfg, msg="Valid Schema failed validation."):
        """Assert the config is valid per self.schema.

        If there is only one top level key in the schema properties, then
        the cfg will be put under that key."""
        props = list(self.schema.get('properties'))
        # put cfg under top level key if there is only one in the schema
        if len(props) == 1:
            cfg = {props[0]: cfg}
        try:
            validate_cloudconfig_schema(cfg, self.schema, strict=True)
        except SchemaValidationError:
            self.fail(msg)


def populate_dir(path, files):
    if not os.path.exists(path):
        os.makedirs(path)
    ret = []
    for (name, content) in files.items():
        p = os.path.sep.join([path, name])
        util.ensure_dir(os.path.dirname(p))
        with open(p, "wb") as fp:
            if isinstance(content, bytes):
                fp.write(content)
            else:
                fp.write(content.encode('utf-8'))
            fp.close()
        ret.append(p)

    return ret


def populate_dir_with_ts(path, data):
    """data is {'file': ('contents', mtime)}.  mtime relative to now."""
    populate_dir(path, dict((k, v[0]) for k, v in data.items()))
    btime = time.time()
    for fpath, (_contents, mtime) in data.items():
        ts = btime + mtime if mtime else btime
        os.utime(os.path.sep.join((path, fpath)), (ts, ts))


def dir2dict(startdir, prefix=None):
    flist = {}
    if prefix is None:
        prefix = startdir
    for root, _dirs, files in os.walk(startdir):
        for fname in files:
            fpath = os.path.join(root, fname)
            key = fpath[len(prefix):]
            flist[key] = util.load_file(fpath)
    return flist


def wrap_and_call(prefix, mocks, func, *args, **kwargs):
    """
    call func(args, **kwargs) with mocks applied, then unapplies mocks
    nicer to read than repeating dectorators on each function

    prefix: prefix for mock names (e.g. 'cloudinit.stages.util') or None
    mocks: dictionary of names (under 'prefix') to mock and either
        a return value or a dictionary to pass to the mock.patch call
    func: function to call with mocks applied
    *args,**kwargs: arguments for 'func'

    return_value: return from 'func'
    """
    delim = '.'
    if prefix is None:
        prefix = ''
    prefix = prefix.rstrip(delim)
    unwraps = []
    for fname, kw in mocks.items():
        if prefix:
            fname = delim.join((prefix, fname))
        if not isinstance(kw, dict):
            kw = {'return_value': kw}
        p = mock.patch(fname, **kw)
        p.start()
        unwraps.append(p)
    try:
        return func(*args, **kwargs)
    finally:
        for p in unwraps:
            p.stop()


def resourceLocation(subname=None):
    path = os.path.join('tests', 'data')
    if not subname:
        return path
    return os.path.join(path, subname)


def readResource(name, mode='r'):
    with open(resourceLocation(name), mode) as fh:
        return fh.read()


try:
    import jsonschema
    assert jsonschema  # avoid pyflakes error F401: import unused
    _missing_jsonschema_dep = False
except ImportError:
    _missing_jsonschema_dep = True


def skipUnlessJsonSchema():
    return skipIf(
        _missing_jsonschema_dep, "No python-jsonschema dependency present.")


def skipUnlessJinja():
    return skipIf(not JINJA_AVAILABLE, "No jinja dependency present.")


def skipIfJinja():
    return skipIf(JINJA_AVAILABLE, "Jinja dependency present.")


# older versions of mock do not have the useful 'assert_not_called'
if not hasattr(mock.Mock, 'assert_not_called'):
    def __mock_assert_not_called(mmock):
        if mmock.call_count != 0:
            msg = ("[citest] Expected '%s' to not have been called. "
                   "Called %s times." %
                   (mmock._mock_name or 'mock', mmock.call_count))
            raise AssertionError(msg)
    mock.Mock.assert_not_called = __mock_assert_not_called

# vi: ts=4 expandtab
