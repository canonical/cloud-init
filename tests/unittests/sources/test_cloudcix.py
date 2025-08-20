# This file is part of cloud-init. See LICENSE file for license information.
import json
from unittest import mock

import pytest
import responses

from cloudinit import distros, sources
from cloudinit import url_helper as uh
from cloudinit.atomic_helper import json_dumps
from cloudinit.sources import DataSourceCloudCIX as ds_mod
from cloudinit.sources import InvalidMetaDataException

# pylint: disable=attribute-defined-outside-init


METADATA = {
    "instance_id": "12_34",
    "network": {
        "version": 2,
        "ethernets": {
            "eth0": {
                "set-name": "eth0",
                "match": {"macaddress": "ab:cd:ef:00:01:02"},
                "addresses": [
                    "10.0.0.2/24",
                    "192.168.0.2/24",
                ],
                "nameservers": {
                    "addresses": ["10.0.0.1"],
                    "search": ["cloudcix.com"],
                },
                "routes": [{"to": "default", "via": "10.0.0.1"}],
            },
            "eth1": {
                "set-name": "eth1",
                "match": {"macaddress": "12:34:56:ab:cd:ef"},
                "addresses": [
                    "10.10.10.2/24",
                ],
                "nameservers": {
                    "addresses": ["10.0.0.1"],
                    "search": ["cloudcix.com"],
                },
            },
        },
    },
}

# Expected network config resulting from METADATA
NETWORK_CONFIG = {
    "version": 2,
    "ethernets": {
        "eth0": {
            "set-name": "eth0",
            "addresses": [
                "10.0.0.2/24",
                "192.168.0.2/24",
            ],
            "match": {"macaddress": "ab:cd:ef:00:01:02"},
            "nameservers": {
                "addresses": ["10.0.0.1"],
                "search": [
                    "cloudcix.com",
                ],
            },
            "routes": [{"to": "default", "via": "10.0.0.1"}],
        },
        "eth1": {
            "set-name": "eth1",
            "addresses": [
                "10.10.10.2/24",
            ],
            "match": {"macaddress": "12:34:56:ab:cd:ef"},
            "nameservers": {
                "addresses": ["10.0.0.1"],
                "search": [
                    "cloudcix.com",
                ],
            },
        },
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


class TestDataSourceCloudCIX:
    """
    Test reading the meta-data
    """

    @pytest.fixture(autouse=True)
    def setup(self, mocker, tmpdir, paths):
        self.paths = paths
        self.datasource = self._get_ds()
        self.m_read_dmi_data = mocker.patch(
            "cloudinit.dmi.read_dmi_data",
            new_callable=mock.PropertyMock,
        )
        self.m_read_dmi_data.return_value = "CloudCIX"

        self._m_find_fallback_nic = mocker.patch(
            "cloudinit.net.find_fallback_nic",
            new_callable=mock.PropertyMock,
        )
        self._m_find_fallback_nic.return_value = "cixnic0"

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
        assert json_dumps(self.datasource.network_config) == json_dumps(
            NETWORK_CONFIG
        )

    @responses.activate
    def test_failing_imds_endpoints(self, mocker):
        sleep = mocker.patch("time.sleep")
        base_url = ds_mod.METADATA_URLS[0]
        # Make request before imds is set up
        with pytest.raises(
            sources.InvalidMetaDataException,
            match="Could not determine metadata URL",
        ):
            self.datasource.crawl_metadata_service()

        # Make imds respond to healthcheck but fail v1/metadata
        responses.add_callback(
            responses.GET,
            base_url,
            callback=MockImds.base_response,
        )
        version = ds_mod.METADATA_VERSION
        with pytest.raises(
            sources.InvalidMetaDataException,
            match="Could not determine metadata URL",
        ):
            self.datasource.crawl_metadata_service()

        # No sleep/retries when md_url returns 404. No viable IMDS found.
        assert 0 == sleep.call_count

        # Make imds serve metadata but ConnectionError on userdata
        responses.add_callback(
            responses.GET,
            uh.combine_url(base_url, f"v{version}", "metadata"),
            callback=MockImds.metadata_response,
        )
        pytest.raises(
            sources.InvalidMetaDataException,
            self.datasource.crawl_metadata_service,
        )
        # Sleep called number of default datasource configured "retries"
        assert [mock.call(5)] == sleep.call_args_list

        # Make IMDS serve userdata
        responses.add_callback(
            responses.GET,
            uh.combine_url(base_url, f"v{version}", "userdata"),
            callback=MockImds.userdata_response,
        )

        data = self.datasource.crawl_metadata_service()
        assert data == {
            "meta-data": METADATA,
            "user-data": USERDATA.encode("utf-8"),
        }

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

        with pytest.raises(
            InvalidMetaDataException,
            match="Invalid JSON at http://169.254.169.254/v1/metadata",
        ):
            ds_mod.read_metadata(
                versioned_url,
                self.datasource.get_url_params(),
            )

    @responses.activate
    def test_bad_response_code(self, mocker):
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
        sleep = mocker.patch("time.sleep")
        with pytest.raises(
            InvalidMetaDataException,
            match=f"Failed to fetch IMDS metadata: {versioned_url}",
        ):
            ds_mod.read_metadata(
                versioned_url, self.datasource.get_url_params()
            )
        assert [mock.call(5)] == sleep.call_args_list
