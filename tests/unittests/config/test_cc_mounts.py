# This file is part of cloud-init. See LICENSE file for license information.
# pylint: disable=attribute-defined-outside-init

import math
import os.path
import re
import textwrap
from collections import namedtuple
from unittest import mock

import pytest
from pytest import approx

from cloudinit.config import cc_mounts
from cloudinit.config.cc_mounts import (
    GB,
    MB,
    create_swapfile,
    suggested_swapsize,
)
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from cloudinit.subp import ProcessExecutionError
from tests.unittests import helpers as test_helpers

M_PATH = "cloudinit.config.cc_mounts."


class TestSanitizeDevname:
    def _touch(self, path, new_root):
        path = os.path.join(new_root, path.lstrip("/"))
        basedir = os.path.dirname(path)
        if not os.path.exists(basedir):
            os.makedirs(basedir)
        open(path, "a").close()

    def _makedirs(self, directory, new_root):
        directory = os.path.join(new_root, directory.lstrip("/"))
        if not os.path.exists(directory):
            os.makedirs(directory)

    def mock_existence_of_disk(self, disk_path, new_root):
        self._touch(disk_path, new_root)
        self._makedirs(
            os.path.join("/sys/block", disk_path.split("/")[-1]), new_root
        )

    def mock_existence_of_partition(
        self, disk_path, partition_number, new_root
    ):
        self.mock_existence_of_disk(disk_path, new_root)
        self._touch(disk_path + str(partition_number), new_root)
        disk_name = disk_path.split("/")[-1]
        self._makedirs(
            os.path.join(
                "/sys/block", disk_name, disk_name + str(partition_number)
            ),
            new_root,
        )

    def test_existent_full_disk_path_is_returned(self, fake_filesystem):
        disk_path = "/dev/sda"
        self.mock_existence_of_disk(disk_path, fake_filesystem)
        assert disk_path == cc_mounts.sanitize_devname(
            disk_path, lambda x: None
        )

    def test_existent_disk_name_returns_full_path(self, fake_filesystem):
        disk_name = "sda"
        disk_path = "/dev/" + disk_name
        self.mock_existence_of_disk(disk_path, fake_filesystem)
        assert disk_path == cc_mounts.sanitize_devname(
            disk_name, lambda x: None
        )

    def test_existent_meta_disk_is_returned(self, fake_filesystem):
        actual_disk_path = "/dev/sda"
        self.mock_existence_of_disk(actual_disk_path, fake_filesystem)
        assert actual_disk_path == cc_mounts.sanitize_devname(
            "ephemeral0",
            lambda x: actual_disk_path,
        )

    def test_existent_meta_partition_is_returned(self, fake_filesystem):
        disk_name, partition_part = "/dev/sda", "1"
        actual_partition_path = disk_name + partition_part
        self.mock_existence_of_partition(
            disk_name, partition_part, fake_filesystem
        )
        assert actual_partition_path == cc_mounts.sanitize_devname(
            "ephemeral0.1",
            lambda x: disk_name,
        )

    def test_existent_meta_partition_with_p_is_returned(self, fake_filesystem):
        disk_name, partition_part = "/dev/sda", "p1"
        actual_partition_path = disk_name + partition_part
        self.mock_existence_of_partition(
            disk_name, partition_part, fake_filesystem
        )
        assert actual_partition_path == cc_mounts.sanitize_devname(
            "ephemeral0.1",
            lambda x: disk_name,
        )

    def test_first_partition_returned_if_existent_disk_is_partitioned(
        self, fake_filesystem
    ):
        disk_name, partition_part = "/dev/sda", "1"
        actual_partition_path = disk_name + partition_part
        self.mock_existence_of_partition(
            disk_name, partition_part, fake_filesystem
        )
        assert actual_partition_path == cc_mounts.sanitize_devname(
            "ephemeral0",
            lambda x: disk_name,
        )

    def test_nth_partition_returned_if_requested(self, fake_filesystem):
        disk_name, partition_part = "/dev/sda", "3"
        actual_partition_path = disk_name + partition_part
        self.mock_existence_of_partition(
            disk_name, partition_part, fake_filesystem
        )
        assert actual_partition_path == cc_mounts.sanitize_devname(
            "ephemeral0.3",
            lambda x: disk_name,
        )

    def test_transformer_returning_none_returns_none(self, fake_filesystem):
        assert (
            cc_mounts.sanitize_devname(
                "ephemeral0",
                lambda x: None,
            )
            is None
        )

    def test_missing_device_returns_none(self, fake_filesystem):
        assert (
            cc_mounts.sanitize_devname(
                "/dev/sda",
                None,
            )
            is None
        )

    def test_missing_sys_returns_none(self, fake_filesystem):
        disk_path = "/dev/sda"
        self._makedirs(disk_path, fake_filesystem)
        assert (
            cc_mounts.sanitize_devname(
                disk_path,
                None,
            )
            is None
        )

    def test_existent_disk_but_missing_partition_returns_none(
        self, fake_filesystem
    ):
        disk_path = "/dev/sda"
        self.mock_existence_of_disk(disk_path, fake_filesystem)
        assert (
            cc_mounts.sanitize_devname(
                "ephemeral0.1",
                lambda x: disk_path,
            )
            is None
        )

    def test_network_device_returns_network_device(self, fake_filesystem):
        disk_path = "netdevice:/path"
        assert disk_path == cc_mounts.sanitize_devname(
            disk_path,
            None,
        )

    def test_device_aliases_remapping(self, fake_filesystem):
        disk_path = "/dev/sda"
        self.mock_existence_of_disk(disk_path, fake_filesystem)
        assert disk_path == cc_mounts.sanitize_devname(
            "mydata", lambda x: None, {"mydata": disk_path}
        )


