# This file is part of cloud-init. See LICENSE file for license information.
import json

from cloudinit import distros, helpers, sources, url_helper as uh
from cloudinit.sources import (
    DataSourceCloudCIX as ds_mod,
    InvalidMetaDataException,
)
from tests.unittests.helpers import CiTestCase, mock

METADATA = {
    "instance_id": "12_34",
    "network": {
        "interfaces": [
            {
                "mac_address": "ab:cd:ef:00:01:02",
                "addresses": [
                    "10.0.0.2/24",
                    "192.168.0.2/24",
                ],
            },
            {
                "mac_address": "12:34:56:ab:cd:ef",
                "addresses": [
                    "10.10.10.2/24",
                ],
            },
        ]
    },
}

USERDATA = b"""#cloud-config
runcmd:
- [ echo Hello, World >> /etc/greeting ]
"""


def mock_imds(base_url, version):
    # Create a function that mocks responses from a metadata server
    version_str = f"v{version}"

    def func(url, **urlparams):

        if url == base_url:
            return uh.StringResponse("Metadata enabled")

        md_endpoint = uh.combine_url(base_url, version_str, "metadata")
        if url == md_endpoint:
            return uh.StringResponse(json.dumps(METADATA).encode())

        userdata_endpoint = uh.combine_url(base_url, version_str, "userdata")
        if url == userdata_endpoint:
            return uh.StringResponse(USERDATA)

        return uh.StringResponse("Not Found", code=404)

    return func


class TestDataSourceCloudCIX(CiTestCase):
    """
    Test reading the meta-data
    """

    def setUp(self):
        super(TestDataSourceCloudCIX, self).setUp()
        self.paths = helpers.Paths({"run_dir": self.tmp_dir()})
        self.datasource = self._get_ds()
        self.allowed_subp = True
        self.add_patch(
            "cloudinit.dmi.read_dmi_data",
            "m_read_dmi_data",
            return_value="CloudCIX",
        )

    def _get_ds(self):
        distro_cls = distros.fetch("ubuntu")
        distro = distro_cls("ubuntu", cfg={}, paths=self.paths)
        return ds_mod.DataSourceCloudCIX(
            sys_cfg={
                "datasource": {
                    "CloudCIX": {
                        "retries": 1,
                        "timeout": 0,
                        "wait": 0,
                    },
                }
            },
            distro=distro,
            paths=self.paths,
        )

    def test_identifying_cloudcix(self):
        self.assertTrue(self.datasource.ds_detect())

        self.m_read_dmi_data.return_value = "OnCloud9"
        self.assertFalse(self.datasource.ds_detect())

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
    def test_determine_md_url(self, m_readurl):
        base_url = ds_mod.METADATA_URLS[0]
        version = ds_mod.METADATA_VERSION
        m_readurl.side_effect = mock_imds(base_url, version)

        md_url = self._get_ds().determine_md_url()

        expected_url = uh.combine_url(
            ds_mod.METADATA_URLS[0],
            f"v{version}",
        )
        self.assertEqual(md_url, expected_url)

    @mock.patch("cloudinit.url_helper.readurl")
    def test_reading_metadata_on_cloudcix(self, m_readurl):
        base_url = ds_mod.METADATA_URLS[0]
        version = ds_mod.METADATA_VERSION
        m_readurl.side_effect = mock_imds(base_url, version)

        self.assertTrue(self.datasource.get_data())
        self.assertEqual(self.datasource.metadata, METADATA)
        self.assertEqual(self.datasource.userdata_raw, USERDATA.decode())

    @mock.patch("cloudinit.url_helper.readurl")
    def test_failing_imds_endpoints(self, m_readurl):
        # Set up an empty imds
        endpoints = dict()

        def faulty_imds(url, **urlparams):
            if url in endpoints:
                return endpoints[url]
            return uh.StringResponse(b"Not Found", code=404)

        m_readurl.side_effect = faulty_imds

        self.assertRaises(
            sources.InvalidMetaDataException,
            self.datasource.crawl_metadata_service,
        )

        # Make imds respond to healthcheck
        base_url = ds_mod.METADATA_URLS[0]
        endpoints[base_url] = uh.StringResponse("Metadata enabled")

        self.assertRaises(
            sources.InvalidMetaDataException,
            self.datasource.crawl_metadata_service,
        )

        # Make imds serve metadata
        version_str = f"v{ds_mod.METADATA_VERSION}"
        md_url = uh.combine_url(base_url, version_str, "metadata")
        endpoints[md_url] = uh.StringResponse(json.dumps(METADATA).encode())

        self.assertRaises(
            sources.InvalidMetaDataException,
            self.datasource.crawl_metadata_service,
        )

        # Make imds serve userdata
        ud_url = uh.combine_url(base_url, version_str, "userdata")
        endpoints[ud_url] = uh.StringResponse(USERDATA)

        data = self.datasource.crawl_metadata_service()
        self.assertNotEqual(data, dict())

    @mock.patch("cloudinit.url_helper.readurl")
    def test_read_malformed_metadata(self, m_readurl):
        def url_responses(url, **params):
            bad_json = json.dumps(METADATA)[:-2]
            return uh.StringResponse(bad_json.encode(), code=200)

        m_readurl.side_effect = url_responses

        self.assertRaises(
            InvalidMetaDataException,
            ds_mod.read_metadata,
            ds_mod.METADATA_URLS[0],
            self.datasource.get_url_params(),
        )
