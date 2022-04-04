# This file is part of cloud-init. See LICENSE file for license information.
import json

from cloudinit import distros, helpers, sources, url_helper
from cloudinit.sources import DataSourceCloudCIX as ds_mod
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
        return ds_mod.DataSourceCloudCIX(
            sys_cfg={}, distro=distro, paths=self.paths
        )

    def test_identifying_cloudcix(self):
        self.assertTrue(self.datasource.is_running_in_cloudcix())

        self.m_read_dmi_data.return_value = "OnCloud9"
        self.assertFalse(self.datasource.is_running_in_cloudcix())

    @mock.patch("cloudinit.url_helper.readurl")
    def test_reading_metadata_on_cloudcix(self, m_readurl):
        def url_responses(url, **params):
            if url.endswith("metadata"):
                return url_helper.StringResponse(json.dumps(METADATA))
            elif url.endswith("userdata"):
                return url_helper.StringResponse(USERDATA)
            return None

        m_readurl.side_effect = url_responses

        self.assertTrue(self.datasource.get_data())
        self.assertEqual(self.datasource.metadata, METADATA)
        self.assertEqual(self.datasource.userdata_raw, USERDATA.decode())

    def test_setting_config_options(self):
        cix_options = {
            "timeout": 1234,
            "retries": 5678,
        }
        sys_cfg = {
            "datasource": {
                "CloudCIX": cix_options,
            }
        }

        # Instantiate a new datasource
        distro_cls = distros.fetch("ubuntu")
        distro = distro_cls("ubuntu", cfg={}, paths=self.paths)
        new_ds = ds_mod.DataSourceCloudCIX(
            sys_cfg=sys_cfg, distro=distro, paths=self.paths
        )
        self.assertEqual(new_ds.url_timeout, cix_options["timeout"])
        self.assertEqual(new_ds.url_retries, cix_options["retries"])

    @mock.patch("cloudinit.url_helper.readurl")
    def test_read_metadata_cannot_contact_imds(self, m_readurl):
        def url_responses(url, **params):
            raise url_helper.UrlError("No route")

        m_readurl.side_effect = url_responses

        self.assertFalse(self.datasource.get_data())
        self.assertFalse(getattr(self.datasource, "metadata"))
        self.assertFalse(getattr(self.datasource, "userdata_raw"))

        with self.assertRaises(sources.InvalidMetaDataException):
            ds_mod.read_metadata(
                self.datasource.base_url, self.datasource.get_url_params()
            )

    @mock.patch("cloudinit.url_helper.readurl")
    def test_read_metadata_gets_bad_response(self, m_readurl):
        def url_responses(url, **params):
            return url_helper.StringResponse("", code=403)

        m_readurl.side_effect = url_responses

        with self.assertRaises(sources.InvalidMetaDataException):
            ds_mod.read_metadata(
                self.datasource.base_url, self.datasource.get_url_params()
            )

    @mock.patch("cloudinit.url_helper.readurl")
    def test_read_metadata_gets_malformed_response(self, m_readurl):
        def url_responses(url, **params):
            bad_json = json.dumps(METADATA)[:-2]
            return url_helper.StringResponse(bad_json, code=200)

        m_readurl.side_effect = url_responses

        with self.assertRaises(sources.InvalidMetaDataException):
            ds_mod.read_metadata(
                self.datasource.base_url, self.datasource.get_url_params()
            )

    @mock.patch("cloudinit.sources.DataSourceCloudCIX.read_metadata")
    def test_not_on_cloudcix_returns_false(self, m_read_metadata):
        self.m_read_dmi_data.return_value = "WrongCloud"
        self.assertFalse(self.datasource.get_data())
        m_read_metadata.assert_not_called()
