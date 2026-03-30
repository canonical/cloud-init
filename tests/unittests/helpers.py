# This file is part of cloud-init. See LICENSE file for license information.
# pylint: disable=attribute-defined-outside-init

import copy
import os
import random
import shutil
import string
import time
import unittest
from contextlib import contextmanager
from unittest import mock
from unittest.util import strclass
from urllib.parse import urlsplit, urlunsplit

import pytest
import responses

from cloudinit import distros, helpers, settings, util
from cloudinit.helpers import Paths
from cloudinit.templater import JINJA_AVAILABLE
from tests.helpers import cloud_init_project_dir

try:
    import apt_pkg  # type: ignore # noqa: F401

    HAS_APT_PKG = True
except ImportError:
    HAS_APT_PKG = False


# Used by tests to verify the error message when a jsonschema structure
# is empty but should not be.
# Version 4.20.0 of jsonschema changed the error messages for empty structures.
SCHEMA_EMPTY_ERROR = (
    "(is too short|should be non-empty|does not have enough properties)"
)

example_netdev = {
    "eth0": {
        "hwaddr": "00:16:3e:16:db:54",
        "ipv4": [
            {
                "bcast": "10.85.130.255",
                "ip": "10.85.130.116",
                "mask": "255.255.255.0",
                "scope": "global",
            }
        ],
        "ipv6": [
            {
                "ip": "fd42:baa2:3dd:17a:216:3eff:fe16:db54/64",
                "scope6": "global",
            },
            {"ip": "fe80::216:3eff:fe16:db54/64", "scope6": "link"},
        ],
        "up": True,
    },
    "lo": {
        "hwaddr": "",
        "ipv4": [
            {
                "bcast": "",
                "ip": "127.0.0.1",
                "mask": "255.0.0.0",
                "scope": "host",
            }
        ],
        "ipv6": [{"ip": "::1/128", "scope6": "host"}],
        "up": True,
    },
}


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
        for i in range(nam):
            path = args[i]
            # patchOS() wraps various os and os.path functions, however in
            # Python 3 some of these now accept file-descriptors (integers).
            # That breaks rebase_path() so in lieu of a better solution, just
            # don't rebase if we get a fd.
            if isinstance(path, str):
                n_args[i] = rebase_path(path, new_base)
        return old_func(*n_args, **kwds)

    return wrapper


def random_string(length=8):
    """return a random lowercase string with default length of 8"""
    return "".join(
        random.choice(string.ascii_lowercase) for _ in range(length)
    )


# Note: The use of this class and unittests.TestCase is discouraged. Use pytest
# instead. See development docs on testing.
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
        util._DNS_REDIRECT_IP = None

    def setUp(self):
        super(TestCase, self).setUp()
        self.reset_global_state()

    def shortDescription(self):
        return strclass(self.__class__) + "." + self._testMethodName

    def add_patch(self, target, attr, *args, **kwargs):
        """Patches specified target object and sets it as attr on test
        instance also schedules cleanup"""
        if "autospec" not in kwargs:
            kwargs["autospec"] = True
        m = mock.patch(target, *args, **kwargs)
        p = m.start()
        self.addCleanup(m.stop)
        setattr(self, attr, p)


def replicate_test_root(example_root, target_root):
    real_root = resourceLocation()
    real_root = os.path.join(real_root, "roots", example_root)
    for dir_path, _dirnames, filenames in os.walk(real_root):
        real_path = dir_path
        make_path = rebase_path(real_path[len(real_root) :], target_root)
        util.ensure_dir(make_path)
        for f in filenames:
            real_path = os.path.abspath(os.path.join(real_path, f))
            make_path = os.path.abspath(os.path.join(make_path, f))
            shutil.copy(real_path, make_path)


def responses_assert_call_count(url: str, count: int) -> bool:
    """Focal and older have a version of responses which does
    not carry this attribute. This can be removed when focal
    is no longer supported.
    """
    if hasattr(responses, "assert_call_count"):
        return responses.assert_call_count(url, count)

    def _ensure_url_default_path(url):
        if isinstance(url, str):
            url_parts = list(urlsplit(url))
            if url_parts[2] == "":
                url_parts[2] = "/"
                url = urlunsplit(url_parts)
        return url

    call_count = len(
        [
            1
            for call in responses.calls
            if call.request.url == _ensure_url_default_path(url)
        ]
    )
    if call_count == count:
        return True
    else:
        raise AssertionError(
            f"Expected URL '{url}' to be called {count} times. "
            f"Called {call_count} times."
        )


def get_mock_paths(temp_dir):
    class MockPaths(Paths):
        def __init__(self, path_cfgs: dict, ds=None):
            super().__init__(path_cfgs=path_cfgs, ds=ds)

            self.cloud_dir: str = path_cfgs.get(
                "cloud_dir", f"{temp_dir}/var/lib/cloud"
            )
            self.run_dir: str = path_cfgs.get(
                "run_dir", f"{temp_dir}/run/cloud/"
            )
            self.template_dir: str = path_cfgs.get(
                "templates_dir", f"{temp_dir}/etc/cloud/templates/"
            )

    return MockPaths


