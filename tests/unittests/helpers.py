from __future__ import print_function

import os
import sys
import shutil
import tempfile
import unittest

import six

try:
    from unittest import mock
except ImportError:
    import mock
try:
    from contextlib import ExitStack
except ImportError:
    from contextlib2 import ExitStack

from cloudinit import helpers as ch
from cloudinit import util

# Used for detecting different python versions
PY2 = False
PY26 = False
PY27 = False
PY3 = False

_PY_VER = sys.version_info
_PY_MAJOR, _PY_MINOR = _PY_VER[0:2]
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

if PY26:
    # For now add these on, taken from python 2.7 + slightly adjusted.  Drop
    # all this once Python 2.6 is dropped as a minimum requirement.
    class TestCase(unittest.TestCase):
        def setUp(self):
            super(TestCase, self).setUp()
            self.__all_cleanups = ExitStack()

        def tearDown(self):
            self.__all_cleanups.close()
            unittest.TestCase.tearDown(self)

        def addCleanup(self, function, *args, **kws):
            self.__all_cleanups.callback(function, *args, **kws)

        def assertIs(self, expr1, expr2, msg=None):
            if expr1 is not expr2:
                standardMsg = '%r is not %r' % (expr1, expr2)
                self.fail(self._formatMessage(msg, standardMsg))

        def assertIn(self, member, container, msg=None):
            if member not in container:
                standardMsg = '%r not found in %r' % (member, container)
                self.fail(self._formatMessage(msg, standardMsg))

        def assertNotIn(self, member, container, msg=None):
            if member in container:
                standardMsg = '%r unexpectedly found in %r'
                standardMsg = standardMsg % (member, container)
                self.fail(self._formatMessage(msg, standardMsg))

        def assertIsNone(self, value, msg=None):
            if value is not None:
                standardMsg = '%r is not None'
                standardMsg = standardMsg % (value)
                self.fail(self._formatMessage(msg, standardMsg))

        def assertIsInstance(self, obj, cls, msg=None):
            """Same as self.assertTrue(isinstance(obj, cls)), with a nicer
            default message."""
            if not isinstance(obj, cls):
                standardMsg = '%s is not an instance of %r' % (repr(obj), cls)
                self.fail(self._formatMessage(msg, standardMsg))

        def assertDictContainsSubset(self, expected, actual, msg=None):
            missing = []
            mismatched = []
            for k, v in expected.items():
                if k not in actual:
                    missing.append(k)
                elif actual[k] != v:
                    mismatched.append('%r, expected: %r, actual: %r'
                                      % (k, v, actual[k]))

            if len(missing) == 0 and len(mismatched) == 0:
                return

            standardMsg = ''
            if missing:
                standardMsg = 'Missing: %r' % ','.join(m for m in missing)
            if mismatched:
                if standardMsg:
                    standardMsg += '; '
                standardMsg += 'Mismatched values: %s' % ','.join(mismatched)

            self.fail(self._formatMessage(msg, standardMsg))


else:
    class TestCase(unittest.TestCase):
        pass


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

    def getCloudPaths(self):
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir)
        cp = ch.Paths({
            'cloud_dir': tmpdir,
            'templates_dir': self.resourceLocation(),
        })
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
            os.path: ['isfile', 'exists', 'islink', 'isdir'],
            os: ['listdir'],
        }
        for (mod, funcs) in patch_funcs.items():
            for f in funcs:
                func = getattr(mod, f)
                trap_func = retarget_many_wrapper(new_root, 1, func)
                self.patched_funcs.enter_context(
                    mock.patch.object(mod, f, trap_func))


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


def populate_dir(path, files):
    if not os.path.exists(path):
        os.makedirs(path)
    for (name, content) in files.items():
        with open(os.path.join(path, name), "w") as fp:
            fp.write(content)
            fp.close()

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
