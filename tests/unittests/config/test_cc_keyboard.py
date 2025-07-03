# This file is part of cloud-init. See LICENSE file for license information.

"""Tests cc_keyboard module"""

import os
import re
from unittest import mock

import pytest

from cloudinit.config import cc_keyboard
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import (
    FilesystemMockingTestCase,
    populate_dir,
    skipUnlessJsonSchema,
)
from tests.unittests.util import get_cloud


class TestKeyboardSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        (
            # Valid schemas
            ({"keyboard": {"layout": "somestring"}}, None),
            # Invalid schemas
            (
                {"keyboard": {}},
                "Cloud config schema errors: keyboard: 'layout' is a"
                " required property",
            ),
            (
                {"keyboard": "bogus"},
                "Cloud config schema errors: keyboard: 'bogus' is not"
                " of type 'object'",
            ),
            (
                {"keyboard": {"layout": 1}},
                "Cloud config schema errors: keyboard.layout: 1 is not"
                " of type 'string'",
            ),
            (
                {"keyboard": {"layout": "somestr", "model": None}},
                "Cloud config schema errors: keyboard.model: None is not"
                " of type 'string'",
            ),
            (
                {"keyboard": {"layout": "somestr", "variant": [1]}},
                re.escape(
                    "Cloud config schema errors: keyboard.variant: [1] is"
                    " not of type 'string'"
                ),
            ),
            (
                {"keyboard": {"layout": "somestr", "options": {}}},
                "Cloud config schema errors: keyboard.options: {} is not"
                " of type 'string'",
            ),
            (
                {"keyboard": {"layout": "somestr", "extraprop": "somestr"}},
                re.escape(
                    "Cloud config schema errors: keyboard: Additional"
                    " properties are not allowed ('extraprop' was unexpected)"
                ),
            ),
        ),
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        """Assert expected schema validation and error messages."""
        # New-style schema $defs exist in config/cloud-init-schema*.json
        schema = get_schema()
        if error_msg is None:
            validate_cloudconfig_schema(config, schema, strict=True)
        else:
            with pytest.raises(SchemaValidationError, match=error_msg):
                validate_cloudconfig_schema(config, schema, strict=True)


class TestKeyboard(FilesystemMockingTestCase):
    with_logs = True

    def setUp(self):
        super(TestKeyboard, self).setUp()
        self.root_d = self.tmp_dir()
        self.root_d = self.reRoot()

    @mock.patch("cloudinit.distros.Distro.uses_systemd")
    @mock.patch("cloudinit.distros.subp.subp")
    def test_systemd_linux_cmd(self, m_subp, m_uses_systemd, *args):
        """Non-Debian systems run localectl"""
        cfg = {"keyboard": {"layout": "us", "variant": "us"}}
        layout = "us"
        model = "pc105"
        variant = "us"
        options = ""
        m_uses_systemd.return_value = True
        cloud = get_cloud("fedora")
        cc_keyboard.handle("cc_keyboard", cfg, cloud, [])
        locale_call = mock.call(
            [
                "localectl",
                "set-x11-keymap",
                layout,
                model,
                variant,
                options,
            ]
        )
        assert m_subp.call_args == locale_call

    @mock.patch("cloudinit.util.write_file")
    @mock.patch("cloudinit.distros.subp.subp")
    def test_debian_linux_cmd(self, m_subp, m_write_file):
        """localectl is broken on Debian-based systems so write conf file"""
        cfg = {"keyboard": {"layout": "gb", "variant": "dvorak"}}
        cloud = get_cloud("debian")
        cc_keyboard.handle("cc_keyboard", cfg, cloud, [])

        m_content = m_write_file.call_args[1]["content"]
        assert 'XKBMODEL="pc105"' in m_content
        assert 'XKBLAYOUT="gb"' in m_content
        assert 'XKBVARIANT="dvorak"' in m_content
        assert "/etc/default/keyboard" == m_write_file.call_args[1]["filename"]
        m_subp.assert_called_with(
            ["service", "console-setup", "restart"], capture=True, rcs=None
        )

    @mock.patch("cloudinit.distros.subp.subp")
    def test_alpine_linux_cmd(self, m_subp, *args):
        """Alpine Linux runs setup-keymap"""
        cfg = {"keyboard": {"layout": "us", "variant": "us"}}
        layout = "us"
        variant = "us"
        cloud = get_cloud("alpine")

        # Create a dummy directory and file for keymap
        keymap_dir = "/usr/share/bkeymaps/%s" % "us"
        keymap_file = "%s/%s.bmap.gz" % (keymap_dir, "us")
        os.makedirs("%s%s" % (self.root_d, keymap_dir))
        populate_dir(self.root_d, {keymap_file: "# Test\n"})

        cc_keyboard.handle("cc_keyboard", cfg, cloud, [])
        m_subp.assert_called_once_with(["setup-keymap", layout, variant])

    @mock.patch("cloudinit.distros.subp.subp")
    def test_alpine_linux_ignore_model(self, m_subp):
        """Alpine Linux ignores model setting"""
        cfg = {
            "keyboard": {
                "layout": "us",
                "model": "pc105",
                "variant": "us",
            },
        }
        layout = "us"
        variant = "us"
        cloud = get_cloud("alpine")

        keymap_dir = "/usr/share/bkeymaps/%s" % "us"
        keymap_file = "%s/%s.bmap.gz" % (keymap_dir, "us")
        os.makedirs("%s%s" % (self.root_d, keymap_dir))
        populate_dir(self.root_d, {keymap_file: "# Test\n"})

        cc_keyboard.handle("cc_keyboard", cfg, cloud, [])
        assert (
            "Keyboard model is ignored for Alpine Linux."
            in self.logs.getvalue()
        )
        m_subp.assert_called_once_with(
            [
                "setup-keymap",
                layout,
                variant,
            ],
        )
