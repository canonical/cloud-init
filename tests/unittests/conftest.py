import builtins
import glob
import os
from pathlib import Path
from unittest import mock

import pytest

from cloudinit import atomic_helper, log, util
from cloudinit.gpg import GPG
from tests.hypothesis import HAS_HYPOTHESIS
from tests.unittests.helpers import retarget_many_wrapper


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
def disable_sysfs_net(request, tmpdir_factory):
    """Avoid tests which read the undertying host's /syc/class/net.

    To allow unobscured reads of /sys/class/net on the host we can
    parametrize the fixture with:

    @pytest.mark.parametrize("disable_sysfs_net", [False], indirect=True)
    """
    if hasattr(request, "param") and getattr(request, "param") is False:
        # Test disabled this fixture, perform no mocks.
        yield
        return
    mock_sysfs = f"{tmpdir_factory.mktemp('sysfs')}/"
    with mock.patch(
        "cloudinit.net.get_sys_class_path", return_value=mock_sysfs
    ):
        yield mock_sysfs


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


@pytest.fixture(autouse=True)
def disable_root_logger_setup(request):
    with mock.patch("cloudinit.cmd.main.configure_root_logger", autospec=True):
        yield


PYTEST_VERSION_TUPLE = tuple(map(int, pytest.__version__.split(".")))

if PYTEST_VERSION_TUPLE < (3, 9, 0):

    @pytest.fixture
    def tmp_path(tmpdir):
        return Path(tmpdir)


if HAS_HYPOTHESIS:
    from hypothesis import settings  # pylint: disable=import-error

    settings.register_profile("ci", max_examples=1000)
    settings.load_profile(os.getenv("HYPOTHESIS_PROFILE", "default"))
