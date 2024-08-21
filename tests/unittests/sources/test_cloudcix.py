# This file is part of cloud-init. See LICENSE file for license information.
import json

import responses

from cloudinit import distros, helpers, sources
from cloudinit import url_helper as uh
from cloudinit.sources import DataSourceCloudCIX as ds_mod
from cloudinit.sources import InvalidMetaDataException
from tests.unittests.helpers import ResponsesTestCase

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

USERDATA = """#cloud-config
runcmd:
- [ echo Hello, World >> /etc/greeting ]
"""


class MockImds:
    @staticmethod
    def base_response(response):
        return 200, response.headers, "Metadata enabled"

    @staticmethod
    def metadata_response(response):
        return 200, response.headers, json.dumps(METADATA).encode()

    @staticmethod
    def userdata_response(response):
        return 200, response.headers, USERDATA.encode()


class MockEphemeralIPNetworkWithStateMsg:
    @property
    def state_msg(self):
        return "Mock state"


class TestDataSourceCloudCIX(ResponsesTestCase):
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
        self.add_patch(
            "cloudinit.net.find_fallback_nic",
            "_m_find_fallback_nic",
            return_value="cixnic0",
        )
        self.add_patch(
            "cloudinit.net.ephemeral.EphemeralIPNetwork.__enter__",
            "_m_EphemeralIPNetwork_enter",
            return_value=MockEphemeralIPNetworkWithStateMsg(),
        )
        self.add_patch(
            "cloudinit.net.ephemeral.EphemeralIPNetwork.__exit__",
            "_m_EphemeralIPNetwork_exit",
            return_value=MockEphemeralIPNetworkWithStateMsg(),
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
        self.assertTrue(ds_mod.is_platform_viable())

        self.m_read_dmi_data.return_value = "OnCloud9"
        self.assertFalse(self.datasource.ds_detect())
        self.assertFalse(ds_mod.is_platform_viable())

    def test_setting_config_options(self):
        cix_options = {
            "timeout": 1234,
            "retries": 5678,
            "sec_between_retries": 9012,
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
        self.assertEqual(
            new_ds.get_url_params().timeout_seconds, cix_options["timeout"]
        )
        self.assertEqual(
            new_ds.get_url_params().num_retries, cix_options["retries"]
        )
        self.assertEqual(
            new_ds.get_url_params().sec_between_retries,
            cix_options["sec_between_retries"],
        )

    def test_determine_md_url(self):
        base_url = ds_mod.METADATA_URLS[0]
        version = ds_mod.METADATA_VERSION
        self.responses.reset()
        self.responses.add_callback(
            responses.GET,
            base_url,
            callback=MockImds.base_response,
        )
        self.responses.add_callback(
            responses.GET,
            uh.combine_url(base_url, f"v{version}", "metadata"),
            callback=MockImds.metadata_response,
        )

        md_url = self._get_ds().determine_md_url()

        expected_url = uh.combine_url(
            ds_mod.METADATA_URLS[0],
            f"v{version}",
        )
        self.assertEqual(md_url, expected_url)

    def test_reading_metadata_on_cloudcix(self):
        base_url = ds_mod.METADATA_URLS[0]
        version = ds_mod.METADATA_VERSION
        # Set up mock endpoints
        self.responses.reset()
        self.responses.add_callback(
            responses.GET,
            base_url,
            callback=MockImds.base_response,
        )
        self.responses.add_callback(
            responses.GET,
            uh.combine_url(base_url, f"v{version}", "metadata"),
            callback=MockImds.metadata_response,
        )
        self.responses.add_callback(
            responses.GET,
            uh.combine_url(base_url, f"v{version}", "userdata"),
            callback=MockImds.userdata_response,
        )

        self.assertTrue(self.datasource.get_data())
        self.assertEqual(self.datasource.metadata, METADATA)
        self.assertEqual(self.datasource.userdata_raw, USERDATA)

    def test_failing_imds_endpoints(self):
        # Make request before imds is set up
        self.assertRaises(
            sources.InvalidMetaDataException,
            self.datasource.crawl_metadata_service,
        )

        # Make imds respond to healthcheck
        base_url = ds_mod.METADATA_URLS[0]
        self.responses.add_callback(
            responses.GET,
            base_url,
            callback=MockImds.base_response,
        )

        self.assertRaises(
            sources.InvalidMetaDataException,
            self.datasource.crawl_metadata_service,
        )

        # Make imds serve metadata
        version = ds_mod.METADATA_VERSION
        self.responses.add_callback(
            responses.GET,
            uh.combine_url(base_url, f"v{version}", "metadata"),
            callback=MockImds.metadata_response,
        )

        self.assertRaises(
            sources.InvalidMetaDataException,
            self.datasource.crawl_metadata_service,
        )

        # Make imds serve userdata
        self.responses.add_callback(
            responses.GET,
            uh.combine_url(base_url, f"v{version}", "userdata"),
            callback=MockImds.userdata_response,
        )

        data = self.datasource.crawl_metadata_service()
        self.assertNotEqual(data, dict())

    def test_read_malformed_metadata(self):
        def bad_response(response):
            return 200, response.headers, json.dumps(METADATA)[:-2]

        version = ds_mod.METADATA_VERSION
        base_url = ds_mod.METADATA_URLS[0]
        versioned_url = uh.combine_url(base_url, f"v{version}")

        # Malformed metadata
        self.responses.add_callback(
            responses.GET,
            uh.combine_url(versioned_url, "metadata"),
            callback=bad_response,
        )
        self.responses.add_callback(
            responses.GET,
            uh.combine_url(versioned_url, "userdata"),
            callback=MockImds.userdata_response,
        )

        self.assertRaises(
            InvalidMetaDataException,
            ds_mod.read_metadata,
            versioned_url,
            self.datasource.get_url_params(),
        )

    def test_bad_response_code(self):
        def bad_response(response):
            return 404, response.headers, ""

        version = ds_mod.METADATA_VERSION
        base_url = ds_mod.METADATA_URLS[0]
        versioned_url = uh.combine_url(base_url, f"v{version}")

        self.responses.add_callback(
            responses.GET,
            uh.combine_url(versioned_url, "metadata"),
            callback=bad_response,
        )

        self.assertRaises(
            InvalidMetaDataException,
            ds_mod.read_metadata,
            versioned_url,
            self.datasource.get_url_params(),
        )
