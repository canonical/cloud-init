import builtins
import glob
import os
import shutil
from pathlib import Path
from unittest import mock

import pytest

from cloudinit import (
    atomic_helper,
    distros,
    helpers,
    lifecycle,
    temp_utils,
)
from cloudinit import user_data as ud
from cloudinit import (
    util,
)
from cloudinit.gpg import GPG
from cloudinit.log import loggers
from tests.unittests.helpers import (
    example_netdev,
    rebase_path,
    retarget_many_wrapper,
)


@pytest.fixture
def Distro(paths):
    def _get_distro(name, cfg=None):
        cls = distros.fetch(name)
        return cls(name, cfg or {}, paths)

    return _get_distro


@pytest.fixture
def m_gpg():
    MockGPG = mock.Mock(spec=GPG)
    MockGPG.configure_mock(**{"getkeybyid.return_value": "fakekey"})
    gpg = MockGPG()
    gpg.list_keys = mock.Mock(return_value="<mocked: list_keys>")
    gpg.getkeybyid = mock.Mock(return_value="<mocked: getkeybyid>")

    # to make tests for cc_apt_configure behave, we need the mocked GPG
    # to actually behave like a context manager
    gpg.__enter__ = GPG.__enter__
    gpg.__exit__ = GPG.__exit__
    yield gpg


FS_FUNCS = {
    os.path: [
        ("isfile", 1),
        ("exists", 1),
        ("islink", 1),
        ("isdir", 1),
        ("lexists", 1),
        ("relpath", 1),
    ],
    os: [
        ("chmod", 2),
        ("chown", 2),
        ("listdir", 1),
        ("lstat", 1),
        ("mkdir", 1),
        ("rename", 2),
        ("rmdir", 1),
        ("scandir", 1),
        ("stat", 1),
        ("symlink", 2),
    ],
    util: [
        ("write_file", 1),
        ("append_file", 1),
        ("load_binary_file", 1),
        ("load_text_file", 1),
        ("ensure_dir", 1),
        ("chmod", 1),
        ("delete_dir_contents", 1),
        ("del_file", 1),
        ("sym_link", -1),
        ("copy", -1),
    ],
    glob: [
        ("glob", 1),
    ],
    builtins: [
        ("open", 1),
    ],
    atomic_helper: [
        ("write_file", 1),
        ("write_json", 1),
    ],
    shutil: [
        ("rmtree", 1),
    ],
}

FS_VARS = {
    temp_utils: ["_ROOT_TMPDIR", "_EXE_ROOT_TMPDIR"],
}


@pytest.fixture
def fake_filesystem_hook():
    """A hook to interact with the real filesystem before mocking it in
    fake_filesystem.

    Fixtures needing to access the real filesystem in tests that use
    fake_filesystem, can depend on this fixture to ensure they run before
    fake_filesystem.

    See in action in tests/unittests/runs/test_simple_run.py.
    """


@pytest.fixture
def fake_filesystem(mocker, tmpdir, fake_filesystem_hook):
    """Mocks fs functions to operate under `tmpdir`

    This fixture is sorted after fix_cloud_init_hook to allow fixtures sorted
    before fake_cloud_init_hook to access the real filesystem.
    """
    # This allows fake_filesystem to be used with production code that
    # creates temporary directories. Functions like TemporaryDirectory()
    # attempt to create a directory under $TMPDIR (among other locations)
    # assuming that it already exists, but then it fails because of the
    # retargeting that happens here.
    TMPDIR = os.getenv("TMPDIR", "/tmp")
    Path(tmpdir, TMPDIR[1:]).mkdir(parents=True, exist_ok=True)
    Path(tmpdir, "tmp").mkdir(exist_ok=True)

    for mod, funcs in FS_FUNCS.items():
        for f, nargs in funcs:
            func = getattr(mod, f)
            trap_func = retarget_many_wrapper(str(tmpdir), nargs, func)
            mocker.patch.object(mod, f, trap_func)

    for mod, vars in FS_VARS.items():
        for var_name in vars:
            var_val = getattr(mod, var_name)
            new_var_val = rebase_path(var_val, str(tmpdir))
            mocker.patch.object(mod, var_name, new_var_val)

    yield str(tmpdir)


@pytest.fixture(scope="session", autouse=True)
def disable_sysfs_net(tmpdir_factory):
    """Avoid tests which read the underlying host's /syc/class/net."""
    mock_sysfs = f"{tmpdir_factory.mktemp('sysfs')}/"
    with mock.patch(
        "cloudinit.net.get_sys_class_path", return_value=mock_sysfs
    ):
        yield mock_sysfs


@pytest.fixture(scope="class")
def disable_netdev_info(request):
    """Avoid tests which read the underlying host's /syc/class/net."""
    with mock.patch(
        "cloudinit.netinfo.netdev_info", return_value=example_netdev
    ) as mock_netdev:
        yield mock_netdev


@pytest.fixture(autouse=True)
def disable_dns_lookup(request):
    if "allow_dns_lookup" in request.keywords:
        yield
        return

    def side_effect(args, *other_args, **kwargs):
        raise AssertionError("Unexpectedly used util.is_resolvable")

    with mock.patch(
        "cloudinit.util.is_resolvable", side_effect=side_effect, autospec=True
    ):
        yield


@pytest.fixture()
def dhclient_exists():
    with mock.patch(
        "cloudinit.net.dhcp.subp.which",
        return_value="/sbin/dhclient",
        autospec=True,
    ):
        yield


loggers.configure_root_logger()


@pytest.fixture(autouse=True, scope="session")
def disable_root_logger_setup():
    with mock.patch(
        "cloudinit.log.loggers.configure_root_logger", autospec=True
    ):
        yield


@pytest.fixture
def clear_deprecation_log():
    """Clear any deprecation warnings before and after running tests."""
    # Since deprecations are de-duped, the existence (or non-existence) of
    # a deprecation warning in a previous test can cause the next test to
    # fail.
    setattr(lifecycle.deprecate, "log", set())


PYTEST_VERSION_TUPLE = tuple(map(int, pytest.__version__.split(".")))

if PYTEST_VERSION_TUPLE < (3, 9, 0):

    @pytest.fixture
    def tmp_path(tmpdir):
        return Path(tmpdir)


@pytest.fixture
def paths(tmpdir) -> helpers.Paths:
    """
    Return a helpers.Paths object configured to use a tmpdir.

    (This uses the builtin tmpdir fixture.)
    """
    dirs = {
        "cloud_dir": tmpdir.mkdir("cloud_dir").strpath,
        "docs_dir": tmpdir.mkdir("docs_dir").strpath,
        "run_dir": tmpdir.mkdir("run_dir").strpath,
        "templates_dir": tmpdir.mkdir("templates_dir").strpath,
    }
    return helpers.Paths(dirs)


@pytest.fixture
def ud_proc(paths):
    return ud.UserDataProcessor(paths)


@pytest.fixture
def socket_attrs(mocker):
    """A fixture to add to some attributes to the socket module.

    Many socket attributes are OS-specific, so ensure we have attributes
    that work for the tests that need them.
    """
    mocker.patch("socket.AF_NETLINK", 0, create=True)
    mocker.patch("socket.NETLINK_ROUTE", 0, create=True)
    mocker.patch("socket.SOCK_CLOEXEC", 0, create=True)


@pytest.fixture
def fake_socket(mocker, socket_attrs):
    """A fixture to mock socket.socket()."""
    # Even though this is just a one-liner, if we need to mock
    # socket.socket, we want to ensure that socket_attrs is
    # applied too.
    return mocker.patch("socket.socket", autospec=True)
