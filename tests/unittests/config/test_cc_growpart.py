# This file is part of cloud-init. See LICENSE file for license information.
# pylint: disable=attribute-defined-outside-init

import errno
import logging
import os
import re
import shutil
import stat
from contextlib import ExitStack
from itertools import chain
from unittest import mock

import pytest

from cloudinit import cloud, distros, subp, temp_utils
from cloudinit.config import cc_growpart
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from cloudinit.distros.bsd import BSD
from cloudinit.subp import SubpResult
from tests.unittests.helpers import (
    does_not_raise,
    skipUnlessJsonSchema,
)
from tests.unittests.util import MockDistro

# growpart:
#   mode: auto  # off, on, auto, 'growpart'
#   devices: ['root']

HELP_GROWPART_RESIZE = """
growpart disk partition
   rewrite partition table so that partition takes up all the space it can
   options:
    -h | --help       print Usage and exit
<SNIP>
    -u | --update  R  update the the kernel partition table info after growing
                      this requires kernel support and 'partx --update'
                      R is one of:
                       - 'auto'  : [default] update partition if possible
<SNIP>
   Example:
    - growpart /dev/sda 1
      Resize partition 1 on /dev/sda
"""

HELP_GROWPART_NO_RESIZE = """
growpart disk partition
   rewrite partition table so that partition takes up all the space it can
   options:
    -h | --help       print Usage and exit
<SNIP>
   Example:
    - growpart /dev/sda 1
      Resize partition 1 on /dev/sda
"""

HELP_GPART = """
usage: gpart add -t type [-a alignment] [-b start] <SNIP> geom
       gpart backup geom
       gpart bootcode [-b bootcode] [-p partcode -i index] [-f flags] geom
<SNIP>
       gpart resize -i index [-a alignment] [-s size] [-f flags] geom
       gpart restore [-lF] [-f flags] provider [...]
       gpart recover [-f flags] geom
       gpart help
<SNIP>
"""


class Dir:
    """Stub object"""

    def __init__(self, name):
        self.name = name
        self.st_mode = name

    def is_dir(self, *args, **kwargs):
        return True

    def stat(self, *args, **kwargs):
        return self


class Scanner:
    """Stub object"""

    def __enter__(self):
        return (
            Dir(""),
            Dir(""),
        )

    def __exit__(self, *args):
        pass


def test_mode_off(mocker):
    # Test that nothing is done if mode is off.

    # this really only verifies that resizer_factory isn't called
    config = {"growpart": {"mode": "off"}}

    mock_resizer = mocker.patch.object(cc_growpart, "resizer_factory")

    cc_growpart.handle(
        name="growpart",
        cfg=config,
        cloud=None,
        args=[],
    )
    mock_resizer.assert_not_called()


@pytest.fixture
def freebsd_cloud(mocker):
    # Patch networking call during distro init
    mocker.patch(
        "cloudinit.distros.networking.subp.subp",
        return_value=("", None),
    )
    cls = distros.fetch("freebsd")
    distro = cls("freebsd", {}, None)

    cloud_obj = cloud.Cloud(
        None,
        None,
        {},
        distro,
        None,
    )
    return cloud_obj


