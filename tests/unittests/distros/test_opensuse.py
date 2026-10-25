# This file is part of cloud-init. See LICENSE file for license information.

from unittest import mock

from cloudinit import distros


@mock.patch("cloudinit.distros.opensuse.subp.subp")
class TestPackageCommands:
    distro = distros.fetch("opensuse")("opensuse", {}, None)

    @mock.patch(
        "cloudinit.distros.opensuse.util.get_mount_info",
        return_value=("/dev/sda1", "xfs", "/"),
    )
    @mock.patch(
        "cloudinit.distros.opensuse.util.load_text_file",
        return_value="foo\n/dev/sda1 / xfs rw,bar\n",
    )
    @mock.patch(
        "cloudinit.distros.opensuse.os.path.exists", return_value=False
    )
    def test_upgrade_not_btrfs(self, m_tu_path, m_mounts, m_minfo, m_subp):
        # Reset state
        self.distro.update_method = None

        self.distro.package_command("upgrade")
        expected_cmd = ["zypper", "--non-interactive", "update"]
        m_subp.assert_called_with(expected_cmd, capture=False)

    @mock.patch(
        "cloudinit.distros.opensuse.util.get_mount_info",
        return_value=("/dev/sda1", "xfs", "/"),
    )
    @mock.patch(
        "cloudinit.distros.opensuse.util.load_text_file",
        return_value="foo\n/dev/sda1 / xfs rw,bar\n",
    )
    @mock.patch(
        "cloudinit.distros.opensuse.os.path.exists", return_value=False
    )
    def test_upgrade_not_btrfs_pkg(self, m_tu_path, m_mounts, m_minfo, m_subp):
        # Reset state
        self.distro.update_method = None

        self.distro.package_command("upgrade", None, ["python36", "gzip"])
        expected_cmd = [
            "zypper",
            "--non-interactive",
            "update",
            "python36",
            "gzip",
        ]
        m_subp.assert_called_with(expected_cmd, capture=False)

    @mock.patch(
        "cloudinit.distros.opensuse.util.get_mount_info",
        return_value=("/dev/sda1", "xfs", "/"),
    )
    @mock.patch(
        "cloudinit.distros.opensuse.util.load_text_file",
        return_value="foo\n/dev/sda1 / xfs rw,bar\n",
    )
    @mock.patch(
        "cloudinit.distros.opensuse.os.path.exists", return_value=False
    )
    def test_update_not_btrfs(self, m_tu_path, m_mounts, m_minfo, m_subp):
        # Reset state
        self.distro.update_method = None

        self.distro.package_command("update")
        expected_cmd = ["zypper", "--non-interactive", "update"]
        m_subp.assert_called_with(expected_cmd, capture=False)

    @mock.patch(
        "cloudinit.distros.opensuse.util.get_mount_info",
        return_value=("/dev/sda1", "xfs", "/"),
    )
    @mock.patch(
        "cloudinit.distros.opensuse.util.load_text_file",
        return_value="foo\n/dev/sda1 / xfs rw,bar\n",
    )
    @mock.patch(
        "cloudinit.distros.opensuse.os.path.exists", return_value=False
    )
    def test_update_not_btrfs_pkg(self, m_tu_path, m_mounts, m_minfo, m_subp):
        # Reset state
        self.distro.update_method = None

        self.distro.package_command("update", None, ["python36", "gzip"])
        expected_cmd = [
            "zypper",
            "--non-interactive",
            "update",
            "python36",
            "gzip",
        ]
        m_subp.assert_called_with(expected_cmd, capture=False)

    @mock.patch(
        "cloudinit.distros.opensuse.util.get_mount_info",
        return_value=("/dev/sda1", "xfs", "/"),
    )
    @mock.patch(
        "cloudinit.distros.opensuse.util.load_text_file",
        return_value="foo\n/dev/sda1 / xfs rw,bar\n",
    )
    @mock.patch(
        "cloudinit.distros.opensuse.os.path.exists", return_value=False
    )
    def test_install_not_btrfs_pkg(self, m_tu_path, m_mounts, m_minfo, m_subp):
        # Reset state
        self.distro.update_method = None

        self.distro.install_packages(["python36", "gzip"])
        expected_cmd = [
            "zypper",
            "--non-interactive",
            "install",
            "--auto-agree-with-licenses",
            "python36",
            "gzip",
        ]
        m_subp.assert_called_with(expected_cmd, capture=False)

    @mock.patch(
        "cloudinit.distros.opensuse.util.get_mount_info",
        return_value=("/dev/sda1", "btrfs", "/"),
    )
    @mock.patch(
        "cloudinit.distros.opensuse.util.load_text_file",
        return_value="foo\n/dev/sda1 / btrfs rw,bar\n",
    )
    @mock.patch("cloudinit.distros.opensuse.os.path.exists", return_value=True)
    def test_upgrade_btrfs(self, m_tu_path, m_mounts, m_minfo, m_subp):
        # Reset state
        self.distro.update_method = None

        self.distro.package_command("upgrade")
        expected_cmd = [
            "transactional-update",
            "--non-interactive",
            "--drop-if-no-change",
            "up",
        ]
        m_subp.assert_called_with(expected_cmd, capture=False)

    @mock.patch(
        "cloudinit.distros.opensuse.util.get_mount_info",
        return_value=("/dev/sda1", "btrfs", "/"),
    )
    @mock.patch(
        "cloudinit.distros.opensuse.util.load_text_file",
        return_value="foo\n/dev/sda1 / btrfs rw,bar\n",
    )
    @mock.patch("cloudinit.distros.opensuse.os.path.exists", return_value=True)
    def test_upgrade_btrfs_pkg(self, m_tu_path, m_mounts, m_minfo, m_subp):
        # Reset state
        self.distro.update_method = None

        self.distro.package_command("upgrade", None, ["python36", "gzip"])
        expected_cmd = [
            "transactional-update",
            "--non-interactive",
            "--drop-if-no-change",
            "pkg",
            "update",
            "python36",
            "gzip",
        ]
        m_subp.assert_called_with(expected_cmd, capture=False)

    @mock.patch(
        "cloudinit.distros.opensuse.util.get_mount_info",
        return_value=("/dev/sda1", "btrfs", "/"),
    )
    @mock.patch(
        "cloudinit.distros.opensuse.util.load_text_file",
        return_value="foo\n/dev/sda1 / btrf rw,bar\n",
    )
    @mock.patch("cloudinit.distros.opensuse.os.path.exists", return_value=True)
    def test_update_btrfs(self, m_tu_path, m_mounts, m_minfo, m_subp):
        # Reset state
        self.distro.update_method = None

        self.distro.package_command("update")
        expected_cmd = [
            "transactional-update",
            "--non-interactive",
            "--drop-if-no-change",
            "up",
        ]
        m_subp.assert_called_with(expected_cmd, capture=False)

    @mock.patch(
        "cloudinit.distros.opensuse.util.get_mount_info",
        return_value=("/dev/sda1", "btrfs", "/"),
    )
    @mock.patch(
        "cloudinit.distros.opensuse.util.load_text_file",
        return_value="foo\n/dev/sda1 / btrfs rw,bar\n",
    )
    @mock.patch("cloudinit.distros.opensuse.os.path.exists", return_value=True)
    def test_update_btrfs_pkg(self, m_tu_path, m_mounts, m_minfo, m_subp):
        # Reset state
        self.distro.update_method = None

        self.distro.package_command("update", None, ["python36", "gzip"])
        expected_cmd = [
            "transactional-update",
            "--non-interactive",
            "--drop-if-no-change",
            "pkg",
            "update",
            "python36",
            "gzip",
        ]
        m_subp.assert_called_with(expected_cmd, capture=False)

    @mock.patch(
        "cloudinit.distros.opensuse.util.get_mount_info",
        return_value=("/dev/sda1", "btrfs", "/"),
    )
    @mock.patch(
        "cloudinit.distros.opensuse.util.load_text_file",
        return_value="foo\n/dev/sda1 / btrfs rw,bar\n",
    )
    @mock.patch("cloudinit.distros.opensuse.os.path.exists", return_value=True)
    def test_install_btrfs_pkg(self, m_tu_path, m_mounts, m_minfo, m_subp):
        # Reset state
        self.distro.update_method = None

        self.distro.install_packages(["python36", "gzip"])
        expected_cmd = [
            "transactional-update",
            "--non-interactive",
            "--drop-if-no-change",
            "pkg",
            "install",
            "--auto-agree-with-licenses",
            "python36",
            "gzip",
        ]
        m_subp.assert_called_with(expected_cmd, capture=False)

    @mock.patch(
        "cloudinit.distros.opensuse.util.get_mount_info",
        return_value=("/dev/sda1", "btrfs", "/"),
    )
    @mock.patch(
        "cloudinit.distros.opensuse.util.load_text_file",
        return_value="foo\n/dev/sda1 / btrfs ro,bar\n",
    )
    @mock.patch(
        "cloudinit.distros.opensuse.os.path.exists", return_value=False
    )
    def test_upgrade_no_transact_up_ro_root(
        self, m_tu_path, m_mounts, m_minfo, m_subp
    ):
        # Reset state
        self.distro.update_method = None

        result = self.distro.package_command("upgrade")
        assert self.distro.read_only_root
        assert result is None
        assert not m_subp.called

    @mock.patch(
        "cloudinit.distros.opensuse.util.get_mount_info",
        return_value=("/dev/sda1", "btrfs", "/"),
    )
    @mock.patch(
        "cloudinit.distros.opensuse.util.load_text_file",
        return_value="foo\n/dev/sda1 / btrfs rw,bar\n",
    )
    @mock.patch(
        "cloudinit.distros.opensuse.os.path.exists", return_value=False
    )
    def test_upgrade_no_transact_up_rw_root_btrfs(
        self, m_tu_path, m_mounts, m_minfo, m_subp
    ):
        # Reset state
        self.distro.update_method = None

        self.distro.package_command("upgrade")
        assert self.distro.update_method == "zypper"
        assert self.distro.read_only_root is False
        expected_cmd = ["zypper", "--non-interactive", "update"]
        m_subp.assert_called_with(expected_cmd, capture=False)

    @mock.patch(
        "cloudinit.distros.opensuse.util.get_mount_info",
        return_value=("/dev/sda1", "xfs", "/"),
    )
    @mock.patch(
        "cloudinit.distros.opensuse.util.load_text_file",
        return_value="foo\n/dev/sda1 / xfs ro,bar\n",
    )
    @mock.patch("cloudinit.distros.opensuse.os.path.exists", return_value=True)
    def test_upgrade_transact_up_ro_root(
        self, m_tu_path, m_mounts, m_minfo, m_subp
    ):
        # Reset state
        self.distro.update_method = None

        result = self.distro.package_command("upgrade")
        assert self.distro.update_method == "zypper"
        assert self.distro.read_only_root
        assert result is None
        assert not m_subp.called

    @mock.patch(
        "cloudinit.distros.opensuse.util.get_mount_info",
        return_value=("/dev/sda1", "btrfs", "/"),
    )
    @mock.patch(
        "cloudinit.distros.opensuse.util.load_text_file",
        return_value="foo\n/dev/sda1 / btrfs ro,bar\n",
    )
    @mock.patch("cloudinit.distros.opensuse.os.path.exists", return_value=True)
    def test_refresh_transact_up_ro_root_btrfs(
        self, m_tu_path, m_mounts, m_minfo, m_subp
    ):
        # Reset state
        self.distro.update_method = None

        self.distro.package_command("refresh")
        assert self.distro.update_method == "transactional"
        assert self.distro.read_only_root
        expected_cmd = ["zypper", "--non-interactive", "refresh"]
        m_subp.assert_called_with(expected_cmd, capture=False)