class TestSwapFileCreation:
    @pytest.fixture(autouse=True)
    def setup(self, mocker, fake_filesystem: str):
        self.new_root = fake_filesystem
        self.swap_path = os.path.join(fake_filesystem, "swap.img")
        fstab_path = os.path.join(fake_filesystem, "etc/fstab")
        self._makedirs("/etc")

        self.m_fstab = mocker.patch(f"{M_PATH}FSTAB_PATH", fstab_path)
        self.m_subp = mocker.patch(f"{M_PATH}subp.subp")
        self.m_mounts = mocker.patch(
            f"{M_PATH}util.mounts",
            return_value={
                "/dev/sda1": {
                    "fstype": "ext4",
                    "mountpoint": "/",
                    "opts": "rw,relatime,discard",
                }
            },
        )

        self.mock_cloud = mock.Mock()
        self.mock_log = mock.Mock()
        self.mock_cloud.device_name_to_device = self.device_name_to_device

        self.cc = {
            "swap": {
                "filename": self.swap_path,
                "size": "512",
                "maxsize": "512",
            }
        }

    def _makedirs(self, directory):
        directory = os.path.join(self.new_root, directory.lstrip("/"))
        if not os.path.exists(directory):
            os.makedirs(directory)

    def device_name_to_device(self, path):
        if path == "swap":
            return self.swap_path
        else:
            dev = None

        return dev

    @mock.patch("cloudinit.util.get_mount_info")
    @mock.patch("cloudinit.util.kernel_version")
    def test_swap_creation_method_fallocate_on_xfs(
        self, m_kernel_version, m_get_mount_info
    ):
        m_kernel_version.return_value = (4, 20)
        m_get_mount_info.return_value = ["", "xfs"]

        cc_mounts.handle("", self.cc, self.mock_cloud, [])
        self.m_subp.assert_has_calls(
            [
                mock.call(
                    ["fallocate", "-l", "0M", self.swap_path], capture=True
                ),
                mock.call(["mkswap", self.swap_path]),
                mock.call(["swapon", "-a"]),
            ]
        )

    @mock.patch("cloudinit.util.get_mount_info")
    @mock.patch("cloudinit.util.kernel_version")
    def test_swap_creation_method_xfs(
        self, m_kernel_version, m_get_mount_info
    ):
        m_kernel_version.return_value = (3, 18)
        m_get_mount_info.return_value = ["", "xfs"]

        cc_mounts.handle("", self.cc, self.mock_cloud, [])
        self.m_subp.assert_has_calls(
            [
                mock.call(
                    [
                        "dd",
                        "if=/dev/zero",
                        "of=" + self.swap_path,
                        "bs=1M",
                        "count=0",
                    ],
                    capture=True,
                ),
                mock.call(["mkswap", self.swap_path]),
                mock.call(["swapon", "-a"]),
            ]
        )

    @mock.patch("cloudinit.util.get_mount_info")
    @mock.patch("cloudinit.util.kernel_version")
    def test_swap_creation_method_btrfs(
        self, m_kernel_version, m_get_mount_info
    ):
        m_kernel_version.return_value = (4, 20)
        m_get_mount_info.return_value = ["", "btrfs"]

        cc_mounts.handle("", self.cc, self.mock_cloud, [])
        self.m_subp.assert_has_calls(
            [
                mock.call(["truncate", "-s", "0", self.swap_path]),
                mock.call(["chattr", "+C", self.swap_path]),
                mock.call(
                    ["fallocate", "-l", "0M", self.swap_path],
                    capture=True,
                ),
                mock.call(["mkswap", self.swap_path]),
                mock.call(["swapon", "-a"]),
            ]
        )

    @mock.patch("cloudinit.util.get_mount_info")
    @mock.patch("cloudinit.util.kernel_version")
    def test_swap_creation_method_ext4(
        self, m_kernel_version, m_get_mount_info
    ):
        m_kernel_version.return_value = (5, 14)
        m_get_mount_info.return_value = ["", "ext4"]

        cc_mounts.handle("", self.cc, self.mock_cloud, [])
        self.m_subp.assert_has_calls(
            [
                mock.call(
                    ["fallocate", "-l", "0M", self.swap_path], capture=True
                ),
                mock.call(["mkswap", self.swap_path]),
                mock.call(["swapon", "-a"]),
            ]
        )


