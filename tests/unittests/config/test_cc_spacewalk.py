# This file is part of cloud-init. See LICENSE file for license information.

import logging
from unittest import mock

from cloudinit import subp
from cloudinit.config import cc_spacewalk
from tests.unittests import helpers

LOG = logging.getLogger(__name__)


class TestSpacewalk(helpers.TestCase):
    space_cfg = {
        "spacewalk": {
            "server": "localhost",
            "profile_name": "test",
        }
    }

    @mock.patch("cloudinit.config.cc_spacewalk.subp.subp")
    def test_not_is_registered(self, mock_subp):
        mock_subp.side_effect = subp.ProcessExecutionError(exit_code=1)
        self.assertFalse(cc_spacewalk.is_registered())

    @mock.patch("cloudinit.config.cc_spacewalk.subp.subp")
    def test_is_registered(self, mock_subp):
        mock_subp.side_effect = None
        self.assertTrue(cc_spacewalk.is_registered())

    @mock.patch("cloudinit.config.cc_spacewalk.subp.subp")
    def test_do_register(self, mock_subp):
        cc_spacewalk.do_register(**self.space_cfg["spacewalk"])
        mock_subp.assert_called_with(
            [
                "rhnreg_ks",
                "--serverUrl",
                "https://localhost/XMLRPC",
                "--profilename",
                "test",
                "--sslCACert",
                cc_spacewalk.def_ca_cert_path,
            ],
            capture=False,
        )


# vi: ts=4 expandtab