class TestConfig:
    name = "growpart"
    log = logging.getLogger("TestConfig")
    args: list[str] = []

    def test_no_resizers_auto_is_fine(self, freebsd_cloud, mocker):
        mocker.patch.object(os.path, "isfile", return_value=False)

        mock_subp = mocker.patch.object(
            subp, "subp", return_value=SubpResult(HELP_GROWPART_NO_RESIZE, "")
        )
        config = {"growpart": {"mode": "auto"}}
        cc_growpart.handle(self.name, config, freebsd_cloud, self.args)

        mock_subp.assert_has_calls(
            [
                mocker.call(["growpart", "--help"], update_env={"LANG": "C"}),
                mocker.call(
                    ["gpart", "help"], update_env={"LANG": "C"}, rcs=[0, 1]
                ),
            ]
        )

    def test_no_resizers_mode_growpart_is_exception(self, freebsd_cloud):
        with mock.patch.object(
            subp, "subp", return_value=SubpResult(HELP_GROWPART_NO_RESIZE, "")
        ) as mockobj:
            config = {"growpart": {"mode": "growpart"}}
            with pytest.raises(ValueError):
                cc_growpart.handle(self.name, config, freebsd_cloud, self.args)

            mockobj.assert_called_once_with(
                ["growpart", "--help"], update_env={"LANG": "C"}
            )

    def test_mode_auto_prefers_growpart(self, mocker):
        mock_subp = mocker.patch.object(
            subp, "subp", return_value=SubpResult(HELP_GROWPART_RESIZE, "")
        )
        ret = cc_growpart.resizer_factory(
            mode="auto", distro=mock.Mock(), devices=["/"]
        )
        assert isinstance(ret, cc_growpart.ResizeGrowPart)

        mock_subp.assert_called_once_with(
            ["growpart", "--help"], update_env={"LANG": "C"}
        )

    @mock.patch.object(temp_utils, "mkdtemp", return_value="/tmp/much-random")
    @mock.patch.object(stat, "S_ISDIR", return_value=False)
    @mock.patch.object(os.path, "samestat", return_value=True)
    @mock.patch.object(os.path, "join", return_value="/tmp")
    @mock.patch.object(os, "mkdir")
    @mock.patch.object(os, "unlink")
    @mock.patch.object(os, "rmdir")
    @mock.patch.object(os, "open", return_value=1)
    @mock.patch.object(os, "close")
    @mock.patch.object(shutil, "rmtree")
    @mock.patch.object(os, "lseek", return_value=1024)
    @mock.patch.object(os, "lstat", return_value="interesting metadata")
    def test_force_lang_check_tempfile(self, *args, **kwargs):
        with mock.patch.object(
            subp, "subp", return_value=SubpResult(HELP_GROWPART_RESIZE, "")
        ) as mockobj:
            ret = cc_growpart.resizer_factory(
                mode="auto", distro=mock.Mock(), devices=["/"]
            )
            assert isinstance(ret, cc_growpart.ResizeGrowPart)
            diskdev = "/dev/sdb"
            partnum = 1
            partdev = "/dev/sdb"
            ret.resize(diskdev, partnum, partdev, None)
        mockobj.assert_has_calls(
            [
                mock.call(
                    ["growpart", "--dry-run", diskdev, partnum],
                    update_env={"LANG": "C", "TMPDIR": "/tmp"},
                ),
                mock.call(
                    ["growpart", diskdev, partnum],
                    update_env={"LANG": "C", "TMPDIR": "/tmp"},
                ),
            ]
        )

    def test_mode_use_growfs_on_root(self, mocker):
        mocker.patch.object(os.path, "isfile", return_value=True)
        mock_subp = mocker.patch.object(
            subp, "subp", return_value=SubpResult("File not found", "")
        )
        ret = cc_growpart.resizer_factory(
            mode="auto", distro=mock.Mock(), devices=["/"]
        )
        assert isinstance(ret, cc_growpart.ResizeGrowFS)

        mock_subp.assert_has_calls(
            [
                mocker.call(["growpart", "--help"], update_env={"LANG": "C"}),
            ]
        )

    def test_mode_auto_falls_back_to_gpart(self, mocker):
        mock_subp = mocker.patch.object(
            subp, "subp", return_value=SubpResult("", HELP_GPART)
        )
        ret = cc_growpart.resizer_factory(
            mode="auto", distro=mock.Mock(), devices=["/", "/opt"]
        )
        assert isinstance(ret, cc_growpart.ResizeGpart)

        mock_subp.assert_has_calls(
            [
                mocker.call(["growpart", "--help"], update_env={"LANG": "C"}),
                mocker.call(
                    ["gpart", "help"], update_env={"LANG": "C"}, rcs=[0, 1]
                ),
            ]
        )

    def test_mode_auto_falls_back_to_growfs(self, mocker):
        mocker.patch.object(os.path, "isfile", return_value=True)
        mock_subp = mocker.patch.object(
            subp, "subp", return_value=SubpResult("", HELP_GPART)
        )
        ret = cc_growpart.resizer_factory(
            mode="auto", distro=mock.Mock(), devices=["/"]
        )
        assert isinstance(ret, cc_growpart.ResizeGrowFS)

        mock_subp.assert_has_calls(
            [
                mocker.call(["growpart", "--help"], update_env={"LANG": "C"}),
            ]
        )

    def test_handle_with_no_growpart_entry(self, freebsd_cloud):
        # if no 'growpart' entry in config, then mode=auto should be used

        myresizer = object()
        retval = (
            (
                "/",
                cc_growpart.RESIZE.CHANGED,
                "my-message",
            ),
        )

        with ExitStack() as mocks:
            factory = mocks.enter_context(
                mock.patch.object(
                    cc_growpart, "resizer_factory", return_value=myresizer
                )
            )
            rsdevs = mocks.enter_context(
                mock.patch.object(
                    cc_growpart, "resize_devices", return_value=retval
                )
            )
            mocks.enter_context(
                mock.patch.object(
                    cc_growpart, "RESIZERS", (("mysizer", object),)
                )
            )

            cc_growpart.handle(self.name, {}, freebsd_cloud, self.args)

            factory.assert_called_once_with(
                "auto", distro=freebsd_cloud.distro, devices=["/"]
            )
            rsdevs.assert_called_once_with(
                myresizer, ["/"], freebsd_cloud.distro, resize_lv=True
            )


class TestResize:
    def test_simple_devices(self, mocker):
        # test simple device list
        # this patches out devent2dev, os.stat, and device_part_info
        # so in the end, doesn't test a lot
        distro = MockDistro()
        devs = ["/dev/XXda1", "/dev/YYda2"]
        enoent = ["/dev/ZZda3"]

        devstat_ret = Bunch(
            st_mode=25008,
            st_ino=6078,
            st_dev=5,
            st_nlink=1,
            st_uid=0,
            st_gid=6,
            st_size=0,
            st_atime=0,
            st_mtime=0,
            st_ctime=0,
        )
        resize_calls = []

        class myresizer:
            def resize(self, diskdev, partnum, partdev, fs):
                resize_calls.append((diskdev, partnum, partdev, fs))
                if partdev == "/dev/YYda2":
                    return (1024, 2048)
                return (1024, 1024)  # old size, new size

        def mystat(path):
            if path in devs:
                return devstat_ret
            if path in enoent:
                e = OSError("%s: does not exist" % path)
                e.errno = errno.ENOENT
                raise e
            raise AssertionError(f"unexpected stat call for {path}")

        mocker.patch.object(
            distro,
            "device_part_info",
            side_effect=simple_device_part_info,
        )
        mocker.patch("os.stat", side_effect=mystat)
        resized = cc_growpart.resize_devices(
            myresizer(), devs + enoent, distro
        )

        def find(name, res):
            for entry in res:
                if entry[0] == name:
                    return entry
            return None

        assert cc_growpart.RESIZE.NOCHANGE == find("/dev/XXda1", resized)[1]
        assert cc_growpart.RESIZE.CHANGED == find("/dev/YYda2", resized)[1]
        assert cc_growpart.RESIZE.SKIPPED == find(enoent[0], resized)[1]


