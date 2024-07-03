# This file is part of cloud-init. See LICENSE file for license information.

from unittest import mock

import pytest

from cloudinit.config.cc_grub_dpkg import fetch_idevs, handle
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from cloudinit.subp import ProcessExecutionError, SubpResult
from tests.unittests.helpers import does_not_raise, skipUnlessJsonSchema


class TestFetchIdevs:
    """Tests cc_grub_dpkg.fetch_idevs()"""

    # Note: udevadm info returns devices in a large single line string
    @pytest.mark.parametrize(
        "grub_output,path_exists,expected_log_call,udevadm_output"
        ",expected_idevs,is_efi_boot",
        [
            # Inside a container, grub not installed
            (
                ProcessExecutionError(reason=FileNotFoundError()),
                False,
                mock.call("'grub-probe' not found in $PATH"),
                "",
                "",
                False,
            ),
            # Inside a container, grub installed
            (
                ProcessExecutionError(stderr="failed to get canonical path"),
                False,
                mock.call("grub-probe 'failed to get canonical path'"),
                "",
                "",
                False,
            ),
            # KVM Instance
            (
                SubpResult("/dev/vda", ""),
                True,
                None,
                (
                    "/dev/disk/by-path/pci-0000:00:00.0 ",
                    "/dev/disk/by-path/virtio-pci-0000:00:00.0 ",
                ),
                "/dev/vda",
                False,
            ),
            # Xen Instance
            (
                SubpResult("/dev/xvda", ""),
                True,
                None,
                "",
                "/dev/xvda",
                False,
            ),
            # NVMe Hardware Instance
            (
                SubpResult("/dev/nvme1n1", ""),
                True,
                None,
                (
                    "/dev/disk/by-id/nvme-Company_hash000 ",
                    "/dev/disk/by-id/nvme-nvme.000-000-000-000-000 ",
                    "/dev/disk/by-path/pci-0000:00:00.0-nvme-0 ",
                ),
                "/dev/disk/by-id/nvme-Company_hash000",
                False,
            ),
            # SCSI Hardware Instance
            (
                SubpResult("/dev/sda", ""),
                True,
                None,
                (
                    "/dev/disk/by-id/company-user-1 ",
                    "/dev/disk/by-id/scsi-0Company_user-1 ",
                    "/dev/disk/by-path/pci-0000:00:00.0-scsi-0:0:0:0 ",
                ),
                "/dev/disk/by-id/company-user-1",
                False,
            ),
            # UEFI Hardware Instance
            (
                SubpResult("/dev/sda2", ""),
                True,
                None,
                (
                    "/dev/disk/by-id/scsi-3500a075116e6875a "
                    "/dev/disk/by-id/scsi-SATA_Crucial_CT525MX3_171816E6875A "
                    "/dev/disk/by-id/scsi-0ATA_Crucial_CT525MX3_171816E6875A "
                    "/dev/disk/by-path/pci-0000:00:17.0-ata-1 "
                    "/dev/disk/by-id/wwn-0x500a075116e6875a "
                    "/dev/disk/by-id/ata-Crucial_CT525MX300SSD1_171816E6875A"
                ),
                "/dev/disk/by-id/ata-Crucial_CT525MX300SSD1_171816E6875A-"
                "part1",
                True,
            ),
        ],
    )
    @mock.patch("cloudinit.config.cc_grub_dpkg.is_efi_booted")
    @mock.patch("cloudinit.config.cc_grub_dpkg.util.logexc")
    @mock.patch("cloudinit.config.cc_grub_dpkg.os.path.exists")
    @mock.patch("cloudinit.config.cc_grub_dpkg.subp.subp")
    @mock.patch("cloudinit.config.cc_grub_dpkg.LOG")
    def test_fetch_idevs(
        self,
        m_log,
        m_subp,
        m_exists,
        m_logexc,
        m_efi_booted,
        grub_output,
        path_exists,
        expected_log_call,
        udevadm_output,
        expected_idevs,
        is_efi_boot,
    ):
        """Tests outputs from grub-probe and udevadm info against grub_dpkg"""
        m_subp.side_effect = [
            grub_output,
            SubpResult("".join(udevadm_output), ""),
        ]
        m_exists.return_value = path_exists
        m_efi_booted.return_value = is_efi_boot

        idevs = fetch_idevs()

        if is_efi_boot:
            assert expected_idevs.startswith(idevs) is True
        else:
            assert idevs == expected_idevs

        if expected_log_call is not None:
            assert expected_log_call in m_log.debug.call_args_list


