# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import distros, helpers, util
from cloudinit.sources.DataSourceCloudCIX import DataSourceCloudCIX
from tests.unittests.helpers import CiTestCase, mock

METADATA = util.load_yaml(
    """
    instance-id: 123456
    network-config:
      config:
      - name: eth0
        subnets:
        - dns_nameservers:
          - 213.133.99.99
          - 213.133.100.100
          - 213.133.98.98
          ipv4: true
          type: dhcp
        type: physical
      version: 1
"""
)

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
        "cloudinit.sources.DataSourceCloudCIX.DataSourceCloudCIX.read_url"
    )
    def test_reading_data(self, m_read_url):
        def m_responses(url):
            if url.endswith("metadata"):
                return METADATA
            elif url.endswith("userdata"):
                return USERDATA

        m_read_url.side_effect = m_responses

        self.datasource.get_data()
        self.assertEqual(self.datasource.metadata, METADATA)
        self.assertEqual(self.datasource.userdata_raw, USERDATA)
