# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import helpers, settings, util
from cloudinit.sources import DataSourceNWCS
from tests.unittests.helpers import CiTestCase, mock

METADATA = util.load_yaml(
    """
instance-id: test
machine_type: b1.centi
hostname: debian
network:
  version: 1
  config:
  - type: physical
    name: eth0
    mac_address: 96:00:00:08:19:da
    subnets:
    - type: dhcp
public-keys:
- ssh-rsa \
  AAAAC3Nzac1lZdI1NTE5AaaAIaFrcac0yVITsmRrmueq6MD0qYNKlEvW8O1Ib4nkhmWh
userdata: "test"
vendordata: "test"
"""
)


class TestDataSourceNWCS(CiTestCase):
    """
    Test reading the metadata
    """

    def setUp(self):
        super(TestDataSourceNWCS, self).setUp()
        self.tmp = self.tmp_dir()

    def get_ds(self):
        distro = mock.MagicMock()
        distro.get_tmp_exec_path = self.tmp_dir
        ds = DataSourceNWCS.DataSourceNWCS(
            settings.CFG_BUILTIN, distro, helpers.Paths({"run_dir": self.tmp})
        )
        return ds

    @mock.patch("cloudinit.net.dhcp.maybe_perform_dhcp_discovery")
    @mock.patch("cloudinit.sources.DataSourceNWCS.EphemeralDHCPv4")
    @mock.patch("cloudinit.net.find_fallback_nic")
    @mock.patch("cloudinit.sources.DataSourceNWCS.read_metadata")
    @mock.patch("cloudinit.sources.DataSourceNWCS.DataSourceNWCS.ds_detect")
    def test_read_data(
        self,
        m_ds_detect,
        m_readmd,
        m_fallback_nic,
        m_net,
        m_dhcp,
    ):
        m_ds_detect.return_value = True
        m_readmd.return_value = METADATA.copy()
        m_fallback_nic.return_value = "eth0"
        m_dhcp.return_value = [
            {
                "interface": "eth0",
                "fixed-address": "192.168.0.2",
                "routers": "192.168.0.1",
                "subnet-mask": "255.255.255.0",
                "broadcast-address": "192.168.0.255",
            }
        ]

        ds = self.get_ds()
        ret = ds.get_data()
        self.assertTrue(ret)

        m_net.assert_called_once_with(
            ds.distro,
            iface="eth0",
            connectivity_urls_data=[
                {"url": "http://169.254.169.254/api/v1/metadata/instance-id"}
            ],
        )

        self.assertTrue(m_readmd.called)

        self.assertEqual(METADATA.get("hostname"), ds.get_hostname().hostname)

        self.assertEqual(METADATA.get("public-keys"), ds.get_public_ssh_keys())

        self.assertIsInstance(ds.get_public_ssh_keys(), list)
        self.assertEqual(ds.get_userdata_raw(), METADATA.get("userdata"))
        self.assertEqual(ds.get_vendordata_raw(), METADATA.get("vendordata"))

    @mock.patch("cloudinit.sources.DataSourceNWCS.read_metadata")
    @mock.patch("cloudinit.net.find_fallback_nic")
    @mock.patch("cloudinit.sources.DataSourceNWCS.DataSourceNWCS.ds_detect")
    def test_not_on_nwcs_returns_false(
        self, m_ds_detect, m_find_fallback, m_read_md
    ):
        """If 'ds_detect' returns False,
        return False from get_data."""
        m_ds_detect.return_value = False
        ds = self.get_ds()
        ret = ds.get_data()

        self.assertFalse(ret)
        # These are a white box attempt to ensure it did not search.
        m_find_fallback.assert_not_called()
        m_read_md.assert_not_called()

    @mock.patch("cloudinit.sources.DataSourceNWCS.get_interface_name")
    def test_get_interface_name(self, m_ifname):
        m_ifname.return_value = "eth0"

        self.assertEqual(
            m_ifname.return_value, METADATA["network"]["config"][0]["name"]
        )
