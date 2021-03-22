"""Tests for cc_keys_to_console."""
from unittest import mock

import pytest

from cloudinit.config import cc_keys_to_console


class TestHandle:
    """Tests for cloudinit.config.cc_keys_to_console.handle.

    TODO: These tests only cover the emit_keys_to_console config option, they
    should be expanded to cover the full functionality.
    """

    @mock.patch("cloudinit.config.cc_keys_to_console.util.multi_log")
    @mock.patch("cloudinit.config.cc_keys_to_console.os.path.exists")
    @mock.patch("cloudinit.config.cc_keys_to_console.subp.subp")
    @pytest.mark.parametrize("cfg,subp_called", [
        ({}, True),  # Default to emitting keys
        ({"ssh": {}}, True),  # Default even if we have the parent key
        ({"ssh": {"emit_keys_to_console": True}}, True),  # Explicitly enabled
        ({"ssh": {"emit_keys_to_console": False}}, False),  # Disabled
    ])
    def test_emit_keys_to_console_config(
        self, m_subp, m_path_exists, _m_multi_log, cfg, subp_called
    ):
        # Ensure we always find the helper
        m_path_exists.return_value = True
        m_subp.return_value = ("", "")

        cc_keys_to_console.handle("name", cfg, mock.Mock(), mock.Mock(), ())

        assert subp_called == (m_subp.call_count == 1)
