# This file is part of cloud-init. See LICENSE file for license information.
import pytest

from cloudinit import subp
from cloudinit.config import cc_wireguard
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import CiTestCase, mock, skipUnlessJsonSchema

NL = "\n"
# Module path used in mocks
MPATH = "cloudinit.config.cc_wireguard"


class FakeCloud(object):
    def __init__(self, distro):
        self.distro = distro


class TestWireGuard(CiTestCase):

    with_logs = True
    allowed_subp = [CiTestCase.SUBP_SHELL_TRUE]

    def setUp(self):
        super(TestWireGuard, self).setUp()
        self.tmp = self.tmp_dir()

    def test_readiness_probe_schema_non_string_values(self):
        """ValueError raised for any values expected as string type."""
        wg_readinessprobes = [1, ["not-a-valid-command"]]
        errors = [
            "Expected a string for readinessprobe at 0. Found 1",
            "Expected a string for readinessprobe at 1."
            " Found ['not-a-valid-command']",
        ]
        with self.assertRaises(ValueError) as context_mgr:
            cc_wireguard.readinessprobe_command_validation(wg_readinessprobes)
        error_msg = str(context_mgr.exception)
        for error in errors:
            self.assertIn(error, error_msg)

    def test_suppl_schema_error_on_missing_keys(self):
        """ValueError raised reporting any missing required keys"""
        cfg = {}
        match = (
            f"Invalid wireguard interface configuration:{NL}"
            "Missing required wg:interfaces keys: config_path, content, name"
        )
        with self.assertRaisesRegex(ValueError, match):
            cc_wireguard.supplemental_schema_validation(cfg)

    def test_suppl_schema_error_on_non_string_values(self):
        """ValueError raised for any values expected as string type."""
        cfg = {"name": 1, "config_path": 2, "content": 3}
        errors = [
            "Expected a string for wg:interfaces:config_path. Found 2",
            "Expected a string for wg:interfaces:content. Found 3",
            "Expected a string for wg:interfaces:name. Found 1",
        ]
        with self.assertRaises(ValueError) as context_mgr:
            cc_wireguard.supplemental_schema_validation(cfg)
        error_msg = str(context_mgr.exception)
        for error in errors:
            self.assertIn(error, error_msg)

    def test_write_config_failed(self):
        """Errors when writing config are raised."""
        wg_int = {"name": "wg0", "config_path": "/no/valid/path"}

        with self.assertRaises(RuntimeError) as context_mgr:
            cc_wireguard.write_config(wg_int)
        self.assertIn(
            "Failure writing Wireguard configuration file /no/valid/path:\n",
            str(context_mgr.exception),
        )

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

        with self.assertRaises(RuntimeError) as context_mgr:
            cc_wireguard.readinessprobe(wg_readinessprobes)
        self.assertIn(
            "Failed running readinessprobe command:\n"
            "not-a-valid-command: Unexpected error while"
            " running command.\n"
            "Command: -\nExit code: -\nReason: -\n"
            "Stdout: not-a-valid-command: command not found\nStderr: -",
            str(context_mgr.exception),
        )

    @mock.patch("%s.subp.subp" % MPATH)
    def test_enable_wg_on_error(self, m_subp):
        """Errors when enabling wireguard interfaces are raised."""
        wg_int = {"name": "wg0"}
        distro = mock.MagicMock()  # No errors raised
        distro.manage_service.side_effect = subp.ProcessExecutionError(
            "systemctl start wg-quik@wg0 failed: exit code 1"
        )
        mycloud = FakeCloud(distro)
        with self.assertRaises(RuntimeError) as context_mgr:
            cc_wireguard.enable_wg(wg_int, mycloud)
        self.assertEqual(
            "Failed enabling/starting Wireguard interface(s):\n"
            "Unexpected error while running command.\n"
            "Command: -\nExit code: -\nReason: -\n"
            "Stdout: systemctl start wg-quik@wg0 failed: exit code 1\n"
            "Stderr: -",
            str(context_mgr.exception),
        )

    @mock.patch("%s.subp.which" % MPATH)
    def test_maybe_install_wg_tools_noop_when_wg_tools_present(self, m_which):
        """Do nothing if wireguard-tools already exists."""
        m_which.return_value = "/usr/bin/wg"  # already installed
        distro = mock.MagicMock()
        distro.update_package_sources.side_effect = RuntimeError(
            "Some apt error"
        )
        cc_wireguard.maybe_install_wireguard_tools(cloud=FakeCloud(distro))

    @mock.patch("%s.subp.which" % MPATH)
    def test_maybe_install_wf_tools_raises_update_errors(self, m_which):
        """maybe_install_wireguard_tools logs and raises apt update errors."""
        m_which.return_value = None
        distro = mock.MagicMock()
        distro.update_package_sources.side_effect = RuntimeError(
            "Some apt error"
        )
        with self.assertRaises(RuntimeError) as context_manager:
            cc_wireguard.maybe_install_wireguard_tools(cloud=FakeCloud(distro))
        self.assertEqual("Some apt error", str(context_manager.exception))
        self.assertIn("Package update failed\nTraceback", self.logs.getvalue())

    @mock.patch("%s.subp.which" % MPATH)
    def test_maybe_install_wg_raises_install_errors(self, m_which):
        """maybe_install_wireguard_tools logs and raises package
        install errors."""
        m_which.return_value = None
        distro = mock.MagicMock()
        distro.update_package_sources.return_value = None
        distro.install_packages.side_effect = RuntimeError(
            "Some install error"
        )
        with self.assertRaises(RuntimeError) as context_manager:
            cc_wireguard.maybe_install_wireguard_tools(cloud=FakeCloud(distro))
        self.assertEqual("Some install error", str(context_manager.exception))
        self.assertIn(
            "Failed to install wireguard-tools\n", self.logs.getvalue()
        )

    @mock.patch("%s.subp.subp" % MPATH)
    @mock.patch("%s.subp.which" % MPATH)
    def test_maybe_install_wg_failed_load_module(self, m_which, m_subp):
        """maybe_install_wireguard_tools logs and raises
        kernel modules loading error."""
        m_which.return_value = None
        distro = mock.MagicMock()
        distro.update_package_sources.return_value = None
        distro.install_packages.return_value = None
        m_subp.side_effect = subp.ProcessExecutionError(
            "Some kernel module load error"
        )
        with self.assertRaises(subp.ProcessExecutionError) as context_manager:
            cc_wireguard.maybe_install_wireguard_tools(cloud=FakeCloud(distro))
        self.assertEqual(
            "Unexpected error while running command.\n"
            "Command: -\nExit code: -\nReason: -\n"
            "Stdout: Some kernel module load error\n"
            "Stderr: -",
            str(context_manager.exception),
        )
        self.assertIn(
            "WARNING: Could not load wireguard module:\n", self.logs.getvalue()
        )

    @mock.patch("%s.subp.which" % MPATH)
    def test_maybe_install_wg_tools_happy_path(self, m_which):
        """maybe_install_wireguard_tools installs wireguard-tools."""
        m_which.return_value = None
        distro = mock.MagicMock()  # No errors raised
        cc_wireguard.maybe_install_wireguard_tools(cloud=FakeCloud(distro))
        distro.update_package_sources.assert_called_once_with()
        distro.install_packages.assert_called_once_with(["wireguard-tools"])

    @mock.patch("%s.maybe_install_wireguard_tools" % MPATH)
    def test_handle_no_config(self, m_maybe_install_wireguard_tools):
        """When no wireguard configuration is provided, nothing happens."""
        cfg = {}
        cc_wireguard.handle(
            "wg", cfg=cfg, cloud=None, log=self.logger, args=None
        )
        self.assertIn(
            "DEBUG: Skipping module named wg, no 'wireguard'"
            " configuration found",
            self.logs.getvalue(),
        )
        self.assertEqual(m_maybe_install_wireguard_tools.call_count, 0)

    def test_readiness_probe_with_non_string_values(self):
        """ValueError raised for any values expected as string type."""
        cfg = [1, 2]
        errors = [
            "Expected a string for readinessprobe at 0. Found 1",
            "Expected a string for readinessprobe at 1. Found 2",
        ]
        with self.assertRaises(ValueError) as context_manager:
            cc_wireguard.readinessprobe_command_validation(cfg)
        error_msg = str(context_manager.exception)
        for error in errors:
            self.assertIn(error, error_msg)


class TestWireguardSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        [
            # Allow empty wireguard config
            ({"wireguard": None}, None),
        ],
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        if error_msg is not None:
            with pytest.raises(SchemaValidationError, match=error_msg):
                validate_cloudconfig_schema(config, get_schema(), strict=True)
        else:
            validate_cloudconfig_schema(config, get_schema(), strict=True)


# vi: ts=4 expandtab
