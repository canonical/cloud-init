# This file is part of cloud-init. See LICENSE file for license information.
# pylint: disable=attribute-defined-outside-init

import random
import tempfile

import pytest

from cloudinit.config import cc_disk_setup
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import (
    CiTestCase,
    ExitStack,
    mock,
    skipUnlessJsonSchema,
)


class TestIsDiskUsed:
    def setup_method(self):
        self.patches = ExitStack()
        mod_name = "cloudinit.config.cc_disk_setup"
        self.enumerate_disk = self.patches.enter_context(
            mock.patch("{0}.enumerate_disk".format(mod_name))
        )
        self.check_fs = self.patches.enter_context(
            mock.patch("{0}.check_fs".format(mod_name))
        )

    def teardown_method(self):
        self.patches.close()

    def test_multiple_child_nodes_returns_true(self):
        self.enumerate_disk.return_value = (mock.MagicMock() for _ in range(2))
        self.check_fs.return_value = (mock.MagicMock(), None, mock.MagicMock())
        assert cc_disk_setup.is_disk_used(mock.MagicMock())

    def test_valid_filesystem_returns_true(self):
        self.enumerate_disk.return_value = (mock.MagicMock() for _ in range(1))
        self.check_fs.return_value = (
            mock.MagicMock(),
            "ext4",
            mock.MagicMock(),
        )
        assert cc_disk_setup.is_disk_used(mock.MagicMock())

    def test_one_child_nodes_and_no_fs_returns_false(self):
        self.enumerate_disk.return_value = (mock.MagicMock() for _ in range(1))
        self.check_fs.return_value = (mock.MagicMock(), None, mock.MagicMock())
        assert not cc_disk_setup.is_disk_used(mock.MagicMock())


class TestGetMbrHddSize:
    def _test_for_sector_size(self, sector_size):
        size_in_bytes = random.randint(10000, 10000000) * 512
        size_in_sectors = size_in_bytes / sector_size

        def _subp(cmd, *args, **kwargs):
            assert 3 == len(cmd)
            if "--getsize64" in cmd:
                return size_in_bytes, None
            elif "--getss" in cmd:
                return sector_size, None
            raise RuntimeError("Unexpected blockdev command called")

        with mock.patch.object(cc_disk_setup.subp, "subp", _subp):
            assert size_in_sectors == cc_disk_setup.get_hdd_size("/dev/sda1")

    def test_size_for_512_byte_sectors(self):
        self._test_for_sector_size(512)

    def test_size_for_1024_byte_sectors(self):
        self._test_for_sector_size(1024)

    def test_size_for_2048_byte_sectors(self):
        self._test_for_sector_size(2048)

    def test_size_for_4096_byte_sectors(self):
        self._test_for_sector_size(4096)


class TestGetPartitionMbrLayout:
    def test_single_partition_using_boolean(self):
        assert ",,83" == cc_disk_setup.get_partition_mbr_layout(1000, True)

    def test_single_partition_using_list(self):
        disk_size = random.randint(1000000, 1000000000000)
        assert ",,83" == cc_disk_setup.get_partition_mbr_layout(
            disk_size, [100]
        )

    def test_half_and_half(self):
        disk_size = random.randint(1000000, 1000000000000)
        expected_partition_size = int(float(disk_size) / 2)
        assert ",{0},83\n,,83".format(
            expected_partition_size
        ) == cc_disk_setup.get_partition_mbr_layout(disk_size, [50, 50])

    def test_thirds_with_different_partition_type(self):
        disk_size = random.randint(1000000, 1000000000000)
        expected_partition_size = int(float(disk_size) * 0.33)
        assert ",{0},83\n,,82".format(
            expected_partition_size
        ) == cc_disk_setup.get_partition_mbr_layout(disk_size, [33, [66, 82]])


class TestUpdateFsSetupDevices:
    def test_regression_1634678(self):
        # Cf. https://bugs.launchpad.net/cloud-init/+bug/1634678
        fs_setup = {
            "partition": "auto",
            "device": "/dev/xvdb1",
            "overwrite": False,
            "label": "test",
            "filesystem": "ext4",
        }

        cc_disk_setup.update_fs_setup_devices(
            [fs_setup], lambda device: device
        )

        assert {
            "_origname": "/dev/xvdb1",
            "partition": "auto",
            "device": "/dev/xvdb1",
            "overwrite": False,
            "label": "test",
            "filesystem": "ext4",
        } == fs_setup

    def test_dotted_devname(self):
        fs_setup = {
            "partition": "auto",
            "device": "ephemeral0.0",
            "label": "test2",
            "filesystem": "xfs",
        }

        cc_disk_setup.update_fs_setup_devices(
            [fs_setup], lambda device: device
        )

        assert {
            "_origname": "ephemeral0.0",
            "_partition": "auto",
            "partition": "0",
            "device": "ephemeral0",
            "label": "test2",
            "filesystem": "xfs",
        } == fs_setup

    def test_dotted_devname_populates_partition(self):
        fs_setup = {
            "device": "ephemeral0.1",
            "label": "test2",
            "filesystem": "xfs",
        }
        cc_disk_setup.update_fs_setup_devices(
            [fs_setup], lambda device: device
        )
        assert {
            "_origname": "ephemeral0.1",
            "device": "ephemeral0",
            "partition": "1",
            "label": "test2",
            "filesystem": "xfs",
        } == fs_setup