def populate_dir(path, files):
    if not os.path.exists(path):
        os.makedirs(path)
    ret = []
    for name, content in files.items():
        p = os.path.sep.join([path, name])
        util.ensure_dir(os.path.dirname(p))
        with open(p, "wb") as fp:
            if isinstance(content, bytes):
                fp.write(content)
            else:
                fp.write(content.encode("utf-8"))
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


def dir2dict(startdir, prefix=None, filter=None):
    flist = {}
    if prefix is None:
        prefix = startdir
    for root, _dirs, files in os.walk(startdir):
        for fname in files:
            fpath = os.path.join(root, fname)
            key = fpath[len(prefix) :]
            if filter is not None and not filter(fpath):
                continue
            flist[key] = util.load_text_file(fpath)
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
    delim = "."
    if prefix is None:
        prefix = ""
    prefix = prefix.rstrip(delim)
    unwraps = []
    for fname, kw in mocks.items():
        if prefix:
            fname = delim.join((prefix, fname))
        if not isinstance(kw, dict):
            kw = {"return_value": kw}
        p = mock.patch(fname, **kw)
        p.start()
        unwraps.append(p)
    try:
        return func(*args, **kwargs)
    finally:
        for p in unwraps:
            p.stop()


def resourceLocation(subname=None):
    path = cloud_init_project_dir("tests/data")
    if not subname:
        return path
    return os.path.join(path, subname)


def readResource(name, mode="r"):
    with open(resourceLocation(name), mode) as fh:
        return fh.read()


def skipIfAptPkg():
    return pytest.mark.skipif(
        HAS_APT_PKG, reason="No python-apt dependency present."
    )


try:
    import importlib.metadata

    import jsonschema

    assert jsonschema  # avoid pyflakes error F401: import unused
    _jsonschema_version = tuple(
        int(part)
        for part in importlib.metadata.metadata("jsonschema")
        .get("Version", "")
        .split(".")
    )
    _missing_jsonschema_dep = False
except ImportError:
    _missing_jsonschema_dep = True
    _jsonschema_version = (0, 0, 0)


def skipUnlessJsonSchemaVersionGreaterThan(version=(0, 0, 0)):
    return pytest.mark.skipif(
        _jsonschema_version <= version,
        reason=(
            f"python3-jsonschema {_jsonschema_version} not greater than"
            f" {version}"
        ),
    )


def skipUnlessJsonSchema():
    return pytest.mark.skipif(
        _missing_jsonschema_dep,
        reason="No python-jsonschema dependency present.",
    )


def skipUnlessJinja():
    return pytest.mark.skipif(
        not JINJA_AVAILABLE, reason="No jinja dependency present."
    )


@skipUnlessJinja()
def skipUnlessJinjaVersionGreaterThan(version=(0, 0, 0)):
    import jinja2

    return pytest.mark.skipif(
        tuple(map(int, jinja2.__version__.split("."))) < version,
        reason=f"jinj2 version is less than {version}",
    )


def skipIfJinja():
    return pytest.mark.skipif(
        JINJA_AVAILABLE, reason="Jinja dependency present."
    )


# older versions of mock do not have the useful 'assert_not_called'
if not hasattr(mock.Mock, "assert_not_called"):

    def __mock_assert_not_called(mmock):
        if mmock.call_count != 0:
            msg = (
                "[citest] Expected '%s' to not have been called. "
                "Called %s times."
                % (mmock._mock_name or "mock", mmock.call_count)
            )
            raise AssertionError(msg)

    mock.Mock.assert_not_called = __mock_assert_not_called  # type: ignore


@contextmanager
def does_not_raise():
    """Context manager to parametrize tests raising and not raising exceptions

    Note: In python-3.7+, this can be substituted by contextlib.nullcontext
    More info:
    https://docs.pytest.org/en/6.2.x/example/parametrize.html?highlight=does_not_raise#parametrizing-conditional-raising

    Example:
    --------
    >>> @pytest.mark.parametrize(
    >>>     "example_input,expectation",
    >>>     [
    >>>         (1, does_not_raise()),
    >>>         (0, pytest.raises(ZeroDivisionError)),
    >>>     ],
    >>> )
    >>> def test_division(example_input, expectation):
    >>>     with expectation:
    >>>         assert (0 / example_input) is not None

    """
    yield


def get_distro(dname, system_info=None, /, renderers=None, activators=None):
    """Return a Distro class of distro 'dname'.

    system_info has the format of CFG_BUILTIN['system_info'].

    Example: get_distro("debian")
    """
    if system_info is None:
        system_info = copy.deepcopy(settings.CFG_BUILTIN["system_info"])
    system_info["distro"] = dname
    if renderers:
        system_info["network"]["renderers"] = renderers
    if activators:
        system_info["network"]["activators"] = activators
    paths = helpers.Paths(system_info["paths"])
    distro_cls = distros.fetch(dname)
    return distro_cls(dname, system_info, paths)


def assert_count_equal(a, b):
    """
    Equivalent to unittests.TestCase.assertCountEqual.

    https://docs.python.org/3/library/unittest.html#unittest.TestCase.assertCountEqual
    """
    case = unittest.TestCase()
    case.assertCountEqual(a, b)
