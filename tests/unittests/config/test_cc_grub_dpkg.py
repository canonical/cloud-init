# This file is part of cloud-init. See LICENSE file for license information.

from logging import Logger
from unittest import mock

import pytest

from cloudinit.config.cc_grub_dpkg import fetch_idevs, handle
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from cloudinit.subp import ProcessExecutionError
from tests.unittests.helpers import skipUnlessJsonSchema


class TestFetchIdevs:
    """Tests cc_grub_dpkg.fetch_idevs()"""

    # Note: udevadm info returns devices in a large single line string
    @pytest.mark.parametrize(
        "grub_output,path_exists,expected_log_call,udevadm_output"
        ",expected_idevs",
        [
            # Inside a container, grub not installed
            (
                ProcessExecutionError(reason=FileNotFoundError()),
                False,
                mock.call("'grub-probe' not found in $PATH"),
                "",
                "",
            ),
            # Inside a container, grub installed
            (
                ProcessExecutionError(stderr="failed to get canonical path"),
                False,
                mock.call("grub-probe 'failed to get canonical path'"),
                "",
                "",
            ),
            # KVM Instance
            (
                ["/dev/vda"],
                True,
                None,
                (
                    "/dev/disk/by-path/pci-0000:00:00.0 ",
                    "/dev/disk/by-path/virtio-pci-0000:00:00.0 ",
                ),
                "/dev/vda",
            ),
            # Xen Instance
            (
                ["/dev/xvda"],
                True,
                None,
                "",
                "/dev/xvda",
            ),
            # NVMe Hardware Instance
            (
                ["/dev/nvme1n1"],
                True,
                None,
                (
                    "/dev/disk/by-id/nvme-Company_hash000 ",
                    "/dev/disk/by-id/nvme-nvme.000-000-000-000-000 ",
                    "/dev/disk/by-path/pci-0000:00:00.0-nvme-0 ",
                ),
                "/dev/disk/by-id/nvme-Company_hash000",
            ),
            # SCSI Hardware Instance
            (
                ["/dev/sda"],
                True,
                None,
                (
                    "/dev/disk/by-id/company-user-1 ",
                    "/dev/disk/by-id/scsi-0Company_user-1 ",
                    "/dev/disk/by-path/pci-0000:00:00.0-scsi-0:0:0:0 ",
                ),
                "/dev/disk/by-id/company-user-1",
            ),
        ],
    )
    @mock.patch("cloudinit.config.cc_grub_dpkg.util.logexc")
    @mock.patch("cloudinit.config.cc_grub_dpkg.os.path.exists")
    @mock.patch("cloudinit.config.cc_grub_dpkg.subp.subp")
    def test_fetch_idevs(
        self,
        m_subp,
        m_exists,
        m_logexc,
        grub_output,
        path_exists,
        expected_log_call,
        udevadm_output,
        expected_idevs,
    ):
        """Tests outputs from grub-probe and udevadm info against grub-dpkg"""
        m_subp.side_effect = [grub_output, ["".join(udevadm_output)]]
        m_exists.return_value = path_exists
        log = mock.Mock(spec=Logger)
        idevs = fetch_idevs(log)
        assert expected_idevs == idevs
        if expected_log_call is not None:
            assert expected_log_call in log.debug.call_args_list


class TestHandle:
    """Tests cc_grub_dpkg.handle()"""

    @pytest.mark.parametrize(
        "cfg_idevs,cfg_idevs_empty,fetch_idevs_output,expected_log_output",
        [
            (
                # No configuration
                None,
                None,
                "/dev/disk/by-id/nvme-Company_hash000",
                (
                    "Setting grub debconf-set-selections with ",
                    "'/dev/disk/by-id/nvme-Company_hash000','false'",
                ),
            ),
            (
                # idevs set, idevs_empty unset
                "/dev/sda",
                None,
                "/dev/sda",
                (
                    "Setting grub debconf-set-selections with ",
                    "'/dev/sda','false'",
                ),
            ),
            (
                # idevs unset, idevs_empty set
                None,
                "true",
                "/dev/xvda",
                (
                    "Setting grub debconf-set-selections with ",
                    "'/dev/xvda','true'",
                ),
            ),
            (
                # idevs set, idevs_empty set
                "/dev/vda",
                False,
                "/dev/disk/by-id/company-user-1",
                (
                    "Setting grub debconf-set-selections with ",
                    "'/dev/vda','false'",
                ),
            ),
            (
                # idevs set, idevs_empty set
                # Respect what the user defines, even if its logically wrong
                "/dev/nvme0n1",
                True,
                "",
                (
                    "Setting grub debconf-set-selections with ",
                    "'/dev/nvme0n1','true'",
                ),
            ),
        ],
    )
    @mock.patch("cloudinit.config.cc_grub_dpkg.fetch_idevs")
    @mock.patch("cloudinit.config.cc_grub_dpkg.util.logexc")
    @mock.patch("cloudinit.config.cc_grub_dpkg.subp.subp")
    def test_handle(
        self,
        m_subp,
        m_logexc,
        m_fetch_idevs,
        cfg_idevs,
        cfg_idevs_empty,
        fetch_idevs_output,
        expected_log_output,
    ):
        """Test setting of correct debconf database entries"""
        m_fetch_idevs.return_value = fetch_idevs_output
        log = mock.Mock(spec=Logger)
        cfg = {"grub_dpkg": {}}
        if cfg_idevs is not None:
            cfg["grub_dpkg"]["grub-pc/install_devices"] = cfg_idevs
        if cfg_idevs_empty is not None:
            cfg["grub_dpkg"]["grub-pc/install_devices_empty"] = cfg_idevs_empty
        handle(mock.Mock(), cfg, mock.Mock(), log, mock.Mock())
        log.debug.assert_called_with("".join(expected_log_output))


class TestGrubDpkgSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        (
            ({"grub_dpkg": {"grub-pc/install_devices_empty": False}}, None),
            ({"grub_dpkg": {"grub-pc/install_devices_empty": "off"}}, None),
            (
                {"grub_dpkg": {"enabled": "yes"}},
                "'yes' is not of type 'boolean'",
            ),
            (
                {"grub_dpkg": {"grub-pc/install_devices": ["/dev/sda"]}},
                r"\['/dev/sda'\] is not of type 'string'",
            ),
        ),
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        """Assert expected schema validation and error messages."""
        schema = get_schema()
        if error_msg is None:
            validate_cloudconfig_schema(config, schema, strict=True)
        else:
            with pytest.raises(SchemaValidationError, match=error_msg):
                validate_cloudconfig_schema(config, schema, strict=True)
