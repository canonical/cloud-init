# This file is part of cloud-init. See LICENSE file for license information.
# pylint: disable=attribute-defined-outside-init

import errno
import logging
import os
import re
import shutil
import stat
import unittest
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
    TestCase,
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


class TestDisabled(unittest.TestCase):
    def setUp(self):
        super(TestDisabled, self).setUp()
        self.name = "growpart"
        self.cloud = None
        self.args = []

        self.handle = cc_growpart.handle

    def test_mode_off(self):
        # Test that nothing is done if mode is off.

        # this really only verifies that resizer_factory isn't called
        config = {"growpart": {"mode": "off"}}

        with mock.patch.object(cc_growpart, "resizer_factory") as mockobj:
            self.handle(self.name, config, self.cloud, self.args)
            self.assertEqual(mockobj.call_count, 0)


class TestConfig(TestCase):
    def setUp(self):
        super(TestConfig, self).setUp()
        self.name = "growpart"
        self.paths = None
        self.distro = mock.Mock()
        self.cloud = cloud.Cloud(None, self.paths, None, self.distro, None)
        self.log = logging.getLogger("TestConfig")
        self.args = []

        self.handle = cc_growpart.handle
        self.tmppath = "/tmp/cloudinit-test-file"
        self.tmpdir = os.scandir("/tmp")
        self.tmpfile = open(self.tmppath, "w")

    def tearDown(self):
        self.tmpfile.close()
        os.remove(self.tmppath)
        super().tearDown()

    @mock.patch.object(os.path, "isfile", return_value=False)
    def test_no_resizers_auto_is_fine(self, m_isfile):
        with mock.patch.object(
            subp, "subp", return_value=SubpResult(HELP_GROWPART_NO_RESIZE, "")
        ) as mockobj:
            config = {"growpart": {"mode": "auto"}}
            self.handle(self.name, config, self.cloud, self.args)

            mockobj.assert_has_calls(
                [
                    mock.call(
                        ["growpart", "--help"], update_env={"LANG": "C"}
                    ),
                    mock.call(
                        ["gpart", "help"], update_env={"LANG": "C"}, rcs=[0, 1]
                    ),
                ]
            )

    def test_no_resizers_mode_growpart_is_exception(self):
        with mock.patch.object(
            subp, "subp", return_value=SubpResult(HELP_GROWPART_NO_RESIZE, "")
        ) as mockobj:
            config = {"growpart": {"mode": "growpart"}}
            self.assertRaises(
                ValueError,
                self.handle,
                self.name,
                config,
                self.cloud,
                self.args,
            )

            mockobj.assert_called_once_with(
                ["growpart", "--help"], update_env={"LANG": "C"}
            )

    def test_mode_auto_prefers_growpart(self):
        with mock.patch.object(
            subp, "subp", return_value=SubpResult(HELP_GROWPART_RESIZE, "")
        ) as mockobj:
            ret = cc_growpart.resizer_factory(
                mode="auto", distro=mock.Mock(), devices=["/"]
            )
            self.assertIsInstance(ret, cc_growpart.ResizeGrowPart)

            mockobj.assert_called_once_with(
                ["growpart", "--help"], update_env={"LANG": "C"}
            )

    @mock.patch.object(temp_utils, "mkdtemp", return_value="/tmp/much-random")
    @mock.patch.object(stat, "S_ISDIR", return_value=False)
    @mock.patch.object(os.path, "samestat", return_value=True)
    @mock.patch.object(os.path, "join", return_value="/tmp")
    @mock.patch.object(os, "scandir", return_value=Scanner())
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
            self.assertIsInstance(ret, cc_growpart.ResizeGrowPart)
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

    @mock.patch.object(os.path, "isfile", return_value=True)
    def test_mode_use_growfs_on_root(self, m_isfile):
        with mock.patch.object(
            subp, "subp", return_value=SubpResult("File not found", "")
        ) as mockobj:
            ret = cc_growpart.resizer_factory(
                mode="auto", distro=mock.Mock(), devices=["/"]
            )
            self.assertIsInstance(ret, cc_growpart.ResizeGrowFS)

            mockobj.assert_has_calls(
                [
                    mock.call(
                        ["growpart", "--help"], update_env={"LANG": "C"}
                    ),
                ]
            )

    def test_mode_auto_falls_back_to_gpart(self):
        with mock.patch.object(
            subp, "subp", return_value=SubpResult("", HELP_GPART)
        ) as mockobj:
            ret = cc_growpart.resizer_factory(
                mode="auto", distro=mock.Mock(), devices=["/", "/opt"]
            )
            self.assertIsInstance(ret, cc_growpart.ResizeGpart)

            mockobj.assert_has_calls(
                [
                    mock.call(
                        ["growpart", "--help"], update_env={"LANG": "C"}
                    ),
                    mock.call(
                        ["gpart", "help"], update_env={"LANG": "C"}, rcs=[0, 1]
                    ),
                ]
            )

    @mock.patch.object(os.path, "isfile", return_value=True)
    def test_mode_auto_falls_back_to_growfs(self, m_isfile):
        with mock.patch.object(
            subp, "subp", return_value=SubpResult("", HELP_GPART)
        ) as mockobj:
            ret = cc_growpart.resizer_factory(
                mode="auto", distro=mock.Mock(), devices=["/"]
            )
            self.assertIsInstance(ret, cc_growpart.ResizeGrowFS)

            mockobj.assert_has_calls(
                [
                    mock.call(
                        ["growpart", "--help"], update_env={"LANG": "C"}
                    ),
                ]
            )

    def test_handle_with_no_growpart_entry(self):
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

            self.handle(self.name, {}, self.cloud, self.args)

            factory.assert_called_once_with(
                "auto", distro=self.distro, devices=["/"]
            )
            rsdevs.assert_called_once_with(myresizer, ["/"], self.distro)