class TestResizeZFS:
    def _devent2dev_side_effect(self, value):
        if value.startswith("zroot"):
            return value, "zfs"
        raise RuntimeError(f"unexpected value {value}")

    def _subp_side_effect(self, value, **kwargs):
        if value[0] == "growpart":
            raise subp.ProcessExecutionError()
        elif value[0] == "zpool":
            return ("1024\n", "")
        raise subp.ProcessExecutionError()

    @pytest.fixture
    def common_mocks(self, mocker):
        # These are all "happy path" mocks which will get overridden
        # when needed
        mocker.patch(
            "cloudinit.config.cc_growpart.devent2dev",
            side_effect=self._devent2dev_side_effect,
        )
        mocker.patch("cloudinit.util.is_container", return_value=False)
        # Find /etc/rc.d/growfs
        mocker.patch("os.path.isfile", return_value=True)
        mocker.patch(
            "cloudinit.config.cc_growpart.subp.subp",
            side_effect=self._subp_side_effect,
        )
        cls = distros.fetch("freebsd")
        # patch ifconfig -a
        mocker.patch(
            "cloudinit.distros.networking.subp.subp", return_value=("", None)
        )
        self.distro = cls("freebsd", {}, None)
        # The fixture must yield to guarantee fixture lifcycle semantics,
        # and to ensure pytest reliably executes the fixture before each test.
        yield

    @pytest.mark.parametrize(
        "dev, expected",
        [
            ("zroot/ROOT/changed", cc_growpart.RESIZE.CHANGED),
            ("zroot/ROOT/nochange", cc_growpart.RESIZE.NOCHANGE),
        ],
    )
    def test_zroot(self, dev, expected, common_mocks):
        resize_calls = []

        class MyResizer(cc_growpart.ResizeGrowFS):
            def resize(self, diskdev, partnum, partdev, fs):
                resize_calls.append((diskdev, partnum, partdev, fs))
                if partdev == "zroot/ROOT/changed":
                    return (1024, 2048)
                return (1024, 1024)  # old size, new size

        def get_status_from_device(device_name, resize_results):
            for result in resize_results:
                if result[0] == device_name:
                    return result[1]
            raise ValueError(
                f"Device {device_name} not found in {resize_results}"
            )

        resized = cc_growpart.resize_devices(
            resizer=MyResizer(distro=self.distro),
            devices=[dev],
            distro=self.distro,
        )
        assert expected == get_status_from_device(dev, resized)


class TestGetSize:
    # TODO: add tests for get_zfs_size()
    @pytest.mark.parametrize(
        "file_exists, expected",
        (
            (False, None),
            (True, 1),
        ),
    )
    def test_get_size_behaves(self, file_exists, expected, tmp_path):
        """Ensure that get_size() doesn't raise exception"""
        tmp_file = tmp_path / "tmp.txt"
        if file_exists:
            tmp_file.write_bytes(b"0")
        assert expected == cc_growpart.get_size(tmp_file, None)


