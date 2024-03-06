# This file is part of cloud-init. See LICENSE file for license information.

import logging
from unittest import mock

import pytest

from cloudinit.config import cc_ssh_import_id
from tests.unittests.util import get_cloud

LOG = logging.getLogger(__name__)

MODPATH = "cloudinit.config.cc_ssh_import_ids."


class TestIsKeyInNestedDict:
    @pytest.mark.parametrize(
        "cfg,expected",
        (
            ({}, False),
            ({"users": [{"name": "bob"}]}, False),
            ({"ssh_import_id": ["yep"]}, True),
            ({"ssh_import_id": ["yep"], "users": [{"name": "bob"}]}, True),
            (
                {
                    "apt": {"preserve_sources_list": True},
                    "ssh_import_id": ["yep"],
                    "users": [{"name": "bob"}],
                },
                True,
            ),
            (
                {
                    "apt": [{}],
                    "ssh_import_id": ["yep"],
                    "users": [{"name": "bob"}],
                },
                True,
            ),
            (
                {
                    "apt": {"preserve_sources_list": True},
                    "users": [
                        {"name": "bob"},
                        {"name": "judy", "ssh_import_id": ["yep"]},
                    ],
                },
                True,
            ),
        ),
    )
    def test_find_ssh_import_id_directives(self, cfg, expected):
        assert expected is cc_ssh_import_id.is_key_in_nested_dict(
            cfg, "ssh_import_id"
        )


class TestHandleSshImportIDs:
    """Test cc_ssh_import_id handling of config."""

    @pytest.mark.parametrize(
        "cfg,log",
        (
            ({}, "no 'ssh_import_id' directives found"),
            (
                {"users": [{"name": "bob"}]},
                "no 'ssh_import_id' directives found",
            ),
            ({"ssh_import_id": ["bobkey"]}, "ssh-import-id is not installed"),
        ),
    )
    @mock.patch("cloudinit.subp.which")
    def test_skip_inapplicable_configs(self, m_which, cfg, log, caplog):
        """Skip config without ssh_import_id"""
        m_which.return_value = None
        cloud = get_cloud("ubuntu")
        cc_ssh_import_id.handle("name", cfg, cloud, [])
        assert log in caplog.text

    @mock.patch("cloudinit.ssh_util.pwd.getpwnam")
    @mock.patch("cloudinit.config.cc_ssh_import_id.subp.subp")
    @mock.patch("cloudinit.subp.which")
    def test_use_sudo(self, m_which, m_subp, m_getpwnam):
        """Check that sudo is available and use that"""
        m_which.return_value = "/usr/bin/ssh-import-id"
        ids = ["waffle"]
        user = "bob"
        cc_ssh_import_id.import_ssh_ids(ids, user)
        m_subp.assert_called_once_with(
            [
                "sudo",
                "--preserve-env=https_proxy",
                "-Hu",
                user,
                "ssh-import-id",
            ]
            + ids,
            capture=False,
        )

    @mock.patch("cloudinit.ssh_util.pwd.getpwnam")
    @mock.patch("cloudinit.config.cc_ssh_import_id.subp.subp")
    @mock.patch("cloudinit.subp.which")
    def test_use_doas(self, m_which, m_subp, m_getpwnam):
        """Check that doas is available and use that"""
        m_which.side_effect = [None, "/usr/bin/doas"]
        ids = ["waffle"]
        user = "bob"
        cc_ssh_import_id.import_ssh_ids(ids, user)
        m_subp.assert_called_once_with(
            ["doas", "-u", user, "ssh-import-id"] + ids, capture=False
        )

    @mock.patch("cloudinit.ssh_util.pwd.getpwnam")
    @mock.patch("cloudinit.config.cc_ssh_import_id.subp.subp")
    @mock.patch("cloudinit.subp.which")
    def test_use_neither_sudo_nor_doas(
        self, m_which, m_subp, m_getpwnam, caplog
    ):
        """Test when neither sudo nor doas is available"""
        m_which.return_value = None
        ids = ["waffle"]
        user = "bob"
        cc_ssh_import_id.import_ssh_ids(ids, user)
        assert (
            "Neither sudo nor doas available! Unable to import SSH ids"
        ) in caplog.text