class TestFstabHandling:
    swap_path = "/dev/sdb1"

    @pytest.fixture(autouse=True)
    def setup(self, mocker, fake_filesystem: str):
        self.new_root = fake_filesystem

        self.fstab_path = os.path.join(self.new_root, "etc/fstab")
        self._makedirs("/etc")

        self.m_fstab = mocker.patch(f"{M_PATH}FSTAB_PATH", self.fstab_path)
        self.m_subp = mocker.patch(f"{M_PATH}subp.subp")
        self.m_mounts = mocker.patch(
            f"{M_PATH}util.mounts",
            return_value={
                "/dev/sda1": {
                    "fstype": "ext4",
                    "mountpoint": "/",
                    "opts": "rw,relatime,discard",
                }
            },
        )

        self.m_is_block_device = mocker.patch(
            f"{M_PATH}_is_block_device", return_value=True
        )

        self.mock_cloud = mock.Mock()
        self.mock_log = mock.Mock()
        self.mock_cloud.device_name_to_device = self.device_name_to_device

    def _makedirs(self, directory):
        directory = os.path.join(self.new_root, directory.lstrip("/"))
        if not os.path.exists(directory):
            os.makedirs(directory)

    def device_name_to_device(self, path):
        if path == "swap":
            return self.swap_path
        else:
            dev = None

        return dev

    def test_no_fstab(self):
        """Handle images which do not include an fstab."""
        assert not os.path.exists(cc_mounts.FSTAB_PATH)
        fstab_expected_content = (
            "%s\tnone\tswap\tsw,comment=cloudconfig\t0\t0\n"
            % (self.swap_path,)
        )
        cc_mounts.handle("", {}, self.mock_cloud, [])
        with open(cc_mounts.FSTAB_PATH, "r") as fd:
            fstab_new_content = fd.read()
            assert fstab_expected_content == fstab_new_content

    @pytest.mark.parametrize(
        "fstype, expected",
        [
            (
                "btrfs",
                [
                    mock.call(["truncate", "-s", "0", "/swap.img"]),
                    mock.call(["chattr", "+C", "/swap.img"]),
                    mock.call(
                        ["fallocate", "-l", "0M", "/swap.img"], capture=True
                    ),
                ],
            ),
            (
                "xfs",
                [
                    mock.call(
                        [
                            "dd",
                            "if=/dev/zero",
                            "of=/swap.img",
                            "bs=1M",
                            "count=0",
                        ],
                        capture=True,
                    )
                ],
            ),
            (
                "ext4",
                [
                    mock.call(
                        ["fallocate", "-l", "0M", "/swap.img"], capture=True
                    )
                ],
            ),
        ],
    )
    def test_swap_creation_command(self, fstype, expected, mocker):
        """Ensure that the swap file is correctly created.

        Different filesystems require different methods.
        """
        mocker.patch(
            "cloudinit.util.get_mount_info", return_value=["", fstype]
        )
        mocker.patch("cloudinit.util.kernel_version", return_value=(4, 17))

        fstab = "/swap.img swap swap defaults 0 0\n"

        with open(cc_mounts.FSTAB_PATH, "w") as fd:
            fd.write(fstab)
        cc = {
            "swap": {"filename": "/swap.img", "size": "512", "maxsize": "512"}
        }
        cc_mounts.handle("", cc, self.mock_cloud, [])
        assert self.m_subp.call_args_list == expected + [
            mock.call(["mkswap", "/swap.img"]),
            mock.call(["swapon", "-a"]),
            mock.call(["mount", "-a"]),
            mock.call(["systemctl", "daemon-reload"]),
        ]

    def test_fstab_no_swap_device(self):
        """Ensure that cloud-init adds a discovered swap partition
        to /etc/fstab."""

        fstab_original_content = ""
        fstab_expected_content = (
            "%s\tnone\tswap\tsw,comment=cloudconfig\t0\t0\n"
            % (self.swap_path,)
        )

        with open(cc_mounts.FSTAB_PATH, "w") as fd:
            fd.write(fstab_original_content)

        cc_mounts.handle("", {}, self.mock_cloud, [])

        with open(cc_mounts.FSTAB_PATH, "r") as fd:
            fstab_new_content = fd.read()
            assert fstab_expected_content == fstab_new_content

    def test_fstab_same_swap_device_already_configured(self):
        """Ensure that cloud-init will not add a swap device if the same
        device already exists in /etc/fstab."""

        fstab_original_content = "%s swap swap defaults 0 0\n" % (
            self.swap_path,
        )
        fstab_expected_content = fstab_original_content

        with open(cc_mounts.FSTAB_PATH, "w") as fd:
            fd.write(fstab_original_content)

        cc_mounts.handle("", {}, self.mock_cloud, [])

        with open(cc_mounts.FSTAB_PATH, "r") as fd:
            fstab_new_content = fd.read()
            assert fstab_expected_content == fstab_new_content

    def test_fstab_alternate_swap_device_already_configured(self):
        """Ensure that cloud-init will add a discovered swap device to
        /etc/fstab even when there exists a swap definition on another
        device."""

        fstab_original_content = "/dev/sdc1 swap swap defaults 0 0\n"
        fstab_expected_content = (
            fstab_original_content
            + "%s\tnone\tswap\tsw,comment=cloudconfig\t0\t0\n"
            % (self.swap_path,)
        )

        with open(cc_mounts.FSTAB_PATH, "w") as fd:
            fd.write(fstab_original_content)

        cc_mounts.handle("", {}, self.mock_cloud, [])

        with open(cc_mounts.FSTAB_PATH, "r") as fd:
            fstab_new_content = fd.read()
            assert fstab_expected_content == fstab_new_content

    def test_no_change_fstab_sets_needs_mount_all(self):
        """verify unchanged fstab entries are mounted if not call mount -a"""
        fstab_original_content = textwrap.dedent(
            f"""
            LABEL=cloudimg-rootfs / ext4 defaults 0 0
            LABEL=UEFI /boot/efi vfat defaults 0 0
            /dev/vdb	/mnt	auto	defaults,noexec,comment=cloudconfig	0	2
            {self.swap_path}	none	swap	sw,comment=cloudconfig	0	0
            """  # noqa: E501
        ).strip()
        cc = {"mounts": [["/dev/vdb", "/mnt", "auto", "defaults,noexec"]]}
        with open(cc_mounts.FSTAB_PATH, "w") as fd:
            fd.write(fstab_original_content)
        cc_mounts.handle("", cc, self.mock_cloud, [])
        with open(cc_mounts.FSTAB_PATH, "r") as fd:
            fstab_new_content = fd.read()
            assert fstab_original_content == fstab_new_content.strip()
        self.m_subp.assert_has_calls(
            [
                mock.call(["mount", "-a"]),
                mock.call(["systemctl", "daemon-reload"]),
            ]
        )

    def test_fstab_mounts_combinations(self):
        """Verify various combinations of mount entries in /etc/fstab."""
        # First and third lines show that even with errors we keep fstab lines
        # unedited unless they contain the cloudconfig comment.
        # 2nd line shows we remove a line with a cloudconfig comment that
        # can be added back in with the mounts config.
        # 4th line shows we remove a line with a cloudconfig comment
        # indiscriminately.
        fstab_original_content = (
            "LABEL=keepme	none	ext4	defaults	0	0\n"
            "/dev/sda1	/a	auto	defaults,comment=cloudconfig	0	2\n"
            "LABEL=UEFI\n"
            "\n"
            "/dev/sda2	/b	auto	defaults,comment=cloudconfig	0	2\n"
        )
        with open(cc_mounts.FSTAB_PATH, "w") as fd:
            fd.write(fstab_original_content)
        cfg = {
            "mounts": [
                # Line that will be overridden due to later None value
                ["/dev/sda3", "dontcare", "auto", "defaults", "0", "0"],
                # Add the one missing default field to the end
                ["/dev/sda4", "/mnt2", "auto", "nofail", "1"],
                # Remove all "/dev/sda3"'s here and earlier
                ["/dev/sda3", None],
                # As long as we have two fields we get the rest of the defaults
                ["/dev/sda5", "/mnt3"],
                # Takes the place of the line that was removed from fstab
                # with the cloudconfig comment
                ["/dev/sda1", "/mnt", "xfs", "auto", None, "2"],
                # The line that survies after previous Nones
                ["/dev/sda3", "/mnt4", "btrfs"],
            ]
        }
        cc_mounts.handle("", cfg, self.mock_cloud, [])
        with open(cc_mounts.FSTAB_PATH, "r") as fd:
            fstab_new_content = fd.read()

        assert (
            fstab_new_content.strip()
            == textwrap.dedent(
                """
            LABEL=keepme	none	ext4	defaults	0	0
            LABEL=UEFI
            /dev/sda4	/mnt2	auto	nofail,comment=cloudconfig	1	2
            /dev/sda5	/mnt3	auto	defaults,nofail,x-systemd.after=cloud-init-network.service,_netdev,comment=cloudconfig	0	2
            /dev/sda1	/mnt	xfs	auto,comment=cloudconfig	0	2
            /dev/sda3	/mnt4	btrfs	defaults,nofail,x-systemd.after=cloud-init-network.service,_netdev,comment=cloudconfig	0	2
            /dev/sdb1	none	swap	sw,comment=cloudconfig	0	0
            """  # noqa: E501
            ).strip()
        )