class TestPurgeDisk:
    @mock.patch(
        "cloudinit.config.cc_disk_setup.read_parttbl", return_value=None
    )
    def test_purge_disk_ptable(self, *args):
        pseudo_device = tempfile.NamedTemporaryFile()

        cc_disk_setup.purge_disk_ptable(pseudo_device.name)

        with pseudo_device as f:
            actual = f.read()

        expected = b"\0" * (1024 * 1024)

        assert expected == actual


@mock.patch(
    "cloudinit.config.cc_disk_setup.assert_and_settle_device",
    return_value=None,
)
@mock.patch(
    "cloudinit.config.cc_disk_setup.find_device_node",
    return_value=("/dev/xdb1", False),
)
@mock.patch("cloudinit.config.cc_disk_setup.device_type", return_value=None)
@mock.patch("cloudinit.config.cc_disk_setup.subp.subp", return_value=("", ""))
class TestMkfsCommandHandling(CiTestCase):
    with_logs = True

    def test_with_cmd(self, subp, *args):
        """mkfs honors cmd and logs warnings when extra_opts or overwrite are
        provided."""
        cc_disk_setup.mkfs(
            {
                "cmd": "mkfs -t %(filesystem)s -L %(label)s %(device)s",
                "filesystem": "ext4",
                "device": "/dev/xdb1",
                "label": "with_cmd",
                "extra_opts": ["should", "generate", "warning"],
                "overwrite": "should generate warning too",
            }
        )

        assert (
            "extra_opts "
            "ignored because cmd was specified: mkfs -t ext4 -L with_cmd "
            "/dev/xdb1" in self.logs.getvalue()
        )
        assert (
            "overwrite "
            "ignored because cmd was specified: mkfs -t ext4 -L with_cmd "
            "/dev/xdb1" in self.logs.getvalue()
        )

        subp.assert_called_once_with(
            "mkfs -t ext4 -L with_cmd /dev/xdb1", shell=True
        )

    @mock.patch("cloudinit.config.cc_disk_setup.subp.which")
    def test_overwrite_and_extra_opts_without_cmd(self, m_which, subp, *args):
        """mkfs observes extra_opts and overwrite settings when cmd is not
        present."""
        m_which.side_effect = lambda p: {"mkfs.ext4": "/sbin/mkfs.ext4"}[p]
        cc_disk_setup.mkfs(
            {
                "filesystem": "ext4",
                "device": "/dev/xdb1",
                "label": "without_cmd",
                "extra_opts": ["are", "added"],
                "overwrite": True,
            }
        )

        subp.assert_called_once_with(
            [
                "/sbin/mkfs.ext4",
                "-L",
                "without_cmd",
                "-F",
                "are",
                "added",
                "/dev/xdb1",
            ],
            shell=False,
        )

    @mock.patch("cloudinit.config.cc_disk_setup.subp.which")
    def test_mkswap(self, m_which, subp, *args):
        """mkfs observes extra_opts and overwrite settings when cmd is not
        present."""
        m_which.side_effect = iter([None, "/sbin/mkswap"])
        cc_disk_setup.mkfs(
            {
                "filesystem": "swap",
                "device": "/dev/xdb1",
                "label": "swap",
                "overwrite": True,
            }
        )

        assert [
            mock.call("mkfs.swap"),
            mock.call("mkswap"),
        ] == m_which.call_args_list
        subp.assert_called_once_with(
            ["/sbin/mkswap", "-L", "swap", "-f", "/dev/xdb1"], shell=False
        )


@skipUnlessJsonSchema()
class TestDebugSchema:
    """Directly test schema rather than through handle."""

    @pytest.mark.parametrize(
        "config, error_msg",
        (
            # Valid schemas tested by meta.examples in test_schema
            # Invalid schemas
            ({"disk_setup": 1}, "disk_setup: 1 is not of type 'object'"),
            ({"fs_setup": 1}, "fs_setup: 1 is not of type 'array'"),
            (
                {"device_aliases": 1},
                "device_aliases: 1 is not of type 'object'",
            ),
        ),
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        """Assert expected schema validation and error messages."""
        # New-style schema $defs exist in config/cloud-init-schema*.json
        schema = get_schema()
        with pytest.raises(SchemaValidationError, match=error_msg):
            validate_cloudconfig_schema(config, schema, strict=True)

    @pytest.mark.parametrize(
        "config",
        (
            (
                {
                    "disk_setup": {
                        "/dev/disk/by-id/google-home": {
                            "table_type": "gpt",
                            "layout": [
                                [100, "933AC7E1-2EB4-4F13-B844-0E14E2AEF915"]
                            ],
                        }
                    }
                }
            ),
        ),
    )
    @skipUnlessJsonSchema()
    def test_valid_schema(self, config):
        """Assert expected schema validation and no error messages."""
        schema = get_schema()
        validate_cloudconfig_schema(config, schema, strict=True)
