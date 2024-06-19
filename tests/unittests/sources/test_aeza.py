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
        ds = DataSourceAeza.DataSourceAeza(settings.CFG_BUILTIN, distro, helpers.Paths({"run_dir": self.tmp}))
        return ds

    @mock.patch("cloudinit.sources.DataSourceAeza.read_metadata")
    @mock.patch("cloudinit.sources.DataSourceAeza.read_data")
    @mock.patch("cloudinit.sources.DataSourceAeza.DataSourceAeza.ds_detect")
    def test_read_data(
        self,
        m_ds_detect,
        m_read_data,
        m_read_metadata,
    ):
        m_read_metadata.return_value = METADATA.copy()
        m_read_data.return_value = USERDATA
        m_ds_detect.return_value = True

        ds = self.get_ds()
        with self.allow_subp(True):
            ret = ds.get_data()
        self.assertTrue(ret)

        self.assertTrue(m_read_metadata.called)
        self.assertEqual(METADATA.get("public-keys"), ds.get_public_ssh_keys())
        self.assertIsInstance(ds.get_public_ssh_keys(), list)

        self.assertTrue(m_read_data.called)
        self.assertEqual(ds.get_userdata_raw(), USERDATA)