class TestCreateSwapfile:
    @pytest.mark.parametrize("fstype", ("xfs", "btrfs", "ext4", "other"))
    @mock.patch(M_PATH + "util.get_mount_info")
    @mock.patch(M_PATH + "subp.subp")
    @mock.patch(M_PATH + "util.kernel_version")
    def test_happy_path(
        self, m_kernel_version, m_subp, m_get_mount_info, fstype, tmpdir
    ):
        swap_file = tmpdir.join("swap-file")
        fname = str(swap_file)

        # Some of the calls to subp.subp should create the swap file; this
        # roughly approximates that
        m_subp.side_effect = lambda *args, **kwargs: swap_file.write("")
        m_kernel_version.return_value = (4, 31)

        m_get_mount_info.return_value = (mock.ANY, fstype)

        create_swapfile(fname, "")
        assert mock.call(["mkswap", fname]) in m_subp.call_args_list

    @mock.patch(M_PATH + "util.get_mount_info")
    @mock.patch(M_PATH + "subp.subp")
    def test_fallback_from_fallocate_to_dd(
        self, m_subp, m_get_mount_info, caplog, tmpdir
    ):
        swap_file = tmpdir.join("swap-file")
        fname = str(swap_file)

        def subp_side_effect(cmd, *args, **kwargs):
            # Mock fallocate failing, to initiate fallback
            if cmd[0] == "fallocate":
                raise ProcessExecutionError()

        m_subp.side_effect = subp_side_effect
        # Use ext4 so both fallocate and dd are valid swap creation methods
        m_get_mount_info.return_value = (mock.ANY, "ext4")

        create_swapfile(fname, "")

        cmds = [args[0][0] for args, _kwargs in m_subp.call_args_list]
        assert "fallocate" in cmds, "fallocate was not called"
        assert "dd" in cmds, "fallocate failure did not fallback to dd"

        assert cmds.index("dd") > cmds.index(
            "fallocate"
        ), "dd ran before fallocate"

        assert mock.call(["mkswap", fname]) in m_subp.call_args_list

        msg = "fallocate swap creation failed, will attempt with dd"
        assert msg in caplog.text

    # See https://help.ubuntu.com/community/SwapFaq
    @pytest.mark.parametrize(
        "memsize,expected",
        [
            (256 * MB, 256 * MB),
            (512 * MB, 512 * MB),
            (1 * GB, 1 * GB),
            (2 * GB, 2 * GB),
            (4 * GB, 4 * GB),
            (8 * GB, 4 * GB),
            (16 * GB, 4 * GB),
            (32 * GB, 6 * GB),
            (64 * GB, 8 * GB),
            (128 * GB, 11 * GB),
            (256 * GB, 16 * GB),
            (512 * GB, 23 * GB),
        ],
    )
    def test_suggested_swapsize(self, memsize, expected, mocker):
        mock_stat = namedtuple("mock_stat", "f_frsize f_bfree")
        mocker.patch(
            "os.statvfs",
            # Don't care about available disk space for the purposes of this
            # test
            return_value=mock_stat(math.inf, math.inf),
        )
        size = suggested_swapsize(memsize, math.inf, "dontcare")
        assert expected == approx(size)


class TestMountsSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        [
            # We expect to see one mount if provided in user-data.
            (
                {"mounts": []},
                re.escape("mounts: [] ") + test_helpers.SCHEMA_EMPTY_ERROR,
            ),
            # Disallow less than 1 item per mount entry
            (
                {"mounts": [[]]},
                re.escape("mounts.0: [] ") + test_helpers.SCHEMA_EMPTY_ERROR,
            ),
            # Disallow more than 6 items per mount entry
            ({"mounts": [["1"] * 7]}, "mounts.0:.* is too long"),
            # Disallow mount_default_fields will anything other than 6 items
            (
                {"mount_default_fields": ["1"] * 5},
                "mount_default_fields:.* is too short",
            ),
            (
                {"mount_default_fields": ["1"] * 7},
                "mount_default_fields:.* is too long",
            ),
            (
                {"swap": {"invalidprop": True}},
                re.escape(
                    "Additional properties are not allowed ('invalidprop'"
                ),
            ),
            # Swap size/maxsize positive test cases
            ({"swap": {"size": ".5T", "maxsize": ".5T"}}, None),
            ({"swap": {"size": "1G", "maxsize": "1G"}}, None),
            ({"swap": {"size": "200K", "maxsize": "200K"}}, None),
            ({"swap": {"size": "10485760B", "maxsize": "10485760B"}}, None),
            # Swap size/maxsize negative test cases
            ({"swap": {"size": "1.5MB"}}, "swap.size:"),
            (
                {"swap": {"maxsize": "1.5MT"}},
                re.escape("swap.maxsize: '1.5MT' does not match '^([0-9]+)?"),
            ),
            (
                {"swap": {"maxsize": "..5T"}},
                re.escape("swap.maxsize: '..5T' does not match '^([0-9]+)?"),
            ),
            (
                {"swap": {"size": "K"}},
                "swap.size: 'K' is not of type 'integer'",
            ),
        ],
    )
    @test_helpers.skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        if error_msg is None:
            validate_cloudconfig_schema(config, get_schema(), strict=True)
        else:
            with pytest.raises(SchemaValidationError, match=error_msg):
                validate_cloudconfig_schema(config, get_schema(), strict=True)