class TestHandle:
    """Tests cc_grub_dpkg.handle()"""

    @pytest.mark.parametrize(
        "cfg_idevs,cfg_idevs_empty,fetch_idevs_output,"
        "expected_log_output,is_uefi",
        [
            (
                # No configuration
                None,
                None,
                "/dev/disk/by-id/nvme-Company_hash000",
                (
                    "Setting grub debconf-set-selections with '%s'",
                    "grub-pc grub-pc/install_devices string "
                    "/dev/disk/by-id/nvme-Company_hash000\n"
                    "grub-pc grub-pc/install_devices_empty boolean false\n",
                ),
                False,
            ),
            (
                # idevs set, idevs_empty unset
                "/dev/sda",
                None,
                "/dev/sda",
                (
                    "Setting grub debconf-set-selections with '%s'",
                    "grub-pc grub-pc/install_devices string /dev/sda\n"
                    "grub-pc grub-pc/install_devices_empty boolean false\n",
                ),
                False,
            ),
            (
                # idevs unset, idevs_empty set
                None,
                "true",
                "/dev/xvda",
                (
                    "Setting grub debconf-set-selections with '%s'",
                    "grub-pc grub-pc/install_devices string /dev/xvda\n"
                    "grub-pc grub-pc/install_devices_empty boolean true\n",
                ),
                False,
            ),
            (
                # idevs set, idevs_empty set
                "/dev/vda",
                False,
                "/dev/disk/by-id/company-user-1",
                (
                    "Setting grub debconf-set-selections with '%s'",
                    "grub-pc grub-pc/install_devices string /dev/vda\n"
                    "grub-pc grub-pc/install_devices_empty boolean false\n",
                ),
                False,
            ),
            (
                # idevs set, idevs_empty set
                # Respect what the user defines, even if its logically wrong
                "/dev/nvme0n1",
                True,
                "",
                (
                    "Setting grub debconf-set-selections with '%s'",
                    "grub-pc grub-pc/install_devices string /dev/nvme0n1\n"
                    "grub-pc grub-pc/install_devices_empty boolean true\n",
                ),
                False,
            ),
            (
                # uefi active, idevs set
                "/dev/sda1",
                False,
                "/dev/sda1",
                (
                    "Setting grub debconf-set-selections with '%s'",
                    "grub-pc grub-efi/install_devices string /dev/sda1\n",
                ),
                True,
            ),
        ],
    )
    @mock.patch("cloudinit.config.cc_grub_dpkg.fetch_idevs")
    @mock.patch("cloudinit.config.cc_grub_dpkg.util.logexc")
    @mock.patch("cloudinit.config.cc_grub_dpkg.subp.subp")
    @mock.patch("cloudinit.config.cc_grub_dpkg.is_efi_booted")
    @mock.patch("cloudinit.config.cc_grub_dpkg.LOG")
    def test_handle(
        self,
        m_log,
        m_is_efi_booted,
        m_subp,
        m_logexc,
        m_fetch_idevs,
        cfg_idevs,
        cfg_idevs_empty,
        fetch_idevs_output,
        expected_log_output,
        is_uefi,
    ):
        """Test setting of correct debconf database entries"""
        m_is_efi_booted.return_value = is_uefi
        m_fetch_idevs.return_value = fetch_idevs_output
        cfg = {"grub_dpkg": {}}
        if cfg_idevs is not None:
            cfg["grub_dpkg"]["grub-pc/install_devices"] = cfg_idevs
        if cfg_idevs_empty is not None:
            cfg["grub_dpkg"]["grub-pc/install_devices_empty"] = cfg_idevs_empty
        handle(mock.Mock(), cfg, mock.Mock(), mock.Mock())
        print(m_log.debug.call_args_list)
        m_log.debug.assert_called_with(*expected_log_output)


class TestGrubDpkgSchema:
    @pytest.mark.parametrize(
        "config, expectation, has_errors",
        (
            (
                {"grub_dpkg": {"grub-pc/install_devices_empty": False}},
                does_not_raise(),
                None,
            ),
            (
                {"grub_dpkg": {"grub-pc/install_devices_empty": "off"}},
                pytest.raises(
                    SchemaValidationError,
                    match=(
                        "Cloud config schema deprecations: "
                        "grub_dpkg.grub-pc/install_devices_empty:  "
                        "Changed in version 22.3. Use a boolean value "
                        "instead."
                    ),
                ),
                False,
            ),
            (
                {"grub_dpkg": {"enabled": "yes"}},
                pytest.raises(
                    SchemaValidationError,
                    match="'yes' is not of type 'boolean'",
                ),
                True,
            ),
            (
                {"grub_dpkg": {"grub-pc/install_devices": ["/dev/sda"]}},
                pytest.raises(
                    SchemaValidationError,
                    match=r"\['/dev/sda'\] is not of type 'string'",
                ),
                True,
            ),
            (
                {"grub-dpkg": {"grub-pc/install_devices_empty": False}},
                pytest.raises(
                    SchemaValidationError,
                    match=(
                        "Cloud config schema deprecations: grub-dpkg:"
                        "  Deprecated in version 22.2. Use "
                        "``grub_dpkg`` instead."
                    ),
                ),
                False,
            ),
        ),
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, expectation, has_errors):
        """Assert expected schema validation and error messages."""
        schema = get_schema()
        with expectation as exc_info:
            validate_cloudconfig_schema(config, schema, strict=True)
        if has_errors is not None:
            assert has_errors == exc_info.value.has_errors()
