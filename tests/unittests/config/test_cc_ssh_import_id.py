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
