# This file is part of cloud-init. See LICENSE file for license information.
import json
from unittest.mock import PropertyMock

import pytest
import responses

from cloudinit import distros, helpers, sources
from cloudinit import url_helper as uh
from cloudinit.sources import DataSourceCloudCIX as ds_mod
from cloudinit.sources import InvalidMetaDataException

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


class TestDataSourceCloudCIX:
    """
    Test reading the meta-data
    """

    allowed_subp = True

    @pytest.fixture(autouse=True)
    def setup(self, mocker, tmp_path):
        self.paths = helpers.Paths({"run_dir": tmp_path})
        self.datasource = self._get_ds()
        self.m_read_dmi_data = mocker.patch(
            "cloudinit.dmi.read_dmi_data",
            new_callable=PropertyMock,
        )
        self.m_read_dmi_data.return_value = "CloudCIX"

        self._m_find_fallback_nic = mocker.patch(
            "cloudinit.net.find_fallback_nic",
            new_callable=PropertyMock,
        )
        self._m_find_fallback_nic.return_value = "cixnic0"
        self._m_EphemeralIPNetwork_enter = mocker.patch(
            "cloudinit.net.ephemeral.EphemeralIPNetwork.__enter__",
            new_callable=PropertyMock,
        )
        self._m_EphemeralIPNetwork_enter.return_value = (
            MockEphemeralIPNetworkWithStateMsg()
        )
        self._m_EphemeralIPNetwork_exit = mocker.patch(
            "cloudinit.net.ephemeral.EphemeralIPNetwork.__exit__",
            new_callable=PropertyMock,
        )
        self._m_EphemeralIPNetwork_exit.return_value = (
            MockEphemeralIPNetworkWithStateMsg()
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

    @responses.activate
    def test_identifying_cloudcix(self):
        assert self.datasource.ds_detect()
        assert ds_mod.is_platform_viable()

        self.m_read_dmi_data.return_value = "OnCloud9"
        assert not self.datasource.ds_detect()
        assert not ds_mod.is_platform_viable()

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
        assert (
            new_ds.get_url_params().timeout_seconds == cix_options["timeout"]
        )
        assert new_ds.get_url_params().num_retries == cix_options["retries"]
        assert (
            new_ds.get_url_params().sec_between_retries
            == cix_options["sec_between_retries"]
        )

    @responses.activate
    def test_determine_md_url(self):
        base_url = ds_mod.METADATA_URLS[0]
        version = ds_mod.METADATA_VERSION
        responses.reset()
        responses.add_callback(
            responses.GET,
            base_url,
            callback=MockImds.base_response,
        )
        responses.add_callback(
            responses.GET,
            uh.combine_url(base_url, f"v{version}", "metadata"),
            callback=MockImds.metadata_response,
        )

        md_url = self._get_ds().determine_md_url()

        expected_url = uh.combine_url(
            ds_mod.METADATA_URLS[0],
            f"v{version}",
        )
        assert md_url == expected_url

    @responses.activate
    def test_reading_metadata_on_cloudcix(self):
        base_url = ds_mod.METADATA_URLS[0]
        version = ds_mod.METADATA_VERSION
        # Set up mock endpoints
        responses.reset()
        responses.add_callback(
            responses.GET,
            base_url,
            callback=MockImds.base_response,
        )
        responses.add_callback(
            responses.GET,
            uh.combine_url(base_url, f"v{version}", "metadata"),
            callback=MockImds.metadata_response,
        )
        responses.add_callback(
            responses.GET,
            uh.combine_url(base_url, f"v{version}", "userdata"),
            callback=MockImds.userdata_response,
        )

        assert self.datasource.get_data()
        assert self.datasource.metadata == METADATA
        assert self.datasource.userdata_raw == USERDATA

    @responses.activate
    def test_failing_imds_endpoints(self):
        # Make request before imds is set up
        pytest.raises(
            sources.InvalidMetaDataException,
            self.datasource.crawl_metadata_service,
        )

        # Make imds respond to healthcheck
        base_url = ds_mod.METADATA_URLS[0]
        responses.add_callback(
            responses.GET,
            base_url,
            callback=MockImds.base_response,
        )

        pytest.raises(
            sources.InvalidMetaDataException,
            self.datasource.crawl_metadata_service,
        )

        # Make imds serve metadata
        version = ds_mod.METADATA_VERSION
        responses.add_callback(
            responses.GET,
            uh.combine_url(base_url, f"v{version}", "metadata"),
            callback=MockImds.metadata_response,
        )

        pytest.raises(
            sources.InvalidMetaDataException,
            self.datasource.crawl_metadata_service,
        )

        # Make imds serve userdata
        responses.add_callback(
            responses.GET,
            uh.combine_url(base_url, f"v{version}", "userdata"),
            callback=MockImds.userdata_response,
        )

        data = self.datasource.crawl_metadata_service()
        assert data != dict()

    @responses.activate
    def test_read_malformed_metadata(self):
        def bad_response(response):
            return 200, response.headers, json.dumps(METADATA)[:-2]

        version = ds_mod.METADATA_VERSION
        base_url = ds_mod.METADATA_URLS[0]
        versioned_url = uh.combine_url(base_url, f"v{version}")

        # Malformed metadata
        responses.add_callback(
            responses.GET,
            uh.combine_url(versioned_url, "metadata"),
            callback=bad_response,
        )
        responses.add_callback(
            responses.GET,
            uh.combine_url(versioned_url, "userdata"),
            callback=MockImds.userdata_response,
        )

        pytest.raises(
            InvalidMetaDataException,
            ds_mod.read_metadata,
            versioned_url,
            self.datasource.get_url_params(),
        )

    @responses.activate
    def test_bad_response_code(self):
        def bad_response(response):
            return 404, response.headers, ""

        version = ds_mod.METADATA_VERSION
        base_url = ds_mod.METADATA_URLS[0]
        versioned_url = uh.combine_url(base_url, f"v{version}")

        responses.add_callback(
            responses.GET,
            uh.combine_url(versioned_url, "metadata"),
            callback=bad_response,
        )

        pytest.raises(
            InvalidMetaDataException,
            ds_mod.read_metadata,
            versioned_url,
            self.datasource.get_url_params(),
        )
