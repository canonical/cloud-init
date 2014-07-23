import os
import sys
import unittest

from contextlib import contextmanager

from mocker import Mocker
from mocker import MockerTestCase

from cloudinit import helpers as ch
from cloudinit import util

import shutil

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
    # For now add these on, taken from python 2.7 + slightly adjusted
    class TestCase(unittest.TestCase):
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

        def assertDictContainsSubset(self, expected, actual, msg=None):
            missing = []
            mismatched = []
            for k, v in expected.iteritems():
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


@contextmanager
def mocker(verify_calls=True):
    m = Mocker()
    try:
        yield m
    finally:
        m.restore()
        if verify_calls:
            m.verify()


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
            n_args[i] = rebase_path(path, new_base)
        return old_func(*n_args, **kwds)
    return wrapper


class ResourceUsingTestCase(MockerTestCase):
    def __init__(self, methodName="runTest"):
        MockerTestCase.__init__(self, methodName)
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
        cp = ch.Paths({
            'cloud_dir': self.makeDir(),
            'templates_dir': self.resourceLocation(),
        })
        return cp


class FilesystemMockingTestCase(ResourceUsingTestCase):
    def __init__(self, methodName="runTest"):
        ResourceUsingTestCase.__init__(self, methodName)
        self.patched_funcs = []

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

    def tearDown(self):
        self.restore()
        ResourceUsingTestCase.tearDown(self)

    def restore(self):
        for (mod, f, func) in self.patched_funcs:
            setattr(mod, f, func)
        self.patched_funcs = []

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
                setattr(mod, f, trap_func)
                self.patched_funcs.append((mod, f, func))

        # Handle subprocess calls
        func = getattr(util, 'subp')

        def nsubp(*_args, **_kwargs):
            return ('', '')

        setattr(util, 'subp', nsubp)
        self.patched_funcs.append((util, 'subp', func))

        def null_func(*_args, **_kwargs):
            return None

        for f in ['chownbyid', 'chownbyname']:
            func = getattr(util, f)
            setattr(util, f, null_func)
            self.patched_funcs.append((util, f, func))

    def patchOS(self, new_root):
        patch_funcs = {
            os.path: ['isfile', 'exists', 'islink', 'isdir'],
            os: ['listdir'],
        }
        for (mod, funcs) in patch_funcs.items():
            for f in funcs:
                func = getattr(mod, f)
                trap_func = retarget_many_wrapper(new_root, 1, func)
                setattr(mod, f, trap_func)
                self.patched_funcs.append((mod, f, func))


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
    for (name, content) in files.iteritems():
        with open(os.path.join(path, name), "w") as fp:
            fp.write(content)
            fp.close()
