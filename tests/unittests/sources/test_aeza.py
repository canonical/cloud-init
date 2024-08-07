# Copyright (C) 2024 Aeza.net.
#
# Author: Egor Ternovoy <cofob@riseup.net>
#
# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import helpers, settings, util
from cloudinit.sources import DataSourceAeza
from tests.unittests.helpers import CiTestCase, mock

METADATA = util.load_yaml(
    """---
hostname: cloudinit-test.aeza.network
instance-id: ic0859a7003d840d093756680cb45d51f
public-keys:
- ssh-ed25519 AAAA...4nkhmWh example-key
"""
)

VENDORDATA = None

USERDATA = b"""#cloud-config
runcmd:
- [touch, /root/cloud-init-worked]
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
        ds = DataSourceAeza.DataSourceAeza(
            settings.CFG_BUILTIN,
            distro,
            helpers.Paths({"run_dir": self.tmp}),
        )
        return ds

    @mock.patch("cloudinit.util.read_seeded")
    @mock.patch("cloudinit.sources.DataSourceAeza.DataSourceAeza.ds_detect")
    def test_read_data(
        self,
        m_ds_detect,
        m_read_seeded,
    ):
        m_ds_detect.return_value = True
        m_read_seeded.return_value = (METADATA, USERDATA, VENDORDATA)

        with self.allow_subp(True):
            ds = self.get_ds()
        ret = ds.get_data()
        self.assertTrue(ret)

        self.assertTrue(m_read_seeded.called)
        self.assertEqual(ds.get_public_ssh_keys(), METADATA.get("public-keys"))
        self.assertIsInstance(ds.get_public_ssh_keys(), list)
        self.assertEqual(ds.get_userdata_raw(), USERDATA)
        self.assertEqual(ds.get_vendordata_raw(), VENDORDATA)