class TestEncrypted:
    """Attempt end-to-end scenarios using encrypted devices.

    Things are mocked such that:
     - "/fake_encrypted" is mounted onto "/dev/mapper/fake"
     - "/dev/mapper/fake" is a LUKS device and symlinked to /dev/dm-1
     - The partition backing "/dev/mapper/fake" is "/dev/vdx1"
     - "/" is not encrypted and mounted onto "/dev/vdz1"

    Note that we don't (yet) support non-encrypted mapped drives, such
    as LVM volumes. If our mount point is /dev/mapper/*, then we will
    not resize it if it is not encrypted.
    """

    def _subp_side_effect(self, value, good=True, **kwargs):
        if value[0] == "dmsetup":
            return ("1 dependencies : (vdx1)",)
        return mock.Mock()

    def _device_part_info_side_effect(self, value):
        if value.startswith("/dev/mapper/"):
            raise TypeError(f"{value} not a partition")
        return (1024, 1024)

    def _devent2dev_side_effect(self, value):
        if value == "/fake_encrypted":
            return "/dev/mapper/fake", "ext3"
        elif value == "/":
            return "/dev/vdz", "ext4"
        elif value.startswith("zroot"):
            return value, "zfs"
        elif value.startswith("/dev"):
            return value, None
        raise RuntimeError(f"unexpected value {value}")

    def _realpath_side_effect(self, value):
        return "/dev/dm-1" if value.startswith("/dev/mapper") else value

    def assert_resize_and_cleanup(self):
        all_subp_args = list(
            chain(*[args[0][0] for args in self.m_subp.call_args_list])
        )
        assert "resize" in all_subp_args
        assert "luksKillSlot" in all_subp_args
        self.m_unlink.assert_called_once()

    def assert_no_resize_or_cleanup(self):
        all_subp_args = list(
            chain(*[args[0][0] for args in self.m_subp.call_args_list])
        )
        assert "resize" not in all_subp_args
        assert "luksKillSlot" not in all_subp_args
        self.m_unlink.assert_not_called()

    @pytest.fixture
    def common_mocks(self, mocker):
        # These are all "happy path" mocks which will get overridden
        # when needed

        self.distro = MockDistro()
        original_device_part_info = self.distro.device_part_info
        self.distro.device_part_info = self._device_part_info_side_effect
        mocker.patch("os.stat")
        mocker.patch("stat.S_ISBLK")
        mocker.patch("stat.S_ISCHR")
        mocker.patch(
            "cloudinit.config.cc_growpart.devent2dev",
            side_effect=self._devent2dev_side_effect,
        )
        mocker.patch(
            "os.path.realpath", side_effect=self._realpath_side_effect
        )
        # Only place subp.which is used in cc_growpart is for cryptsetup
        mocker.patch(
            "cloudinit.config.cc_growpart.subp.which",
            return_value="/usr/sbin/cryptsetup",
        )
        mocker.patch(
            "cloudinit.config.cc_growpart.is_lvm_device", return_value=False
        )
        self.m_subp = mocker.patch(
            "cloudinit.config.cc_growpart.subp.subp",
            side_effect=self._subp_side_effect,
        )
        mocker.patch(
            "pathlib.Path.open",
            new_callable=mock.mock_open,
            read_data=(
                '{"key":"XFmCwX2FHIQp0LBWaLEMiHIyfxt1SGm16VvUAVledlY=",'
                '"slot":5}'
            ),
        )
        mocker.patch("pathlib.Path.exists", return_value=True)
        self.m_unlink = mocker.patch("pathlib.Path.unlink", autospec=True)

        self.resizer = mock.Mock()
        self.resizer.resize = mock.Mock(return_value=(1024, 1024))
        yield
        self.distro.device_part_info = original_device_part_info

    def test_resize_when_encrypted(self, common_mocks, caplog):
        info = cc_growpart.resize_devices(
            self.resizer, ["/fake_encrypted"], self.distro
        )
        assert len(info) == 2
        assert info[0][0] == "/dev/vdx1"
        assert info[0][2].startswith("no change necessary")
        assert info[1][0] == "/fake_encrypted"
        assert (
            info[1][2]
            == "Successfully resized encrypted volume '/dev/mapper/fake'"
        )
        assert (
            "/dev/mapper/fake is a mapped device pointing to /dev/dm-1"
            in caplog.text
        )
        assert "Determined that /dev/dm-1 is encrypted" in caplog.text

        self.assert_resize_and_cleanup()

    def test_resize_when_unencrypted(self, common_mocks):
        info = cc_growpart.resize_devices(self.resizer, ["/"], self.distro)
        assert len(info) == 1
        assert info[0][0] == "/"
        assert "encrypted" not in info[0][2]
        self.assert_no_resize_or_cleanup()

    def test_encrypted_but_cryptsetup_not_found(
        self, common_mocks, mocker, caplog
    ):
        mocker.patch(
            "cloudinit.config.cc_growpart.subp.which",
            return_value=None,
        )
        info = cc_growpart.resize_devices(
            self.resizer, ["/fake_encrypted"], self.distro
        )

        assert len(info) == 1
        assert "skipped as it is neither encrypted" in info[0][2]
        assert "cryptsetup not found" in caplog.text
        self.assert_no_resize_or_cleanup()

    def test_dmsetup_not_found(self, common_mocks, mocker, caplog):
        def _subp_side_effect(value, **kwargs):
            if value[0] == "dmsetup":
                raise subp.ProcessExecutionError()

        mocker.patch(
            "cloudinit.config.cc_growpart.subp.subp",
            side_effect=_subp_side_effect,
        )
        info = cc_growpart.resize_devices(
            self.resizer, ["/fake_encrypted"], self.distro
        )
        assert len(info) == 1
        assert info[0][0] == "/fake_encrypted"
        assert info[0][1] == "FAILED"
        assert "Resizing device (/dev/mapper/fake) failed" in info[0][2]
        self.assert_no_resize_or_cleanup()

    def test_unparsable_dmsetup(self, common_mocks, mocker, caplog):
        def _subp_side_effect(value, **kwargs):
            if value[0] == "dmsetup":
                return ("2 dependencies",)
            return mock.Mock()

        mocker.patch(
            "cloudinit.config.cc_growpart.subp.subp",
            side_effect=_subp_side_effect,
        )
        info = cc_growpart.resize_devices(
            self.resizer, ["/fake_encrypted"], self.distro
        )
        assert len(info) == 1
        assert info[0][0] == "/fake_encrypted"
        assert info[0][1] == "FAILED"
        assert "Resizing device (/dev/mapper/fake) failed" in info[0][2]
        self.assert_no_resize_or_cleanup()

    def test_missing_keydata(self, common_mocks, mocker, caplog):
        # Note that this will be standard behavior after first boot
        # on a system with an encrypted root partition
        mocker.patch("pathlib.Path.open", side_effect=FileNotFoundError())
        info = cc_growpart.resize_devices(
            self.resizer, ["/fake_encrypted"], self.distro
        )
        assert len(info) == 2
        assert info[0][0] == "/dev/vdx1"
        assert info[0][2].startswith("no change necessary")
        assert info[1][0] == "/fake_encrypted"
        assert info[1][1] == "FAILED"
        assert (
            info[1][2] == "Resizing device (/dev/mapper/fake) failed: Could "
            "not load encryption key. This is expected if the volume has "
            "been previously resized."
        )
        self.assert_no_resize_or_cleanup()

    def test_resize_failed(self, common_mocks, mocker, caplog):
        def _subp_side_effect(value, **kwargs):
            if value[0] == "dmsetup":
                return ("1 dependencies : (vdx1)",)
            elif value[0] == "cryptsetup" and "resize" in value:
                raise subp.ProcessExecutionError()
            return mock.Mock()

        self.m_subp = mocker.patch(
            "cloudinit.config.cc_growpart.subp.subp",
            side_effect=_subp_side_effect,
        )

        info = cc_growpart.resize_devices(
            self.resizer, ["/fake_encrypted"], self.distro
        )
        assert len(info) == 2
        assert info[0][0] == "/dev/vdx1"
        assert info[0][2].startswith("no change necessary")
        assert info[1][0] == "/fake_encrypted"
        assert info[1][1] == "FAILED"
        assert "Resizing device (/dev/mapper/fake) failed" in info[1][2]
        # Assert we still cleanup
        all_subp_args = list(
            chain(*[args[0][0] for args in self.m_subp.call_args_list])
        )
        assert "luksKillSlot" in all_subp_args
        self.m_unlink.assert_called_once()

    def test_resize_skipped(self, common_mocks, mocker, caplog):
        mocker.patch("pathlib.Path.exists", return_value=False)
        info = cc_growpart.resize_devices(
            self.resizer, ["/fake_encrypted"], self.distro
        )
        assert len(info) == 2
        assert info[1] == (
            "/fake_encrypted",
            "SKIPPED",
            "No encryption keyfile found",
        )


