# This file is part of cloud-init. See LICENSE file for license information.

"""Tests cc_apt_pipelining handler"""

import cloudinit.config.cc_apt_pipelining as cc_apt_pipelining
from tests.unittests.helpers import mock


class TestAptPipelining:
    @mock.patch("cloudinit.config.cc_apt_pipelining.util.write_file")
    def test_not_disabled_by_default(self, m_write_file):
        """ensure that default behaviour is to not disable pipelining"""
        cc_apt_pipelining.handle("foo", {}, None, mock.MagicMock(), None)
        assert 0 == m_write_file.call_count

    @mock.patch("cloudinit.config.cc_apt_pipelining.util.write_file")
    def test_false_disables_pipelining(self, m_write_file):
        """ensure that pipelining can be disabled with correct config"""
        cc_apt_pipelining.handle(
            "foo", {"apt_pipelining": "false"}, None, mock.MagicMock(), None
        )
        assert 1  == m_write_file.call_count
        args, _ = m_write_file.call_args
        assert cc_apt_pipelining.DEFAULT_FILE == args[0]
        assert 'Pipeline-Depth "0"' in args[1]

    def test_failure_schema_


# vi: ts=4 expandtab
