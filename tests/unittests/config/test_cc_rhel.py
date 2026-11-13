# This file is part of cloud-init. See LICENSE file for license information.
import os
from typing import Any, Dict
from unittest import mock

import pytest

from cloudinit import subp
from cloudinit.config import cc_rhel
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import (
    SCHEMA_EMPTY_ERROR,
    skipUnlessJsonSchema,
)
from tests.unittests.util import get_cloud

UNEXPECTED_PROP = r"Additional properties are not allowed"
r" \('{0}' was unexpected\)"


class TestRHELModule:
    """Test cases for the RHEL configuration module."""

    @mock.patch("cloudinit.util.fips_enabled")
    @mock.patch("os.path.exists")
    def test_fips_mode_enabled_proc_true(self, mock_path, mock_fips_enabled):
        """Test _fips_mode_enabled returns True when fips=1 in cmdline."""
        mock_fips_enabled.return_value = True
        mock_path.return_value = True
        assert cc_rhel._fips_mode_enabled()
        mock_path.assert_called_once_with(cc_rhel.FIPS_MODE_FLAG)
        mock_fips_enabled.assert_called_once()

    @mock.patch("cloudinit.util.get_cmdline")
    @mock.patch("os.path.exists")
    def test_fips_mode_enabled_true(self, mock_path, mock_get_cmdline):
        """Test _fips_mode_enabled returns True when fips=1 in cmdline."""
        mock_get_cmdline.return_value = "ro quiet fips=1 rhgb"
        mock_path.return_value = False
        assert cc_rhel._fips_mode_enabled()
        mock_path.assert_called_once_with(cc_rhel.FIPS_MODE_FLAG)

    @mock.patch("cloudinit.util.get_cmdline")
    @mock.patch("os.path.exists")
    def test_fips_mode_enabled_false_no_fips(
        self, mock_path, mock_get_cmdline
    ):
        """Test _fips_mode_enabled returns False when no fips in cmdline."""
        mock_get_cmdline.return_value = "ro quiet rhgb"
        mock_path.return_value = False
        assert not cc_rhel._fips_mode_enabled()

    @mock.patch("cloudinit.util.get_cmdline")
    @mock.patch("os.path.exists")
    def test_fips_mode_enabled_false_fips_zero(
        self, mock_path, mock_get_cmdline
    ):
        """Test _fips_mode_enabled returns False when fips=0 in cmdline."""
        mock_path.return_value = False
        mock_get_cmdline.return_value = "ro quiet fips=0 rhgb"
        assert not cc_rhel._fips_mode_enabled()

    def test_handle_no_rhel_config(self):
        """Test handle function when no RHEL configuration is provided."""
        cloud = get_cloud("rhel")
        with mock.patch(
            "cloudinit.config.cc_rhel._configure_fips"
        ) as mock_fips:
            cc_rhel.handle("cc_rhel", {}, cloud, [])
            mock_fips.assert_not_called()

    def test_handle_with_rhel_config(self):
        """Test handle function when RHEL configuration is provided."""
        rhel_cfg = {"fips_mode": True}
        cfg = {"rhel": rhel_cfg}
        cloud = get_cloud("rhel")
        with mock.patch(
            "cloudinit.config.cc_rhel._configure_fips"
        ) as mock_fips:
            cc_rhel.handle("cc_rhel", cfg, cloud, [])
            mock_fips.assert_called_once_with(rhel_cfg, cloud)

    def test_configure_fips_no_fips_mode_config(self):
        """Test _configure_fips when fips_mode is not in config."""
        config: Dict[str, Any] = {}
        cloud = get_cloud("rhel")
        with mock.patch("cloudinit.config.cc_rhel.LOG") as mock_log:
            cc_rhel._configure_fips(config, cloud)
            mock_log.warning.assert_called_once_with(
                "FIPS config option not provided!"
            )

    def test_configure_fips_disabled(self):
        """Test _configure_fips when fips_mode is disabled."""
        config = {"fips_mode": False}
        cloud = get_cloud("rhel")
        with mock.patch("cloudinit.config.cc_rhel.LOG") as mock_log:
            cc_rhel._configure_fips(config, cloud)
            mock_log.debug.assert_called_once_with("Fips mode is set to False")

    @mock.patch("cloudinit.config.cc_rhel._fips_mode_enabled")
    def test_configure_fips_already_enabled(self, mock_fips_enabled):
        """Test _configure_fips when FIPS mode is already enabled."""
        config = {"fips_mode": True}
        mock_fips_enabled.return_value = True
        cloud = get_cloud("rhel")
        with mock.patch("cloudinit.config.cc_rhel.subp") as mock_subp:
            cc_rhel._configure_fips(config, cloud)
            mock_subp.subp.assert_not_called()

    @mock.patch("cloudinit.config.cc_rhel._fips_mode_enabled")
    @mock.patch("cloudinit.config.cc_rhel.is_efi_boot")
    @mock.patch("cloudinit.config.cc_rhel.uses_grub_boot")
    def test_configure_fips_efi_nogrub(
        self, mock_grub_boot, mock_efi_boot, mock_fips_enabled
    ):
        """Test _configure_fips when FIPS helper does not exist."""
        config = {"fips_mode": True}
        mock_fips_enabled.return_value = False
        mock_efi_boot.return_value = True
        mock_grub_boot.return_value = False
        cloud = get_cloud("rhel")

        with mock.patch("cloudinit.config.cc_rhel.LOG") as mock_log:
            cc_rhel._configure_fips(config, cloud)
            mock_log.info.assert_called_once_with(
                "Fips mode cannot be enabled with"
                " EFI direct kernel boot for now"
            )

    @mock.patch("cloudinit.config.cc_rhel._fips_mode_enabled")
    @mock.patch("os.path.exists")
    def test_configure_fips_helper_missing(
        self, mock_exists, mock_fips_enabled
    ):
        """Test _configure_fips when FIPS helper does not exist."""
        config = {"fips_mode": True}
        mock_fips_enabled.return_value = False
        mock_exists.return_value = False
        cloud = get_cloud("rhel")

        with mock.patch("cloudinit.config.cc_rhel.LOG") as mock_log:
            cc_rhel._configure_fips(config, cloud)
            expected_path = os.path.join(
                cc_rhel.FIPS_HELPER_PATH, cc_rhel.FIPS_HELPER
            )
            mock_log.debug.assert_called_once_with(
                "fips mode enabler %s does not exist", expected_path
            )

    @mock.patch("cloudinit.config.cc_rhel._fips_mode_enabled")
    @mock.patch("os.path.exists")
    @mock.patch("cloudinit.subp.subp")
    @mock.patch("cloudinit.util.fire_reboot")
    @mock.patch("cloudinit.util.del_file")
    @mock.patch("cloudinit.config.cc_rhel.is_efi_boot")
    @mock.patch("cloudinit.config.cc_rhel.update_kernel_commandline_grubby")
    def test_configure_fips_success(
        self,
        mock_kernel_cmdline,
        mock_efi_boot,
        mock_del_file,
        mock_reboot,
        mock_subp,
        mock_exists,
        mock_fips_enabled,
    ):
        """Test successful FIPS configuration."""
        config = {"fips_mode": True}
        cloud = get_cloud("rhel")
        mock_fips_enabled.return_value = False
        mock_efi_boot.return_value = False
        mock_exists.side_effect = lambda path: (
            path == os.path.join(cc_rhel.FIPS_HELPER_PATH, cc_rhel.FIPS_HELPER)
            or path
            in ["/etc/ssh/ssh_host_ecdsa_key", "/etc/ssh/ssh_host_ed25519_key"]
        )

        with mock.patch(
            "cloudinit.util.FIPS_UNSUPPORTED_KEY_NAMES", ["ecdsa", "ed25519"]
        ):
            with mock.patch(
                "cloudinit.util.KEY_FILE_TPL", "/etc/ssh/ssh_host_%s_key"
            ):
                cc_rhel._configure_fips(config, cloud)

        # Check FIPS helper was called
        expected_path = os.path.join(
            cc_rhel.FIPS_HELPER_PATH, cc_rhel.FIPS_HELPER
        )
        mock_subp.assert_called_once_with([expected_path, "cloud-init"])

        # Check unsupported keys were deleted
        expected_del_calls = [
            mock.call("/etc/ssh/ssh_host_ecdsa_key"),
            mock.call("/etc/ssh/ssh_host_ed25519_key"),
        ]
        mock_del_file.assert_has_calls(expected_del_calls, any_order=True)

        # Check reboot was initiated
        mock_reboot.assert_called_once()

    @mock.patch("cloudinit.config.cc_rhel._fips_mode_enabled")
    @mock.patch("os.path.exists")
    @mock.patch("cloudinit.subp.subp")
    @mock.patch("cloudinit.util.fire_reboot")
    @mock.patch("cloudinit.util.del_file")
    @mock.patch("cloudinit.config.cc_rhel.is_efi_boot")
    @mock.patch("cloudinit.config.cc_rhel.update_kernel_commandline_grubby")
    @mock.patch("cloudinit.config.cc_rhel.uses_grub_boot")
    def test_configure_fips_success_efi_boot(
        self,
        mock_uses_grub,
        mock_kernel_cmdline,
        mock_efi_boot,
        mock_del_file,
        mock_reboot,
        mock_subp,
        mock_exists,
        mock_fips_enabled,
    ):
        """Test successful FIPS configuration."""
        config = {"fips_mode": True}
        cloud = get_cloud("rhel")
        mock_fips_enabled.return_value = False
        mock_efi_boot.return_value = True
        mock_uses_grub.return_value = True
        mock_exists.side_effect = lambda path: (
            path == os.path.join(cc_rhel.FIPS_HELPER_PATH, cc_rhel.FIPS_HELPER)
            or path
            in ["/etc/ssh/ssh_host_ecdsa_key", "/etc/ssh/ssh_host_ed25519_key"]
        )

        with mock.patch(
            "cloudinit.util.FIPS_UNSUPPORTED_KEY_NAMES", ["ecdsa", "ed25519"]
        ):
            with mock.patch(
                "cloudinit.util.KEY_FILE_TPL", "/etc/ssh/ssh_host_%s_key"
            ):
                cc_rhel._configure_fips(config, cloud)

        # Check FIPS helper was called
        expected_path = os.path.join(
            cc_rhel.FIPS_HELPER_PATH, cc_rhel.FIPS_HELPER
        )
        mock_subp.assert_called_once_with([expected_path, "cloud-init"])

        # Check unsupported keys were deleted
        expected_del_calls = [
            mock.call("/etc/ssh/ssh_host_ecdsa_key"),
            mock.call("/etc/ssh/ssh_host_ed25519_key"),
        ]
        mock_del_file.assert_has_calls(expected_del_calls, any_order=True)

        # Check reboot was initiated
        mock_reboot.assert_called_once()

    @mock.patch("cloudinit.config.cc_rhel._fips_mode_enabled")
    @mock.patch("os.path.exists")
    @mock.patch("cloudinit.subp.subp")
    @mock.patch("cloudinit.config.cc_rhel.is_efi_boot")
    def test_configure_fips_helper_failure(
        self, mock_efi_boot, mock_subp, mock_exists, mock_fips_enabled
    ):
        """Test _configure_fips when FIPS helper fails."""
        config = {"fips_mode": True}
        mock_fips_enabled.return_value = False
        mock_exists.return_value = True
        mock_efi_boot.return_value = False
        mock_subp.side_effect = subp.ProcessExecutionError(
            "Failed to enable FIPS", exit_code=1
        )
        cloud = get_cloud("rhel")

        with mock.patch("cloudinit.util.logexc") as mock_logexc:
            cc_rhel._configure_fips(config, cloud)
            mock_logexc.assert_called_once()

    @mock.patch("cloudinit.config.cc_rhel._fips_mode_enabled")
    @mock.patch("os.path.exists")
    @mock.patch("cloudinit.subp.subp")
    @mock.patch("cloudinit.util.fire_reboot")
    @mock.patch("cloudinit.util.del_file")
    @mock.patch("cloudinit.config.cc_rhel.is_efi_boot")
    @mock.patch("cloudinit.config.cc_rhel.update_kernel_commandline_grubby")
    def test_configure_fips_key_deletion_failure(
        self,
        mock_kernel_commandline,
        mock_efi_boot,
        mock_del_file,
        mock_reboot,
        mock_subp,
        mock_exists,
        mock_fips_enabled,
    ):
        """Test _configure_fips when key deletion fails."""
        config = {"fips_mode": True}
        cloud = get_cloud("rhel")
        mock_fips_enabled.return_value = False
        mock_efi_boot.return_value = False
        mock_exists.side_effect = lambda path: (
            path == os.path.join(cc_rhel.FIPS_HELPER_PATH, cc_rhel.FIPS_HELPER)
            or path == "/etc/ssh/ssh_host_ecdsa_key"
        )
        mock_del_file.side_effect = Exception("Permission denied")

        with mock.patch(
            "cloudinit.util.FIPS_UNSUPPORTED_KEY_NAMES", ["ecdsa"]
        ):
            with mock.patch(
                "cloudinit.util.KEY_FILE_TPL", "/etc/ssh/ssh_host_%s_key"
            ):
                with mock.patch("cloudinit.util.logexc") as mock_logexc:
                    cc_rhel._configure_fips(config, cloud)

        # Should still call reboot despite key deletion failure
        mock_reboot.assert_called_once()
        # Should log the exception
        mock_logexc.assert_called()

    @mock.patch("cloudinit.config.cc_rhel._fips_mode_enabled")
    @mock.patch("os.path.exists")
    @mock.patch("cloudinit.subp.subp")
    @mock.patch("cloudinit.util.fire_reboot")
    @mock.patch("cloudinit.config.cc_rhel.is_efi_boot")
    @mock.patch("cloudinit.config.cc_rhel.update_kernel_commandline_grubby")
    def test_configure_fips_no_unsupported_keys(
        self,
        mock_kernel,
        mock_efi_boot,
        mock_reboot,
        mock_subp,
        mock_exists,
        mock_fips_enabled,
    ):
        """Test _configure_fips when no unsupported keys exist."""
        config = {"fips_mode": True}
        cloud = get_cloud("rhel")
        mock_fips_enabled.return_value = False
        mock_efi_boot.return_value = False
        mock_exists.side_effect = lambda path: (
            path == os.path.join(cc_rhel.FIPS_HELPER_PATH, cc_rhel.FIPS_HELPER)
        )

        with mock.patch(
            "cloudinit.util.FIPS_UNSUPPORTED_KEY_NAMES", ["ecdsa", "ed25519"]
        ):
            with mock.patch(
                "cloudinit.util.KEY_FILE_TPL", "/etc/ssh/ssh_host_%s_key"
            ):
                with mock.patch("cloudinit.util.del_file") as mock_del_file:
                    cc_rhel._configure_fips(config, cloud)

        # No keys should be deleted since they don't exist
        mock_del_file.assert_not_called()
        mock_reboot.assert_called_once()

    def test_configure_fips_string_true_config(self):
        """Test _configure_fips with string 'true' configuration."""
        config = {"fips_mode": "true"}
        cloud = get_cloud("rhel")

        with mock.patch("cloudinit.util.get_cfg_option_bool") as mock_get_bool:
            mock_get_bool.return_value = True
            with mock.patch(
                "cloudinit.config.cc_rhel._fips_mode_enabled"
            ) as mock_enabled:
                mock_enabled.return_value = True
                cc_rhel._configure_fips(config, cloud)
                mock_get_bool.assert_called_once_with(
                    config, "fips_mode", False
                )

    def test_configure_fips_string_false_config(self):
        """Test _configure_fips with string 'false' configuration."""
        config = {"fips_mode": "false"}
        cloud = get_cloud("rhel")

        with mock.patch("cloudinit.util.get_cfg_option_bool") as mock_get_bool:
            mock_get_bool.return_value = False
            with mock.patch("cloudinit.config.cc_rhel.LOG") as mock_log:
                cc_rhel._configure_fips(config, cloud)
                mock_get_bool.assert_called_once_with(
                    config, "fips_mode", False
                )
                mock_log.debug.assert_called_once_with(
                    "Fips mode is set to False"
                )

    @mock.patch("cloudinit.config.cc_rhel.find_boot_uuid")
    @mock.patch("cloudinit.config.cc_rhel.find_boot")
    @mock.patch("cloudinit.subp.subp")
    def test_update_kernel_commandline_with_boot_uuid(
        self, mock_subp, mock_find_boot, mock_find_boot_uuid
    ):
        """Test update_kernel_commandline with boot UUID."""
        boot_uuid = "12345678-1234-1234-1234-123456789012"
        mock_find_boot.return_value = "/dev/sda1"
        mock_find_boot_uuid.return_value = boot_uuid
        mock_subp.return_value = (None, None)

        cc_rhel.update_kernel_commandline_grubby()

        # Verify grubby was called with correct arguments
        expected_args = '"fips=1 boot=UUID=%s"' % boot_uuid
        expected_call = [
            "grubby",
            "--update-kernel=ALL",
            "--args=%s" % expected_args,
        ]
        mock_subp.assert_called_once_with(expected_call)

    @mock.patch("cloudinit.config.cc_rhel.find_boot_uuid")
    @mock.patch("cloudinit.config.cc_rhel.find_boot")
    @mock.patch("cloudinit.subp.subp")
    def test_update_kernel_commandline_without_boot_uuid(
        self, mock_subp, mock_find_boot, mock_find_boot_uuid
    ):
        """Test update_kernel_commandline without boot UUID."""
        mock_find_boot.return_value = None
        mock_find_boot_uuid.return_value = None
        mock_subp.return_value = (None, None)

        cc_rhel.update_kernel_commandline_grubby()

        # Verify grubby was called without boot UUID
        expected_args = '"fips=1"'
        expected_call = [
            "grubby",
            "--update-kernel=ALL",
            "--args=%s" % expected_args,
        ]
        mock_subp.assert_called_once_with(expected_call)

    @mock.patch("cloudinit.config.cc_rhel.find_boot_uuid")
    @mock.patch("cloudinit.config.cc_rhel.find_boot")
    @mock.patch("cloudinit.subp.subp")
    def test_update_kernel_commandline_subp_failure(
        self, mock_subp, mock_find_boot, mock_find_boot_uuid
    ):
        """Test update_kernel_commandline when grubby fails."""
        mock_find_boot.return_value = "/dev/sda1"
        mock_find_boot_uuid.return_value = (
            "12345678-1234-1234-1234-123456789012"
        )
        mock_subp.side_effect = subp.ProcessExecutionError(
            "grubby failed", exit_code=1
        )

        with pytest.raises(subp.ProcessExecutionError):
            cc_rhel.update_kernel_commandline_grubby()

    @mock.patch("cloudinit.config.cc_rhel.find_boot_uuid")
    @mock.patch("cloudinit.config.cc_rhel.find_boot")
    @mock.patch("cloudinit.subp.subp")
    def test_update_kernel_commandline_grubby_command_structure(
        self, mock_subp, mock_find_boot, mock_find_boot_uuid
    ):
        """Test that grubby command has correct structure."""
        boot_uuid = "abc123def456"
        mock_find_boot.return_value = "/dev/sda1"
        mock_find_boot_uuid.return_value = boot_uuid
        mock_subp.return_value = (None, None)

        cc_rhel.update_kernel_commandline_grubby()

        # Get the actual call arguments
        args = mock_subp.call_args[0][0]

        # Verify structure
        assert args[0] == "grubby"
        assert args[1] == "--update-kernel=ALL"
        assert args[2].startswith("--args=")

        # Verify argument content
        args_content = args[2].split("--args=")[1]
        assert "fips=1" in args_content
        assert "boot=UUID=%s" % boot_uuid in args_content
        assert args_content.startswith('"')
        assert args_content.endswith('"')

    @mock.patch("cloudinit.util.logexc")
    @mock.patch("cloudinit.config.cc_rhel.find_boot_uuid")
    @mock.patch("cloudinit.config.cc_rhel.find_boot")
    @mock.patch("cloudinit.subp.subp")
    def test_update_kernel_commandline_logs_error_on_failure(
        self, mock_subp, mock_find_boot, mock_find_boot_uuid, mock_logexc
    ):
        """Test that errors are logged when grubby fails."""
        error = subp.ProcessExecutionError("grubby error", exit_code=1)
        mock_find_boot.return_value = "/dev/sda1"
        mock_find_boot_uuid.return_value = "12345678"
        mock_subp.side_effect = error

        with pytest.raises(subp.ProcessExecutionError):
            cc_rhel.update_kernel_commandline_grubby()

        # Verify logexc was called
        mock_logexc.assert_called_once()