@mock.patch("cloudinit.distros.opensuse.subp.subp")
class TestReadHostname:
    distro = distros.fetch("opensuse")("opensuse", {}, None)

    def test_strips_trailing_newline_from_hostname_command(self, m_subp):
        m_subp.return_value = ("myhost\n", "")
        with mock.patch.object(self.distro, "uses_systemd", return_value=True):
            assert self.distro._read_hostname("/etc/hostname") == "myhost"

    def test_empty_hostname_command_output_returns_default(self, m_subp):
        m_subp.return_value = ("\n", "")
        with mock.patch.object(self.distro, "uses_systemd", return_value=True):
            assert (
                self.distro._read_hostname("/etc/hostname", default="dflt")
                == "dflt"
            )

    def test_update_hostname_follows_a_changed_hostname(
        self, m_subp, tmp_path, caplog
    ):
        """The unstripped command output never equaled previous-hostname,
        so update_hostname always took the hostname for user maintained."""
        prev_fn = tmp_path / "previous-hostname"
        prev_fn.write_text("oldname")
        m_subp.return_value = ("oldname\n", "")
        with mock.patch.object(
            self.distro, "uses_systemd", return_value=True
        ), mock.patch.object(self.distro, "_write_hostname") as m_write:
            self.distro.update_hostname("newname", "newname", str(prev_fn))
        assert "assuming user maintained hostname" not in caplog.text
        m_write.assert_any_call("newname", "/etc/hostname")