class TestResize(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.name = "growpart"
        self.distro = MockDistro()
        self.log = logging.getLogger("TestResize")

    def test_simple_devices(self):
        # test simple device list
        # this patches out devent2dev, os.stat, and device_part_info
        # so in the end, doesn't test a lot
        devs = ["/dev/XXda1", "/dev/YYda2"]
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
        enoent = ["/dev/NOENT"]
        real_stat = os.stat
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
            return real_stat(path)

        opinfo = self.distro.device_part_info
        try:
            self.distro.device_part_info = simple_device_part_info
            os.stat = mystat

            resized = cc_growpart.resize_devices(
                myresizer(), devs + enoent, self.distro
            )

            def find(name, res):
                for f in res:
                    if f[0] == name:
                        return f
                return None

            self.assertEqual(
                cc_growpart.RESIZE.NOCHANGE, find("/dev/XXda1", resized)[1]
            )
            self.assertEqual(
                cc_growpart.RESIZE.CHANGED, find("/dev/YYda2", resized)[1]
            )
            self.assertEqual(
                cc_growpart.RESIZE.SKIPPED, find(enoent[0], resized)[1]
            )
        finally:
            self.distro.device_part_info = opinfo
            os.stat = real_stat


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
        self.distro = MockDistro
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
        assert "skipped as it is not encrypted" in info[0][2]
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
        assert (
            "Resizing encrypted device (/dev/mapper/fake) failed" in info[0][2]
        )
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
        assert (
            "Resizing encrypted device (/dev/mapper/fake) failed" in info[0][2]
        )
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
            info[1][2]
            == "Resizing encrypted device (/dev/mapper/fake) failed: Could "
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
        assert (
            "Resizing encrypted device (/dev/mapper/fake) failed" in info[1][2]
        )
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


def simple_device_part_info(devpath):
    # simple stupid return (/dev/vda, 1) for /dev/vda
    ret = re.search("([^0-9]*)([0-9]*)$", devpath)
    x = (ret.group(1), ret.group(2))
    return x


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
                "zroot/ROOТ/default",
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
                    match=(
                        "Cloud config schema deprecations: "
                        "growpart.mode:  Changed in version 22.3. "
                        "Specifying a boolean ``false`` value for "
                        "``mode`` is deprecated. Use the string ``'off'`` "
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
