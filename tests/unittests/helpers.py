# This file is part of cloud-init. See LICENSE file for license information.

from __future__ import print_function

import functools
import os
import shutil
import sys
import tempfile
import unittest

import mock
import six
import unittest2

try:
    from contextlib import ExitStack
except ImportError:
    from contextlib2 import ExitStack

from cloudinit import helpers as ch
from cloudinit import util

# Used for skipping tests
SkipTest = unittest2.SkipTest

# Used for detecting different python versions
PY2 = False
PY26 = False
PY27 = False
PY3 = False
FIX_HTTPRETTY = False

_PY_VER = sys.version_info
_PY_MAJOR, _PY_MINOR, _PY_MICRO = _PY_VER[0:3]
if (_PY_MAJOR, _PY_MINOR) <= (2, 6):
    if (_PY_MAJOR, _PY_MINOR) == (2, 6):
        PY26 = True
    if (_PY_MAJOR, _PY_MINOR) >= (2, 0):
        PY2 = True
else:
    if (_PY_MAJOR, _PY_MINOR) == (2, 7):
        PY27 = True
        PY2 = True
    if (_PY_MAJOR, _PY_MINOR) >= (3, 0):
        PY3 = True
        if _PY_MINOR == 4 and _PY_MICRO < 3:
            FIX_HTTPRETTY = True


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
            if isinstance(path, six.string_types):
                n_args[i] = rebase_path(path, new_base)
        return old_func(*n_args, **kwds)
    return wrapper


class TestCase(unittest2.TestCase):
    pass


class ResourceUsingTestCase(TestCase):
    def setUp(self):
        super(ResourceUsingTestCase, self).setUp()
        self.resource_path = None

    def resourceLocation(self, subname=None):
        if self.resource_path is None:
            paths = [
                os.path.join('tests', 'data'),
                os.path.join('data'),
                os.path.join(os.pardir, 'tests', 'data'),
                os.path.join(os.pardir, 'data'),
            ]
            for p in paths:
                if os.path.isdir(p):
                    self.resource_path = p
                    break
        self.assertTrue((self.resource_path and
                         os.path.isdir(self.resource_path)),
                        msg="Unable to locate test resource data path!")
        if not subname:
            return self.resource_path
        return os.path.join(self.resource_path, subname)

    def readResource(self, name):
        where = self.resourceLocation(name)
        with open(where, 'r') as fh:
            return fh.read()

    def getCloudPaths(self, ds=None):
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir)
        cp = ch.Paths({'cloud_dir': tmpdir,
                       'templates_dir': self.resourceLocation()},
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
        real_root = self.resourceLocation()
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
        func = getattr(util, 'subp')

        def nsubp(*_args, **_kwargs):
            return ('', '')

        self.patched_funcs.enter_context(
            mock.patch.object(util, 'subp', nsubp))

        def null_func(*_args, **_kwargs):
            return None

        for f in ['chownbyid', 'chownbyname']:
            self.patched_funcs.enter_context(
                mock.patch.object(util, f, null_func))

    def patchOS(self, new_root):
        patch_funcs = {
            os.path: [('isfile', 1), ('exists', 1),
                      ('islink', 1), ('isdir', 1)],
            os: [('listdir', 1), ('mkdir', 1),
                 ('lstat', 1), ('symlink', 2)],
        }
        for (mod, funcs) in patch_funcs.items():
            for f, nargs in funcs:
                func = getattr(mod, f)
                trap_func = retarget_many_wrapper(new_root, nargs, func)
                self.patched_funcs.enter_context(
                    mock.patch.object(mod, f, trap_func))

    def patchOpen(self, new_root):
        trap_func = retarget_many_wrapper(new_root, 1, open)
        name = 'builtins.open' if PY3 else '__builtin__.open'
        self.patched_funcs.enter_context(mock.patch(name, trap_func))

    def patchStdoutAndStderr(self, stdout=None, stderr=None):
        if stdout is not None:
            self.patched_funcs.enter_context(
                mock.patch.object(sys, 'stdout', stdout))
        if stderr is not None:
            self.patched_funcs.enter_context(
                mock.patch.object(sys, 'stderr', stderr))

    def reRoot(self, root=None):
        if root is None:
            root = tempfile.mkdtemp()
            self.addCleanup(shutil.rmtree, root)
        self.patchUtils(root)
        self.patchOS(root)
        return root


def import_httpretty():
    """Import HTTPretty and monkey patch Python 3.4 issue.
    See https://github.com/gabrielfalcao/HTTPretty/pull/193 and
    as well as https://github.com/gabrielfalcao/HTTPretty/issues/221.

    Lifted from
    https://github.com/inveniosoftware/datacite/blob/master/tests/helpers.py
    """
    if not FIX_HTTPRETTY:
        import httpretty
    else:
        import socket
        old_SocketType = socket.SocketType

        import httpretty
        from httpretty import core

        def sockettype_patch(f):
            @functools.wraps(f)
            def inner(*args, **kwargs):
                f(*args, **kwargs)
                socket.SocketType = old_SocketType
                socket.__dict__['SocketType'] = old_SocketType
            return inner

        core.httpretty.disable = sockettype_patch(
            httpretty.httpretty.disable
        )
    return httpretty


class HttprettyTestCase(TestCase):
    # necessary as http_proxy gets in the way of httpretty
    # https://github.com/gabrielfalcao/HTTPretty/issues/122
    def setUp(self):
        self.restore_proxy = os.environ.get('http_proxy')
        if self.restore_proxy is not None:
            del os.environ['http_proxy']
        super(HttprettyTestCase, self).setUp()

    def tearDown(self):
        if self.restore_proxy:
            os.environ['http_proxy'] = self.restore_proxy
        super(HttprettyTestCase, self).tearDown()


class TempDirTestCase(TestCase):
    # provide a tempdir per class, not per test.
    def setUp(self):
        super(TempDirTestCase, self).setUp()
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def tmp_path(self, path):
        if path.startswith(os.path.sep):
            path = "." + path

        return os.path.normpath(os.path.join(self.tmp, path))


def populate_dir(path, files):
    if not os.path.exists(path):
        os.makedirs(path)
    for (name, content) in files.items():
        p = os.path.join(path, name)
        util.ensure_dir(os.path.dirname(p))
        with open(p, "wb") as fp:
            if isinstance(content, six.binary_type):
                fp.write(content)
            else:
                fp.write(content.encode('utf-8'))
            fp.close()


def dir2dict(startdir, prefix=None):
    flist = {}
    if prefix is None:
        prefix = startdir
    for root, dirs, files in os.walk(startdir):
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


try:
    skipIf = unittest.skipIf
except AttributeError:
    # Python 2.6.  Doesn't have to be high fidelity.
    def skipIf(condition, reason):
        def decorator(func):
            def wrapper(*args, **kws):
                if condition:
                    return func(*args, **kws)
                else:
                    print(reason, file=sys.stderr)
            return wrapper
        return decorator

# vi: ts=4 expandtab
