# This file is part of cloud-init. See LICENSE file for license information.
import logging

import pytest

from cloudinit import subp, util
from cloudinit.config import cc_wireguard
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import mock, skipUnlessJsonSchema

NL = "\n"
# Module path used in mocks
MPATH = "cloudinit.config.cc_wireguard"
MIN_KERNEL_VERSION = (5, 6)


class FakeCloud:
    def __init__(self, distro):
        self.distro = distro


@pytest.mark.usefixtures("fake_filesystem")
class TestWireGuard:
    def test_readiness_probe_schema_non_string_values(self):
        """ValueError raised for any values expected as string type."""
        wg_readinessprobes = [1, ["not-a-valid-command"]]
        error = (
            r"Expected a string for readinessprobe at 0. Found 1"
            r"\nExpected a string for readinessprobe at 1."
            r" Found \['not-a-valid-command'\]"
        )
        with pytest.raises(ValueError, match=error):
            cc_wireguard.readinessprobe_command_validation(wg_readinessprobes)

    def test_suppl_schema_error_on_missing_keys(self):
        """ValueError raised reporting any missing required keys"""
        cfg = {}
        match = (
            f"Invalid wireguard interface configuration:{NL}"
            "Missing required wg:interfaces keys: config_path, content, name"
        )
        with pytest.raises(ValueError, match=match):
            cc_wireguard.supplemental_schema_validation(cfg)

    def test_suppl_schema_error_on_non_string_values(self):
        """ValueError raised for any values expected as string type."""
        cfg = {"name": 1, "config_path": 2, "content": 3}
        error = (
            "Expected a string for wg:interfaces:config_path. Found 2\n"
            "Expected a string for wg:interfaces:content. Found 3\n"
            "Expected a string for wg:interfaces:name. Found 1"
        )
        with pytest.raises(ValueError, match=error):
            cc_wireguard.supplemental_schema_validation(cfg)

    def test_write_config_failed(self):
        """Errors when writing config are raised."""
        wg_int = {"name": "wg0", "config_path": "/no/valid/path"}

        with pytest.raises(
            RuntimeError,
            match="Failure writing Wireguard configuration file"
            " /no/valid/path:\n",
        ):
            cc_wireguard.write_config(wg_int)

    @mock.patch("%s.subp.subp" % MPATH)
    def test_readiness_probe_invalid_command(self, m_subp):
        """Errors when executing readinessprobes are raised."""
        wg_readinessprobes = ["not-a-valid-command"]

        def fake_subp(cmd, capture=None, shell=None):
            fail_cmds = ["not-a-valid-command"]
            if cmd in fail_cmds and capture and shell:
                raise subp.ProcessExecutionError(
                    "not-a-valid-command: command not found"
                )

        m_subp.side_effect = fake_subp

        error = (
            "Failed running readinessprobe command:\n"
            "not-a-valid-command: Unexpected error while"
            " running command.\n"
            "Command: -\nExit code: -\nReason: -\n"
            "Stdout: not-a-valid-command: command not found\nStderr: -"
        )
        with pytest.raises(RuntimeError, match=error):
            cc_wireguard.readinessprobe(wg_readinessprobes)

    @mock.patch("%s.subp.subp" % MPATH)
    def test_enable_wg_on_error(self, m_subp):
        """Errors when enabling wireguard interfaces are raised."""
        wg_int = {"name": "wg0"}
        distro = mock.MagicMock()  # No errors raised
        distro.manage_service.side_effect = subp.ProcessExecutionError(
            "systemctl start wg-quik@wg0 failed: exit code 1"
        )
        mycloud = FakeCloud(distro)
        error = (
            r"Failed enabling/starting Wireguard interface\(s\):\n"
            "Unexpected error while running command.\n"
            "Command: -\nExit code: -\nReason: -\n"
            "Stdout: systemctl start wg-quik@wg0 failed: exit code 1\n"
            "Stderr: -"
        )
        with pytest.raises(RuntimeError, match=error):
            cc_wireguard.enable_wg(wg_int, mycloud)

    @mock.patch("%s.subp.which" % MPATH)
    def test_maybe_install_wg_packages_noop_when_wg_tools_present(
        self, m_which
    ):
        """Do nothing if wireguard-tools already exists."""
        m_which.return_value = "/usr/bin/wg"  # already installed
        distro = mock.MagicMock()
        distro.update_package_sources.side_effect = RuntimeError(
            "Some apt error"
        )
        cc_wireguard.maybe_install_wireguard_packages(cloud=FakeCloud(distro))

    @mock.patch("%s.subp.which" % MPATH)
    @mock.patch("%s.util.kernel_version" % MPATH)
    def test_maybe_install_wf_tools_raises_update_errors(
        self, m_kernel_version, m_which, caplog
    ):
        """maybe_install_wireguard_packages logs and raises
        apt update errors."""
        m_which.return_value = None
        m_kernel_version.return_value = (4, 42)
        distro = mock.MagicMock()
        distro.update_package_sources.side_effect = RuntimeError(
            "Some apt error"
        )
        with pytest.raises(RuntimeError, match="Some apt error"):
            cc_wireguard.maybe_install_wireguard_packages(
                cloud=FakeCloud(distro)
            )
        assert "Package update failed\nTraceback" in caplog.text

    @mock.patch("%s.subp.which" % MPATH)
    @mock.patch("%s.util.kernel_version" % MPATH)
    def test_maybe_install_wg_raises_install_errors(
        self, m_kernel_version, m_which, caplog
    ):
        """maybe_install_wireguard_packages logs and raises package
        install errors."""
        m_which.return_value = None
        m_kernel_version.return_value = (5, 12)
        distro = mock.MagicMock()
        distro.update_package_sources.return_value = None
        distro.install_packages.side_effect = RuntimeError(
            "Some install error"
        )
        with pytest.raises(RuntimeError, match="Some install error"):
            cc_wireguard.maybe_install_wireguard_packages(
                cloud=FakeCloud(distro)
            )
        assert "Failed to install wireguard-tools\n" in caplog.text

    @mock.patch("%s.subp.subp" % MPATH)
    def test_load_wg_module_failed(self, m_subp, caplog):
        """load_wireguard_kernel_module logs and raises
        kernel modules loading error."""
        m_subp.side_effect = subp.ProcessExecutionError(
            "Some kernel module load error"
        )
        error = (
            "Unexpected error while running command.\n"
            "Command: -\nExit code: -\nReason: -\n"
            "Stdout: Some kernel module load error\n"
            "Stderr: -"
        )
        with pytest.raises(subp.ProcessExecutionError, match=error):
            cc_wireguard.load_wireguard_kernel_module()
        assert (
            mock.ANY,
            logging.WARNING,
            "Could not load wireguard module:\n" + error,
        ) in caplog.record_tuples

    @mock.patch("%s.subp.which" % MPATH)
    @mock.patch("%s.util.kernel_version" % MPATH)
    def test_maybe_install_wg_packages_happy_path(
        self, m_kernel_version, m_which
    ):
        """maybe_install_wireguard_packages installs wireguard-tools."""
        packages = ["wireguard-tools"]

        m_kernel_version.return_value = (5, 2)
        if util.kernel_version() < MIN_KERNEL_VERSION:
            packages.append("wireguard")

        m_which.return_value = None
        distro = mock.MagicMock()  # No errors raised
        cc_wireguard.maybe_install_wireguard_packages(cloud=FakeCloud(distro))
        distro.update_package_sources.assert_called_once_with()
        distro.install_packages.assert_called_once_with(packages)

    @mock.patch("%s.maybe_install_wireguard_packages" % MPATH)
    def test_handle_no_config(
        self, m_maybe_install_wireguard_packages, caplog
    ):
        """When no wireguard configuration is provided, nothing happens."""
        cfg = {}
        cc_wireguard.handle("wg", cfg=cfg, cloud=None, args=None)
        assert (
            mock.ANY,
            logging.DEBUG,
            "Skipping module named wg, no 'wireguard' configuration found",
        ) in caplog.record_tuples
        assert m_maybe_install_wireguard_packages.call_count == 0

    def test_readiness_probe_with_non_string_values(self):
        """ValueError raised for any values expected as string type."""
        cfg = [1, 2]
        error = (
            "Expected a string for readinessprobe at 0. Found 1\n"
            "Expected a string for readinessprobe at 1. Found 2"
        )
        with pytest.raises(ValueError, match=error):
            cc_wireguard.readinessprobe_command_validation(cfg)


class TestWireguardSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        [
            # Valid schemas
            (
                {
                    "wireguard": {
                        "interfaces": [
                            {
                                "name": "wg0",
                                "config_path": "/etc/wireguard/wg0.conf",
                                "content": "test",
                            }
                        ]
                    }
                },
                None,
            ),
        ],
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        if error_msg is not None:
            with pytest.raises(SchemaValidationError, match=error_msg):
                validate_cloudconfig_schema(config, get_schema(), strict=True)
        else:
            validate_cloudconfig_schema(config, get_schema(), strict=True)
