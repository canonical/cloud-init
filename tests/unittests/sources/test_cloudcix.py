# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import distros, helpers
from cloudinit.sources.DataSourceCloudCIX import DataSourceCloudCIX
from tests.unittests.helpers import CiTestCase, mock

METADATA = {
    "instance_id": "12_34",
    "ip_addresses": [
        {
            "private_ip": "10.0.0.2",
            "public_ip": "185.1.2.3",
            "subnet": "10.0.0.1/24",
        }
    ],
}

USERDATA = b"""#cloud-config
runcmd:
- [ echo Hello, World >> /etc/greeting ]
"""


class TestDataSourceCloudCIX(CiTestCase):
    """
    Test reading the meta-data
    """

    def setUp(self):
        super(TestDataSourceCloudCIX, self).setUp()
        self.paths = helpers.Paths({"run_dir": self.tmp_dir()})
        self.datasource = self._get_ds()
        self.add_patch(
            "cloudinit.dmi.read_dmi_data",
            "m_read_dmi_data",
            return_value="CloudCIX",
        )

    def _get_ds(self):
        distro_cls = distros.fetch("ubuntu")
        distro = distro_cls("ubuntu", cfg={}, paths=self.paths)
        return DataSourceCloudCIX(sys_cfg={}, distro=distro, paths=self.paths)

    def test_identifying_cloudcix(self):
        self.assertTrue(self.datasource.is_running_in_cloudcix())

        self.m_read_dmi_data.return_value = "OnCloud9"
        self.assertFalse(self.datasource.is_running_in_cloudcix())

    @mock.patch(
        "cloudinit.sources.DataSourceCloudCIX.DataSourceCloudCIX.read_metadata"
    )
    @mock.patch(
        "cloudinit.sources.DataSourceCloudCIX.DataSourceCloudCIX.read_userdata"
    )
    def test_reading_metadata_on_cloudcix(
        self, m_read_userdata, m_read_metadata
    ):
        m_read_userdata.return_value = USERDATA
        m_read_metadata.return_value = METADATA

        self.datasource.get_data()
        self.assertEqual(self.datasource.metadata, METADATA)
        self.assertEqual(self.datasource.userdata_raw, USERDATA)

    @mock.patch(
        "cloudinit.sources.DataSourceCloudCIX.DataSourceCloudCIX.read_metadata"
    )
    def test_not_on_cloudcix_returns_false(self, m_read_metadata):
        self.m_read_dmi_data.return_value = "WrongCloud"
        self.assertFalse(self.datasource.get_data())
        m_read_metadata.assert_not_called()
