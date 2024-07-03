import builtins
import glob
import os
import pathlib
import shutil
from pathlib import Path
from unittest import mock

import pytest

from cloudinit import atomic_helper, log, util
from cloudinit.cmd.devel import logs
from cloudinit.gpg import GPG
from tests.hypothesis import HAS_HYPOTHESIS
from tests.unittests.helpers import example_netdev, retarget_many_wrapper


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
        ("listdir", 1),
        ("mkdir", 1),
        ("rmdir", 1),
        ("lstat", 1),
        ("symlink", 2),
        ("stat", 1),
        ("scandir", 1),
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


@pytest.fixture
def fake_filesystem(mocker, tmpdir):
    """Mocks fs functions to operate under `tmpdir`"""
    # This allows fake_filesystem to be used with production code that
    # creates temporary directories. Functions like TemporaryDirectory()
    # attempt to create a directory under "/tmp" assuming that it already
    # exists, but then it fails because of the retargeting that happens here.
    tmpdir.mkdir("tmp")

    for (mod, funcs) in FS_FUNCS.items():
        for f, nargs in funcs:
            func = getattr(mod, f)
            trap_func = retarget_many_wrapper(str(tmpdir), nargs, func)
            mocker.patch.object(mod, f, trap_func)
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


log.configure_root_logger()


@pytest.fixture(autouse=True, scope="session")
def disable_root_logger_setup():
    with mock.patch("cloudinit.log.configure_root_logger", autospec=True):
        yield


@pytest.fixture
def clear_deprecation_log():
    """Clear any deprecation warnings before and after running tests."""
    # Since deprecations are de-duped, the existance (or non-existance) of
    # a deprecation warning in a previous test can cause the next test to
    # fail.
    setattr(util.deprecate, "log", set())


PYTEST_VERSION_TUPLE = tuple(map(int, pytest.__version__.split(".")))

if PYTEST_VERSION_TUPLE < (3, 9, 0):

    @pytest.fixture
    def tmp_path(tmpdir):
        return Path(tmpdir)


if HAS_HYPOTHESIS:
    from hypothesis import settings  # pylint: disable=import-error

    settings.register_profile("ci", max_examples=1000)
    settings.load_profile(os.getenv("HYPOTHESIS_PROFILE", "default"))


@pytest.fixture
def m_log_paths(mocker, tmp_path):
    """Define logs.LogPaths for testing and mock get_log_paths with it."""
    paths = logs.LogPaths(
        userdata_raw=tmp_path / "userdata_raw",
        cloud_data=tmp_path / "cloud_data",
        run_dir=tmp_path / "run_dir",
        instance_data_sensitive=tmp_path
        / "run_dir"
        / "instance_data_sensitive",
    )
    pathlib.Path(paths.run_dir).mkdir()
    mocker.patch.object(logs, "get_log_paths", return_value=paths)
    yield paths