class TestRHELModuleIntegration:
    """Integration-style tests for the RHEL module."""

    @mock.patch("cloudinit.config.cc_rhel._configure_fips")
    def test_handle_full_workflow(self, mock_configure_fips):
        """Test complete handle workflow with RHEL configuration."""
        rhel_cfg = {"fips_mode": True}
        cfg = {"rhel": rhel_cfg}
        cloud = get_cloud("rhel")

        cc_rhel.handle("cc_rhel", cfg, cloud, [])
        mock_configure_fips.assert_called_once_with(rhel_cfg, cloud)

    @mock.patch("cloudinit.util.fips_enabled")
    @mock.patch("os.path.exists")
    @mock.patch("cloudinit.subp.subp")
    @mock.patch("cloudinit.util.fire_reboot")
    @mock.patch("cloudinit.config.cc_rhel.is_efi_boot")
    @mock.patch("cloudinit.config.cc_rhel.update_kernel_commandline_grubby")
    def test_end_to_end_fips_enablement(
        self,
        mock_kernel,
        mock_efi,
        mock_reboot,
        mock_subp,
        mock_exists,
        mock_fips_enabled,
    ):
        """Test end-to-end FIPS enablement workflow."""
        # FIPS not enabled, helper exists
        mock_exists.return_value = True
        mock_fips_enabled.return_value = False
        mock_efi.return_value = False

        cfg = {"rhel": {"fips_mode": True}}
        cloud = get_cloud("rhel")

        with mock.patch("cloudinit.util.FIPS_UNSUPPORTED_KEY_NAMES", []):
            cc_rhel.handle("cc_rhel", cfg, cloud, [])

        # Verify the complete workflow
        expected_path = os.path.join(
            cc_rhel.FIPS_HELPER_PATH, cc_rhel.FIPS_HELPER
        )
        mock_subp.assert_called_once_with([expected_path, "cloud-init"])
        mock_fips_enabled.assert_called_once()
        mock_reboot.assert_called_once()


class TestRhelSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        [
            # rhel must have at least one property
            ({"rhel": {}}, SCHEMA_EMPTY_ERROR),
            # one property should be "fips_mode"
            ({"rhel": {"abc": False}}, UNEXPECTED_PROP.format("abc")),
            # only "fips_mode" property is supported and nothing else
            (
                {"rhel": {"fips_mode": False, "cmdline": "foo"}},
                UNEXPECTED_PROP.format("cmdline"),
            ),
        ],
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        with pytest.raises(
            SchemaValidationError, match=error_msg if error_msg else None
        ):
            validate_cloudconfig_schema(config, get_schema(), strict=True)