class TestLvmResize:
    """Attempt end-to-end scenarios for lvm devices."""

    def _device_part_info_side_effect(self, value):
        return (1024, 1024)

    def _devent2dev_side_effect(self, value):
        if value == "/":
            return "/dev/mapper/rootvg-rootlv", "xfs"
        raise RuntimeError(f"unexpected value {value}")

    def _realpath_side_effect(self, value):
        return "/dev/dm-1" if value.startswith("/dev/mapper") else value

    @pytest.fixture
    def common_mocks(self, mocker):
        """
        Common mocks for cc_growpart.resize_devices,
        expanded to support testing the new LVM resize logic.
        """
        self.distro = MockDistro
        original_device_part_info = self.distro.device_part_info
        self.distro.device_part_info = self._device_part_info_side_effect
        mocker.patch("os.stat")
        mocker.patch("stat.S_ISBLK", return_value=True)
        mocker.patch("stat.S_ISCHR", return_value=False)
        mocker.patch(
            "cloudinit.config.cc_growpart.devent2dev",
            side_effect=self._devent2dev_side_effect,
        )
        mocker.patch(
            "os.path.realpath",
            side_effect=self._realpath_side_effect,
        )

        # Mock is_lvm_device so tests can control LVM detection
        self._is_lvm = False

        def _is_lvm_device_side_effect(dev):
            return self._is_lvm

        mocker.patch(
            "cloudinit.config.cc_growpart.is_lvm_device",
            side_effect=_is_lvm_device_side_effect,
        )

        mocker.patch(
            "cloudinit.config.cc_growpart.is_encrypted", return_value=False
        )

        # Mock commands used by resize_lvm()
        def _fake_lvm_subp(cmd, *args, **kwargs):
            cmdline = " ".join(
                str(c) for c in cmd
            )  # Ensure all items are strings
            # Simulate get_underlying_partition
            if "dmsetup" in cmdline:
                return SubpResult("1 dependencies : (sda2)\n", "")
            # Simulate lvs, vgs introspection
            if "lvs" in cmdline:
                return SubpResult("rootvg\n", "")
            if "vgs" in cmdline:
                return SubpResult("/dev/sda2\n", "")

            # Simulate pvresize
            if "pvresize" in cmdline:
                if getattr(self, "_fail_pvresize", False):
                    raise RuntimeError("pvresize fail")
                return SubpResult("", "")

            # Simulate lvextend
            if "lvextend" in cmdline:
                if getattr(self, "_fail_lvextend", False):
                    raise RuntimeError("lvextend fail")
                return SubpResult("", "")

            return SubpResult("", "")  # default fallback

        self.m_subp = mocker.patch(
            "cloudinit.config.cc_growpart.subp.subp",
            side_effect=_fake_lvm_subp,
        )

        # Allow tests to flip failure modes
        self._fail_pvresize = False
        self._fail_lvextend = False

        # Provide a mock resizer used by resize_devices()
        self.resizer = mock.Mock()
        self.resizer.resize = mock.Mock(return_value=(1024, 2048))
        yield
        # Cleanup
        self.distro.device_part_info = original_device_part_info
        del self._fail_pvresize
        del self._fail_lvextend
        del self._is_lvm

    def test_lvm_resize_flow(self, mocker):
        # Test that LVM resize runs lvs → vgs → pvresize → lvextend.
        # Patch subp.subp to control command outputs
        m_subp = mocker.patch("cloudinit.config.cc_growpart.subp.subp")

        # Sequence of command outputs
        # 1. lvs → returns VG name
        # 2. vgs → returns PV list
        # 3. pvresize pv1
        # 4. pvresize pv2
        # 5. lvextend
        m_subp.side_effect = [
            mocker.Mock(stdout="vg0\n", ok=True),  # lvs
            mocker.Mock(stdout="/dev/xvda2 /dev/xvdb1\n", ok=True),  # vgs
            mocker.Mock(stdout="", ok=True),  # pvresize pv1
            mocker.Mock(stdout="", ok=True),  # pvresize pv2
            mocker.Mock(stdout="", ok=True),  # lvextend
        ]
        cc_growpart.resize_lvm("/dev/mapper/vg0-root")

        # Verify calls
        calls = [
            mocker.call(
                [
                    "lvs",
                    "--noheadings",
                    "-o",
                    "vg_name",
                    "/dev/mapper/vg0-root",
                ]
            ),
            mocker.call(
                [
                    "vgs",
                    "--noheadings",
                    "-o",
                    "pv_name",
                    "--separator",
                    " ",
                    "vg0",
                ]
            ),
            mocker.call(["pvresize", "/dev/xvda2"]),
            mocker.call(["pvresize", "/dev/xvdb1"]),
            mocker.call(
                ["lvextend", "-l", "+100%FREE", "/dev/mapper/vg0-root"]
            ),
        ]

        m_subp.assert_has_calls(calls)

    def test_resize_devices_lvm_success(self, common_mocks, mocker, caplog):
        """
        LVM device:
          - partition resize succeeds
          - pvresize succeeds
          - lvextend succeeds
          - Successfully resized
        """
        self._is_lvm = True
        info = cc_growpart.resize_devices(self.resizer, ["/"], self.distro)
        # Partition resize result present
        assert len(info) == 2
        assert info[0][0] == "/"
        assert info[0][1] == cc_growpart.RESIZE.CHANGED
        assert info[0][2] == ("changed (/dev/sda2) from 1024 to 2048")
        # LVM resize result present
        assert info[1][0] == "/"
        assert info[1][1] == cc_growpart.RESIZE.CHANGED
        assert (
            info[1][2]
            == "Successfully resized LVM device '/dev/mapper/rootvg-rootlv' "
            "(PV and LV resized)"
        )
        assert (
            "/dev/mapper/rootvg-rootlv is a mapped device"
            " pointing to /dev/dm-1" in caplog.text
        )
        assert "pvresize succeeded for /dev/sda2" in caplog.text
        assert (
            "lvextend +100%FREE succeeded for /dev/mapper/rootvg-rootlv"
            in caplog.text
        )

    def test_resize_devices_lvm_lvextend_failure(
        self, common_mocks, mocker, caplog
    ):
        """
        LVM case:
          - lvextend fails
        """
        self._is_lvm = True
        self._fail_lvextend = True  # lvextend error

        info = cc_growpart.resize_devices(self.resizer, ["/"], self.distro)
        # LVM failure
        assert any(
            status == cc_growpart.RESIZE.FAILED and "lvextend fail" in msg
            for _, status, msg in info
        )

    def test_resize_devices_lvm_resize_lv_false(
        self, common_mocks, mocker, caplog
    ):
        """
        LVM device with resize_lv=False:
          - partition resize succeeds
          - pvresize succeeds
          - lvextend is NOT called
          - Successfully resized (PV only)
        """
        self._is_lvm = True
        info = cc_growpart.resize_devices(
            self.resizer, ["/"], self.distro, resize_lv=False
        )
        # Partition resize result present
        assert len(info) == 2
        assert info[0][0] == "/"
        assert info[0][1] == cc_growpart.RESIZE.CHANGED
        assert info[0][2] == ("changed (/dev/sda2) from 1024 to 2048")
        # LVM resize result present (PV only, no LV)
        assert info[1][0] == "/"
        assert info[1][1] == cc_growpart.RESIZE.CHANGED
        assert (
            info[1][2]
            == "Successfully resized LVM device '/dev/mapper/rootvg-rootlv' "
            "(PV resized, LV unchanged)"
        )
        assert "pvresize succeeded for /dev/sda2" in caplog.text
        assert "lvextend" not in caplog.text
        assert (
            "Free space remains available in VG for other LVs" in caplog.text
        )

    def test_resize_devices_lvm_with_growpart_single_pv_skips_pvresize(
        self, common_mocks, mocker, caplog
    ):
        """
        LVM device with ResizeGrowPart (growpart) and single PV VG:
          - partition resize succeeds (growpart handles pvresize)
          - cloud-init skips pvresize (single PV, already done by growpart)
          - lvextend succeeds
          - Successfully resized
        """
        self._is_lvm = True

        # Override the vgs mock to return single PV
        def _fake_lvm_subp_single_pv(cmd, *args, **kwargs):
            cmdline = " ".join(
                str(c) for c in cmd
            )  # Ensure all items are strings
            if "dmsetup" in cmdline:
                return SubpResult("1 dependencies : (sda2)\n", "")
            if "lvs" in cmdline:
                return SubpResult("rootvg\n", "")
            if "vgs" in cmdline:
                return SubpResult("/dev/sda2\n", "")  # Single PV
            if "pvresize" in cmdline:
                if getattr(self, "_fail_pvresize", False):
                    raise RuntimeError("pvresize fail")
                return SubpResult("", "")
            if "lvextend" in cmdline:
                if getattr(self, "_fail_lvextend", False):
                    raise RuntimeError("lvextend fail")
                return SubpResult("", "")
            return SubpResult("", "")

        def _fake_subp_with_growpart(cmd, *args, **kwargs):
            cmdline = " ".join(
                str(c) for c in cmd
            )  # Ensure all items are strings
            # Handle growpart commands
            if "growpart" in cmdline:
                if "--dry-run" in cmdline:
                    # Simulate dry-run success
                    return SubpResult("", "")
                # Simulate actual growpart success
                return SubpResult("", "")
            # Handle LVM commands
            return _fake_lvm_subp_single_pv(cmd, *args, **kwargs)

        # Override the subp.subp mock from common_mocks
        self.m_subp.side_effect = _fake_subp_with_growpart

        # Mock get_tmp_exec_path and tempdir for ResizeGrowPart
        self.distro.get_tmp_exec_path = mock.Mock(return_value="/tmp")
        tempdir_mock = mocker.patch(
            "cloudinit.config.cc_growpart.temp_utils.tempdir"
        )
        tempdir_mock.return_value.__enter__.return_value = "/tmp/test"
        tempdir_mock.return_value.__exit__.return_value = None

        # Mock get_size to return different values before/after resize
        # First call returns smaller size (before), second call returns
        # larger (after)
        mocker.patch(
            "cloudinit.config.cc_growpart.get_size",
            side_effect=[
                1024 * 1024 * 1024,
                2 * 1024 * 1024 * 1024,
            ],  # 1GB -> 2GB
        )

        # Use actual ResizeGrowPart instead of mock
        growpart_resizer = cc_growpart.ResizeGrowPart(self.distro)
        info = cc_growpart.resize_devices(
            growpart_resizer, ["/"], self.distro, resize_lv=True
        )
        # Partition resize result present
        assert len(info) == 2
        assert info[0][0] == "/"
        assert info[0][1] == cc_growpart.RESIZE.CHANGED
        # LVM resize result present - should indicate PV already resized
        assert info[1][0] == "/"
        assert info[1][1] == cc_growpart.RESIZE.CHANGED
        assert "PV already resized" in info[1][2]
        # Verify pvresize was NOT called by cloud-init (growpart did it)
        assert "pvresize succeeded" not in caplog.text
        # Verify lvextend WAS called
        assert (
            "lvextend +100%FREE succeeded for /dev/mapper/rootvg-rootlv"
            in caplog.text
        )
        # Verify we detected single PV
        assert "has single PV, skipping pvresize" in caplog.text

    def test_resize_devices_lvm_with_growpart_multi_pv_resizes_all(
        self, common_mocks, mocker, caplog
    ):
        """
        LVM device with ResizeGrowPart (growpart) and multi-PV VG:
          - partition resize succeeds (growpart handles pvresize for one PV)
          - cloud-init resizes ALL PVs (growpart only resized one)
          - lvextend succeeds
          - Successfully resized
        """
        self._is_lvm = True
        # Track pvresize calls
        pvresize_calls = []

        def _fake_lvm_subp_multi_pv(cmd, *args, **kwargs):
            cmdline = " ".join(
                str(c) for c in cmd
            )  # Ensure all items are strings
            if "dmsetup" in cmdline:
                return SubpResult("1 dependencies : (sda2)\n", "")
            if "lvs" in cmdline:
                return SubpResult("rootvg\n", "")
            if "vgs" in cmdline:
                return SubpResult("/dev/sda2 /dev/sdb1\n", "")  # Multiple PVs
            if "pvresize" in cmdline:
                pvresize_calls.append(cmd)
                if getattr(self, "_fail_pvresize", False):
                    raise RuntimeError("pvresize fail")
                return SubpResult("", "")
            if "lvextend" in cmdline:
                if getattr(self, "_fail_lvextend", False):
                    raise RuntimeError("lvextend fail")
                return SubpResult("", "")
            return SubpResult("", "")

        def _fake_subp_with_growpart(cmd, *args, **kwargs):
            cmdline = " ".join(
                str(c) for c in cmd
            )  # Ensure all items are strings
            # Handle growpart commands
            if "growpart" in cmdline:
                if "--dry-run" in cmdline:
                    # Simulate dry-run success
                    return SubpResult("", "")
                # Simulate actual growpart success
                return SubpResult("", "")
            # Handle LVM commands
            return _fake_lvm_subp_multi_pv(cmd, *args, **kwargs)

        # Override the subp.subp mock from common_mocks
        self.m_subp.side_effect = _fake_subp_with_growpart

        # Mock get_tmp_exec_path and tempdir for ResizeGrowPart
        self.distro.get_tmp_exec_path = mock.Mock(return_value="/tmp")
        tempdir_mock = mocker.patch(
            "cloudinit.config.cc_growpart.temp_utils.tempdir"
        )
        tempdir_mock.return_value.__enter__.return_value = "/tmp/test"
        tempdir_mock.return_value.__exit__.return_value = None

        # Mock get_size to return different values before/after resize
        # First call returns smaller size (before), second call returns
        # larger (after)
        mocker.patch(
            "cloudinit.config.cc_growpart.get_size",
            side_effect=[
                1024 * 1024 * 1024,
                2 * 1024 * 1024 * 1024,
            ],  # 1GB -> 2GB
        )

        # Use actual ResizeGrowPart instead of mock
        growpart_resizer = cc_growpart.ResizeGrowPart(self.distro)
        info = cc_growpart.resize_devices(
            growpart_resizer, ["/"], self.distro, resize_lv=True
        )
        # Partition resize result present
        assert len(info) == 2
        assert info[0][0] == "/"
        assert info[0][1] == cc_growpart.RESIZE.CHANGED
        # LVM resize result present - should indicate PVs were resized
        assert info[1][0] == "/"
        assert info[1][1] == cc_growpart.RESIZE.CHANGED
        assert "PV and LV resized" in info[1][2]
        # Verify pvresize WAS called by cloud-init for all PVs
        assert len(pvresize_calls) == 2  # Both PVs should be resized
        assert any("/dev/sda2" in str(call) for call in pvresize_calls)
        assert any("/dev/sdb1" in str(call) for call in pvresize_calls)
        # Verify we detected multi-PV
        assert "has 2 PVs, resizing all PVs" in caplog.text
        # Verify lvextend WAS called
        assert (
            "lvextend +100%FREE succeeded for /dev/mapper/rootvg-rootlv"
            in caplog.text
        )

    def test_resize_lvm_resize_lv_false(self, mocker):
        """Test that resize_lvm with resize_lv=False skips lvextend."""
        m_subp = mocker.patch("cloudinit.config.cc_growpart.subp.subp")
        m_subp.side_effect = [
            mocker.Mock(stdout="vg0\n", ok=True),  # lvs
            mocker.Mock(stdout="/dev/xvda2\n", ok=True),  # vgs
            mocker.Mock(stdout="", ok=True),  # pvresize
            # Note: no lvextend call expected
        ]
        status, message = cc_growpart.resize_lvm(
            "/dev/mapper/vg0-root", resize_lv=False
        )
        assert status == cc_growpart.RESIZE.CHANGED
        assert "(PV resized, LV unchanged)" in message
        # Verify lvextend was NOT called
        lvextend_calls = [
            call for call in m_subp.call_args_list if "lvextend" in str(call)
        ]
        assert len(lvextend_calls) == 0

    def test_resize_lvm_skip_pvresize(self, mocker):
        """Test that resize_lvm with skip_pvresize=True skips pvresize."""
        m_subp = mocker.patch("cloudinit.config.cc_growpart.subp.subp")
        m_subp.side_effect = [
            mocker.Mock(stdout="vg0\n", ok=True),  # lvs
            mocker.Mock(stdout="/dev/xvda2\n", ok=True),  # vgs
            mocker.Mock(stdout="", ok=True),  # lvextend
            # Note: no pvresize call expected
        ]
        status, message = cc_growpart.resize_lvm(
            "/dev/mapper/vg0-root", skip_pvresize=True
        )
        assert status == cc_growpart.RESIZE.CHANGED
        assert "PV already resized" in message
        # Verify pvresize was NOT called
        pvresize_calls = [
            call for call in m_subp.call_args_list if "pvresize" in str(call)
        ]
        assert len(pvresize_calls) == 0
        # Verify lvextend WAS called
        lvextend_calls = [
            call for call in m_subp.call_args_list if "lvextend" in str(call)
        ]
        assert len(lvextend_calls) == 1


