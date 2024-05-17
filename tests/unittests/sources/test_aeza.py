# Copyright (C) 2024 Aeza.net.
#
# Author: Egor Ternovoy <cofob@riseup.net>
#
# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import helpers, settings, util
from cloudinit.sources import DataSourceAeza
from tests.unittests.helpers import CiTestCase, mock

METADATA = util.load_json(
    """
{
  "hostname": "cloudinit-test.aeza.network",
  "instance-id": "ic0859a7003d840d093756680cb45d51f",
  "public-keys": [
    "ssh-ed25519 AAAAC3Nzac1lZdI1NTE5AaaAIaFrcac0yVITsmRrmueq6MD0qYNKlEvW8O1Ib4nkhmWh example-key"
  ]
}
"""
)

USERDATA = b"""#cloud-config
runcmd:
- [touch, /root/cloud-init-worked ]
"""

VENDORDATA = "test"


class TestDataSourceAeza(CiTestCase):
    """
    Test reading the meta-data
    """

    def setUp(self):
        super(TestDataSourceAeza, self).setUp()
        self.tmp = self.tmp_dir()

    def get_ds(self):
        distro = mock.MagicMock()
        distro.get_tmp_exec_path = self.tmp_dir
        ds = DataSourceAeza.DataSourceAeza(
            settings.CFG_BUILTIN, distro, helpers.Paths({"run_dir": self.tmp})
        )
        return ds

    @mock.patch("cloudinit.sources.helpers.aeza.read_metadata")
    @mock.patch("cloudinit.sources.helpers.aeza.read_userdata")
    @mock.patch("cloudinit.sources.helpers.aeza.read_vendordata")
    def test_read_data(
        self,
        m_readvd,
        m_readud,
        m_readmd,
    ):
        m_readmd.return_value = METADATA.copy()
        m_readud.return_value = USERDATA
        m_readvd.return_value = VENDORDATA

        ds = self.get_ds()
        ret = ds.get_data()
        self.assertTrue(ret)

        self.assertTrue(m_readmd.called)
        self.assertEqual(METADATA.get("hostname"), ds.get_hostname().hostname)
        self.assertEqual(METADATA.get("public-keys"), ds.get_public_ssh_keys())
        self.assertIsInstance(ds.get_public_ssh_keys(), list)

        self.assertTrue(m_readud.called)
        self.assertEqual(ds.get_userdata_raw(), USERDATA)

        self.assertTrue(m_readvd.called)
        self.assertEqual(ds.get_vendordata_raw(), VENDORDATA)

