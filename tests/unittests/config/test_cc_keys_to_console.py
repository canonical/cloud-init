"""Tests for cc_keys_to_console."""

import re
from types import SimpleNamespace
from unittest import mock

import pytest

from cloudinit import paths
from cloudinit.config import cc_keys_to_console
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from cloudinit.distros.photon import Distro as PhotonDistro
from tests.unittests.helpers import skipUnlessJsonSchema


class TestHandle:
    """Tests for cloudinit.config.cc_keys_to_console.handle."""

    @mock.patch("cloudinit.config.cc_keys_to_console.log_util.multi_log")
    @mock.patch("cloudinit.config.cc_keys_to_console.os.path.exists")
    @mock.patch("cloudinit.config.cc_keys_to_console.subp.subp")
    @pytest.mark.parametrize(
        "cfg,subp_called",
        [
            ({}, True),  # Default to emitting keys
            ({"ssh": {}}, True),  # Default even if we have the parent key
            (
                {"ssh": {"emit_keys_to_console": True}},
                True,
            ),  # Explicitly enabled
            ({"ssh": {"emit_keys_to_console": False}}, False),  # Disabled
        ],
    )
    def test_emit_keys_to_console_config(
        self, m_subp, m_path_exists, _m_multi_log, cfg, subp_called
    ):
        # Ensure we always find the helper
        m_path_exists.return_value = True
        m_subp.return_value = ("", "")

        cloud = mock.Mock(distro=mock.Mock(usr_lib_exec="/usr/lib"))
        cc_keys_to_console.handle("name", cfg, cloud, ())

        assert subp_called == (m_subp.call_count == 1)

    @pytest.mark.parametrize(
        "helper_dir", ["usr/libexec/cloud-init", 'custom "helpers"/cloud-init']
    )
    def test_photon_uses_configured_helper(self, helper_dir, tmp_path, mocker):
        helper = tmp_path / helper_dir / "write-ssh-key-fingerprints"
        helper.parent.mkdir(parents=True)
        helper.touch(mode=0o755)
        mocker.patch.object(paths, "LIB_EXEC_DIR", str(helper.parent))
        m_subp = mocker.patch.object(
            cc_keys_to_console.subp, "subp", return_value=("fingerprints", "")
        )
        m_multi_log = mocker.patch.object(
            cc_keys_to_console.log_util, "multi_log"
        )
        distro = PhotonDistro("photon", {}, None)
        assert distro.usr_lib_exec == "/usr/libexec"

        cc_keys_to_console.handle(
            "keys_to_console", {}, SimpleNamespace(distro=distro), []
        )

        m_subp.assert_called_once_with([str(helper), "", ""])
        m_multi_log.assert_called_once_with(
            "fingerprints\n", stderr=False, console=True
        )

    def test_missing_configured_helper_does_not_use_legacy_path(
        self, tmp_path, mocker, caplog
    ):
        legacy_base = tmp_path / "legacy"
        legacy_helper = (
            legacy_base / "cloud-init" / "write-ssh-key-fingerprints"
        )
        legacy_helper.parent.mkdir(parents=True)
        legacy_helper.touch(mode=0o755)
        configured_dir = tmp_path / "configured" / "cloud-init"
        mocker.patch.object(paths, "LIB_EXEC_DIR", str(configured_dir))
        m_subp = mocker.patch.object(cc_keys_to_console.subp, "subp")
        m_multi_log = mocker.patch.object(
            cc_keys_to_console.log_util, "multi_log"
        )
        cloud = SimpleNamespace(
            distro=SimpleNamespace(usr_lib_exec=str(legacy_base))
        )

        cc_keys_to_console.handle("keys_to_console", {}, cloud, [])

        m_subp.assert_not_called()
        m_multi_log.assert_not_called()
        assert (
            "helper tool not found at "
            f"{configured_dir / 'write-ssh-key-fingerprints'}"
        ) in caplog.text


class TestHelperToolPath:
    @pytest.mark.parametrize(
        "distro,expected_base",
        [
            (SimpleNamespace(usr_lib_exec="/usr/lib"), "/usr/lib"),
            (SimpleNamespace(usr_lib_exec="/usr/libexec"), "/usr/libexec"),
            (SimpleNamespace(usr_lib_exec="/usr/local/lib"), "/usr/local/lib"),
            (
                SimpleNamespace(usr_lib_exec="/usr/local/libexec"),
                "/usr/local/libexec",
            ),
            (SimpleNamespace(), "/usr/lib"),
        ],
    )
    def test_source_checkout_preserves_distro_default(
        self, distro, expected_base, mocker
    ):
        mocker.patch.object(paths, "LIB_EXEC_DIR", None)

        assert cc_keys_to_console._get_helper_tool_path(distro) == (
            f"{expected_base}/cloud-init/write-ssh-key-fingerprints"
        )


class TestKeysToConsoleSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        (
            # Valid schemas are covered by meta examples tests in test_schema
            # Invalid schemas
            (
                {"ssh": {}},
                (
                    "Cloud config schema errors: ssh:"
                    " 'emit_keys_to_console' is a required property"
                ),
            ),
            (  # Avoid common failure giving a string 'false' instead of false
                {"ssh": {"emit_keys_to_console": "false"}},
                (
                    "Cloud config schema errors:"
                    " ssh.emit_keys_to_console: 'false'"
                    " is not of type 'boolean'"
                ),
            ),
            (
                {"ssh": {"noextraprop": False, "emit_keys_to_console": False}},
                re.escape(
                    "Cloud config schema errors: ssh:"
                    " Additional properties are not allowed"
                    " ('noextraprop' was unexpected)"
                ),
            ),
            (  # Avoid common failure giving a string 'false' instead of false
                {"ssh": {"emit_keys_to_console": "false"}},
                (
                    "Cloud config schema errors:"
                    " ssh.emit_keys_to_console: 'false'"
                    " is not of type 'boolean'"
                ),
            ),
            (  # Avoid common failure giving a string 'false' instead of false
                {"ssh_key_console_blacklist": False},
                (
                    "Cloud config schema errors:"
                    " ssh_key_console_blacklist: False is not of type 'array'"
                ),
            ),
            (  # Avoid common failure giving a string 'false' instead of false
                {"ssh_key_console_blacklist": [1]},
                (
                    "Cloud config schema errors:"
                    " ssh_key_console_blacklist.0: 1 is not of type 'string'"
                ),
            ),
            (  # Avoid common failure giving a string 'false' instead of false
                {"ssh_key_console_blacklist": [1]},
                (
                    "Cloud config schema errors:"
                    " ssh_key_console_blacklist.0: 1 is not of type 'string'"
                ),
            ),
            (  # Avoid common failure giving a string 'false' instead of false
                {"ssh_fp_console_blacklist": None},
                (
                    "Cloud config schema errors:"
                    " ssh_fp_console_blacklist: None is not of type 'array'"
                ),
            ),
            (  # Avoid common failure giving a string 'false' instead of false
                {"ssh_fp_console_blacklist": [1]},
                (
                    "Cloud config schema errors:"
                    " ssh_fp_console_blacklist.0: 1 is not of type 'string'"
                ),
            ),
            (  # Avoid common failure giving a string 'false' instead of false
                {"ssh_fp_console_blacklist": [1]},
                (
                    "Cloud config schema errors:"
                    " ssh_fp_console_blacklist.0: 1 is not of type 'string'"
                ),
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