def simple_device_part_info(devpath):
    # simple stupid return (/dev/vda, 1) for /dev/vda
    match = re.search("([^0-9]*)([0-9]*)$", devpath)

    # just some validation to check if the regex doesn't match.
    # prevents AttributeError from None.group()
    if not match:
        raise ValueError(f"Invalid device path: {devpath}")
    return match.group(1), match.group(2)


class Bunch:
    def __init__(self, **kwds):
        self.__dict__.update(kwds)


class TestDevicePartInfo:
    @pytest.mark.parametrize(
        "devpath, expected, raised_exception",
        (
            pytest.param(
                "/dev/vtbd0p2",
                ("/dev/vtbd0", "2"),
                does_not_raise(),
                id="gpt_partition",
            ),
            pytest.param(
                "/dev/vbd0s3a",
                ("/dev/vbd0", "3a"),
                does_not_raise(),
                id="bsd_mbr_slice_and_partition",
            ),
            pytest.param(
                "zroot/ROOT/default",
                (),
                pytest.raises(ValueError),
                id="zfs_dataset",
            ),
        ),
    )
    def test_device_part_info(self, devpath, expected, raised_exception):
        with raised_exception:
            assert expected == BSD.device_part_info(devpath)


class TestGrowpartSchema:
    @pytest.mark.parametrize(
        "config, expectation",
        (
            ({"growpart": {"mode": "off"}}, does_not_raise()),
            (
                {"growpart": {"mode": False}},
                pytest.raises(
                    SchemaValidationError,
                    match=re.escape(
                        "Cloud config schema deprecations: "
                        "growpart.mode:  Changed in version 22.3. "
                        "Specifying a boolean ``false`` value for "
                        "**mode** is deprecated. Use the string ``'off'`` "
                        "instead."
                    ),
                ),
            ),
            (
                {"growpart": {"mode": "false"}},
                pytest.raises(
                    SchemaValidationError,
                    match=re.escape(
                        "growpart.mode: 'false' is not one of [False"
                    ),
                ),
            ),
            (
                {"growpart": {"mode": "a"}},
                pytest.raises(
                    SchemaValidationError,
                    match=re.escape(
                        "growpart.mode: 'a' is not one of ['auto',"
                    ),
                ),
            ),
            (
                {"growpart": {"devices": "/"}},
                pytest.raises(
                    SchemaValidationError, match="'/' is not of type 'array'"
                ),
            ),
            (
                {"growpart": {"ignore_growroot_disabled": "off"}},
                pytest.raises(
                    SchemaValidationError,
                    match="'off' is not of type 'boolean'",
                ),
            ),
            (
                {"growpart": {"a": "b"}},
                pytest.raises(
                    SchemaValidationError,
                    match="Additional properties are not allowed",
                ),
            ),
        ),
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, expectation):
        """Assert expected schema validation and error messages."""
        schema = get_schema()
        with expectation:
            validate_cloudconfig_schema(config, schema, strict=True)
