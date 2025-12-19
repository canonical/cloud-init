# This file is part of cloud-init. See LICENSE file for license information.
# pylint: disable=attribute-defined-outside-init

import json
import socket
from urllib.parse import SplitResult, urlsplit

import pytest
import requests
import responses
from requests.exceptions import ConnectionError, ConnectTimeout

from cloudinit import settings
from cloudinit.distros import ubuntu
from cloudinit.sources import DataSourceScaleway
from tests.unittests.helpers import mock, responses_assert_call_count


class DataResponses:
    """
    Possible responses of the API endpoint
    169.254.42.42/user_data/cloud-init and
    169.254.42.42/vendor_data/cloud-init.
    """

    FAKE_USER_DATA = '#!/bin/bash\necho "user-data"'

    @staticmethod
    def rate_limited(request):
        return 429, request.headers, ""

    @staticmethod
    def api_error(request):
        return 500, request.headers, ""

    @classmethod
    def get_ok(cls, request):
        return 200, request.headers, cls.FAKE_USER_DATA

    @staticmethod
    def empty(request):
        """
        No user data for this server.
        """
        return 404, request.headers, ""


class MetadataResponses:
    """
    Possible responses of the metadata API.
    """

    FAKE_METADATA = {
        "id": "00000000-0000-0000-0000-000000000000",
        "hostname": "scaleway.host",
        "net_in_use": "ipv4",
        "tags": [
            "AUTHORIZED_KEY=ssh-rsa_AAAAB3NzaC1yc2EAAAADAQABDDDDD",
        ],
        "ssh_public_keys": [
            {
                "key": "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABA",
                "fingerprint": "2048 06:ae:...  login (RSA)",
            },
            {
                "key": "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABCCCCC",
                "fingerprint": "2048 06:ff:...  login2 (RSA)",
            },
        ],
        "zone": "fr-par-1",
    }

    @classmethod
    def get_ok(cls, response):
        return 200, response.headers, json.dumps(cls.FAKE_METADATA)


class TestOnScaleway:
    def install_mocks(self, fake_dmi, fake_file_exists, fake_cmdline):
        mock, faked = fake_dmi
        mock.return_value = "Scaleway" if faked else "Whatever"

        mock, faked = fake_file_exists
        mock.return_value = faked

        mock, faked = fake_cmdline
        mock.return_value = (
            "initrd=initrd showopts scaleway nousb"
            if faked
            else "BOOT_IMAGE=/vmlinuz-3.11.0-26-generic"
        )

    @mock.patch("cloudinit.util.get_cmdline")
    @mock.patch("os.path.exists")
    @mock.patch("cloudinit.dmi.read_dmi_data")
    def test_not_ds_detect(
        self, m_read_dmi_data, m_file_exists, m_get_cmdline, paths
    ):
        self.install_mocks(
            fake_dmi=(m_read_dmi_data, False),
            fake_file_exists=(m_file_exists, False),
            fake_cmdline=(m_get_cmdline, False),
        )
        assert False is DataSourceScaleway.DataSourceScaleway.ds_detect()

        # When not on Scaleway, get_data() returns False.
        datasource = DataSourceScaleway.DataSourceScaleway(
            settings.CFG_BUILTIN, None, paths
        )
        assert False is datasource.get_data()

    @mock.patch("cloudinit.util.get_cmdline")
    @mock.patch("os.path.exists")
    @mock.patch("cloudinit.dmi.read_dmi_data")
    def test_ds_detect_dmi(
        self, m_read_dmi_data, m_file_exists, m_get_cmdline
    ):
        """
        dmidecode returns "Scaleway".
        """
        # dmidecode returns "Scaleway"
        self.install_mocks(
            fake_dmi=(m_read_dmi_data, True),
            fake_file_exists=(m_file_exists, False),
            fake_cmdline=(m_get_cmdline, False),
        )
        assert True is DataSourceScaleway.DataSourceScaleway.ds_detect()

    @mock.patch("cloudinit.util.get_cmdline")
    @mock.patch("os.path.exists")
    @mock.patch("cloudinit.dmi.read_dmi_data")
    def test_ds_detect_var_run_scaleway(
        self, m_read_dmi_data, m_file_exists, m_get_cmdline
    ):
        """
        /var/run/scaleway exists.
        """
        self.install_mocks(
            fake_dmi=(m_read_dmi_data, False),
            fake_file_exists=(m_file_exists, True),
            fake_cmdline=(m_get_cmdline, False),
        )
        assert True is DataSourceScaleway.DataSourceScaleway.ds_detect()

    @mock.patch("cloudinit.util.get_cmdline")
    @mock.patch("os.path.exists")
    @mock.patch("cloudinit.dmi.read_dmi_data")
    def test_ds_detect_cmdline(
        self, m_read_dmi_data, m_file_exists, m_get_cmdline
    ):
        """
        "scaleway" in /proc/cmdline.
        """
        self.install_mocks(
            fake_dmi=(m_read_dmi_data, False),
            fake_file_exists=(m_file_exists, False),
            fake_cmdline=(m_get_cmdline, True),
        )
        assert True is DataSourceScaleway.DataSourceScaleway.ds_detect()


def get_source_address_adapter(*args, **kwargs):
    """
    Scaleway user/vendor data API requires to be called with a privileged port.

    If the unittests are run as non-root, the user doesn't have the permission
    to bind on ports below 1024.

    This function removes the bind on a privileged address, since anyway the
    HTTP call is mocked by responses.
    """
    kwargs.pop("source_address")
    return requests.adapters.HTTPAdapter(*args, **kwargs)


def _fix_mocking_url(url: str) -> str:
    # Workaround https://github.com/getsentry/responses/pull/166
    # This function can be removed when Bionic is EOL
    split_result = urlsplit(url)
    return SplitResult(
        scheme=split_result.scheme,
        netloc=split_result.netloc,
        path=split_result.path,
        query="",  # ignore
        fragment=split_result.fragment,
    ).geturl()


class TestDataSourceScaleway:
    @pytest.fixture(autouse=True)
    def fixtures(self, mocker, paths, tmp_path):
        distro = ubuntu.Distro("", {}, {})
        distro.get_tmp_exec_path = str(tmp_path)
        self.datasource = DataSourceScaleway.DataSourceScaleway(
            settings.CFG_BUILTIN, distro, paths
        )

        self.base_urls = DataSourceScaleway.DS_BASE_URLS
        for url in self.base_urls:
            # Make sure that API answers on the first try.
            # The trailing / at the end of the URL is needed to
            # workaround a bug in responses 3.6 which does not match
            # the URL otherwise.
            responses.add_callback(
                responses.GET,
                f"{url}/",
                callback=MetadataResponses.get_ok,
            )
            # Define the metadata URLS

        mocker.patch(
            "cloudinit.sources.DataSourceScaleway.DataSourceScaleway.ds_detect",
            return_value=True,
        )
        mocker.patch(
            "cloudinit.distros.net.find_fallback_nic",
            return_value="scalewaynic0",
        )

    @responses.activate
    def test_set_metadata_url_ipv4_ok(self):

        self.datasource._set_metadata_url([self.base_urls[0]])

        assert self.base_urls[0] in self.datasource.metadata_url

    @responses.activate
    def test_set_metadata_url_ipv6_ok(self):

        self.datasource._set_metadata_url([self.base_urls[1]])

        assert self.base_urls[1] in self.datasource.metadata_url

    @responses.activate
    @mock.patch(
        "cloudinit.sources.DataSourceScaleway.DataSourceScaleway"
        ".override_ds_detect"
    )
    @mock.patch("cloudinit.sources.DataSourceScaleway.EphemeralDHCPv4")
    def test_ipv4_metadata_ok(self, dhcpv4, ds_detect):
        """
        get_data() returns metadata, user data and vendor data from IPv4.
        """
        ds_detect.return_value = True

        self.datasource._set_metadata_url([self.base_urls[0]])

        responses.reset()
        responses.add_callback(
            responses.GET,
            f"{self.base_urls[0]}/",
            callback=MetadataResponses.get_ok,
        )
        responses.add_callback(
            responses.GET,
            f"{self.base_urls[1]}/",
            callback=MetadataResponses.get_ok,
        )
        # Use _fix_mocking_url to workaround py3.6 bug in responses
        responses.add_callback(
            responses.GET,
            _fix_mocking_url(f"{self.base_urls[0]}/conf?format=json"),
            callback=MetadataResponses.get_ok,
        )
        responses.add_callback(
            responses.GET,
            _fix_mocking_url(f"{self.base_urls[1]}/conf?format=json"),
            callback=MetadataResponses.get_ok,
        )
        responses.add_callback(
            responses.GET,
            f"{self.base_urls[0]}/user_data/cloud-init",
            callback=DataResponses.get_ok,
        )
        responses.add_callback(
            responses.GET,
            f"{self.base_urls[0]}/vendor_data/cloud-init",
            callback=DataResponses.get_ok,
        )
        assert self.datasource.get_data()

        assert (
            self.datasource.get_instance_id()
            == MetadataResponses.FAKE_METADATA["id"]
        )
        ssh_keys = self.datasource.get_public_ssh_keys()
        ssh_keys.sort()
        assert ssh_keys == [
            "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABA",
            "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABCCCCC",
            "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABDDDDD",
        ]
        assert (
            self.datasource.get_hostname().hostname
            == MetadataResponses.FAKE_METADATA["hostname"]
        )
        assert (
            self.datasource.get_userdata_raw() == DataResponses.FAKE_USER_DATA
        )
        assert (
            self.datasource.get_vendordata_raw()
            == DataResponses.FAKE_USER_DATA
        )
        assert self.datasource.availability_zone == "fr-par-1"
        assert self.datasource.region == "fr-par"

    @responses.activate
    @mock.patch(
        "cloudinit.sources.DataSourceScaleway.DataSourceScaleway"
        ".override_ds_detect"
    )
    @mock.patch("cloudinit.sources.DataSourceScaleway.EphemeralIPv6Network")
    @mock.patch("cloudinit.sources.DataSourceScaleway.EphemeralDHCPv4")
    def test_ipv4_metadata_timeout_ipv6_ok(self, dhcpv4, inet6, ds_detect):
        """
        get_data() returns metadata, user data and vendor data from IPv6
        after IPv4 has failed.
        """
        ds_detect.return_value = True

        self.datasource._set_metadata_url([self.base_urls[0]])

        responses.reset()
        responses.add_callback(
            responses.GET,
            f"{self.base_urls[0]}/",
            callback=ConnectTimeout,
        )
        responses.add_callback(
            responses.GET,
            f"{self.base_urls[1]}/",
            callback=MetadataResponses.get_ok,
        )
        responses.add_callback(
            responses.GET,
            _fix_mocking_url(f"{self.base_urls[1]}/conf?format=json"),
            callback=MetadataResponses.get_ok,
        )
        responses.add_callback(
            responses.GET,
            _fix_mocking_url(f"{self.base_urls[1]}/user_data/cloud-init"),
            callback=DataResponses.get_ok,
        )
        responses.add_callback(
            responses.GET,
            f"{self.base_urls[1]}/vendor_data/cloud-init",
            callback=DataResponses.get_ok,
        )
        self.datasource.get_data()

        responses_assert_call_count(
            f"{self.datasource.metadata_urls[0]}",
            1,
        )
        responses_assert_call_count(
            f"{self.datasource.metadata_urls[1]}",
            1,
        )
        responses_assert_call_count(
            f"{self.datasource.metadata_urls[1]}/conf?format=json", 1
        )

        assert (
            self.datasource.get_instance_id()
            == MetadataResponses.FAKE_METADATA["id"]
        )
        ssh_keys = self.datasource.get_public_ssh_keys()
        ssh_keys.sort()
        assert ssh_keys == [
            "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABA",
            "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABCCCCC",
            "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABDDDDD",
        ]
        assert (
            self.datasource.get_hostname().hostname
            == MetadataResponses.FAKE_METADATA["hostname"]
        )
        assert (
            self.datasource.get_userdata_raw() == DataResponses.FAKE_USER_DATA
        )
        assert (
            self.datasource.get_vendordata_raw()
            == DataResponses.FAKE_USER_DATA
        )
        assert self.datasource.availability_zone == "fr-par-1"
        assert self.datasource.region == "fr-par"

    @responses.activate
    @mock.patch(
        "cloudinit.sources.DataSourceScaleway.DataSourceScaleway"
        ".override_ds_detect"
    )
    @mock.patch("cloudinit.url_helper.time.sleep")
    @mock.patch("cloudinit.sources.DataSourceScaleway.EphemeralIPv6Network")
    @mock.patch("cloudinit.sources.DataSourceScaleway.EphemeralDHCPv4")
    def test_ipv4_ipv6_metadata_timeout(self, dhcpv4, inet6, sleep, ds_detect):
        """
        get_data() fails to return metadata. Metadata, user data and
        vendor data are empty
        """
        ds_detect.return_value = True

        self.datasource._set_metadata_url([self.base_urls[0]])

        # Remove callbacks defined at class initialization
        responses.reset()
        responses.add_callback(
            responses.GET,
            f"{self.base_urls[0]}/",
            callback=ConnectTimeout,
        )
        responses.add_callback(
            responses.GET,
            f"{self.base_urls[1]}/",
            callback=ConnectTimeout,
        )
        self.datasource.max_wait = 0
        assert False is self.datasource.get_data()
        responses_assert_call_count(f"{self.datasource.metadata_urls[0]}", 2)
        responses_assert_call_count(f"{self.datasource.metadata_urls[1]}", 2)
        assert self.datasource.metadata == {}
        assert self.datasource.get_userdata_raw() is None
        assert self.datasource.get_vendordata_raw() is None

    @responses.activate
    @mock.patch(
        "cloudinit.sources.DataSourceScaleway.DataSourceScaleway"
        ".override_ds_detect"
    )
    @mock.patch("cloudinit.sources.DataSourceScaleway.EphemeralDHCPv4")
    def test_metadata_ipv4_404(self, dhcpv4, ds_detect):
        """
        get_data() returns metadata, but no user data nor vendor data.
        """
        ds_detect.return_value = True

        self.datasource._set_metadata_url([self.base_urls[0]])

        # Make user and vendor data APIs return HTTP/404, which means there is
        # no user / vendor data for the server.

        responses.add_callback(
            responses.GET,
            _fix_mocking_url(self.datasource.metadata_url),
            callback=MetadataResponses.get_ok,
        )
        responses.add_callback(
            responses.GET,
            _fix_mocking_url(self.datasource.userdata_url),
            callback=DataResponses.empty,
        )
        responses.add_callback(
            responses.GET,
            _fix_mocking_url(self.datasource.vendordata_url),
            callback=DataResponses.empty,
        )
        self.datasource.get_data()
        assert self.datasource.metadata == MetadataResponses.FAKE_METADATA
        assert self.datasource.get_userdata_raw() is None
        assert self.datasource.get_vendordata_raw() is None

    @responses.activate
    @mock.patch("cloudinit.url_helper.time.sleep", lambda x: None)
    @mock.patch("cloudinit.sources.DataSourceScaleway.EphemeralDHCPv4")
    def test_metadata_connection_errors_legacy_ipv4_url(self, dhcpv4):
        """
        get_data() returns ConnectionError on legacy IPv4 URL
        """

        self.datasource._set_metadata_url([self.base_urls[0]])

        # Make metadata API fail to connect for legacy ipv4 url
        self.datasource.metadata_urls = [
            "http://169.254.42.42",
        ]

        responses.reset()
        with pytest.raises(ConnectionError):
            responses.add_callback(
                responses.GET,
                f"{self.datasource.metadata_urls[0]}/",
                callback=ConnectionError,
            )
            self.datasource._set_metadata_url(self.datasource.metadata_urls)
        assert self.datasource.metadata == {}
        assert self.datasource.get_userdata_raw() is None
        assert self.datasource.get_vendordata_raw() is None

    @responses.activate
    @mock.patch(
        "cloudinit.sources.DataSourceScaleway.DataSourceScaleway"
        ".override_ds_detect"
    )
    @mock.patch("cloudinit.url_helper.time.sleep")
    @mock.patch("cloudinit.sources.DataSourceScaleway.socket.getaddrinfo")
    @mock.patch("cloudinit.sources.DataSourceScaleway.EphemeralIPv6Network")
    @mock.patch("cloudinit.sources.DataSourceScaleway.EphemeralDHCPv4")
    def test_metadata_connection_errors_two_urls(
        self, dhcpv4, net6, getaddr, sleep, ds_detect
    ):
        """
        get_data() returns ConnectionError on legacy or DNS URL
        The DNS URL is also tested for IPv6 connectivity
        """
        ds_detect.return_value = True

        self.datasource._set_metadata_url([self.base_urls[0]])
        getaddr.side_effect = [
            [
                [
                    socket.AF_INET,
                ]
            ],
        ] * 4

        # Make metadata API fail to connect for both legacy & DNS
        # DNS url will also be tested for IPv6 connectivity
        self.datasource.metadata_urls = [
            "http://169.254.42.42/",
            "http://api-metadata.com/",
        ]

        self.datasource.has_ipv4 = True
        responses.reset()
        responses.add_callback(
            responses.GET,
            self.datasource.metadata_urls[0],
            callback=ConnectionError,
        )
        responses.add_callback(
            responses.GET,
            self.datasource.metadata_urls[1],
            callback=ConnectionError,
        )
        self.datasource.max_wait = 0
        self.datasource.get_data()
        # url_helper.wait_on_url tests both URL in list each time so
        # called twice for each URL
        responses_assert_call_count(
            f"{self.datasource.metadata_urls[0]}",
            2,
        )
        responses_assert_call_count(
            f"{self.datasource.metadata_urls[1]}",
            2,
        )
        assert self.datasource.get_userdata_raw() is None
        assert self.datasource.get_vendordata_raw() is None

    @responses.activate
    @mock.patch(
        "cloudinit.sources.DataSourceScaleway.DataSourceScaleway"
        ".override_ds_detect"
    )
    @mock.patch("cloudinit.sources.DataSourceScaleway.EphemeralDHCPv4")
    @mock.patch("time.sleep", return_value=None)
    def test_metadata_ipv4_rate_limit(self, sleep, dhcpv4, ds_detect):
        """
        get_data() is rate limited two times by the metadata API when fetching
        user data.
        """
        ds_detect.return_value = True

        self.datasource._set_metadata_url([self.base_urls[0]])

        responses.add_callback(
            responses.GET,
            _fix_mocking_url(self.datasource.metadata_url),
            callback=MetadataResponses.get_ok,
        )
        responses.add_callback(
            responses.GET,
            _fix_mocking_url(self.datasource.vendordata_url),
            callback=DataResponses.empty,
        )
        # Temporary bump the retries count so the two rate limits do not
        # trigger an exception
        self.datasource.retries = 5

        # Workaround https://github.com/getsentry/responses/pull/171
        # This mocking can be unrolled when Bionic is EOL
        call_count = 0

        def _callback(request):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return DataResponses.rate_limited(request)
            return DataResponses.get_ok(request)

        responses.add_callback(
            responses.GET,
            _fix_mocking_url(self.datasource.userdata_url),
            callback=_callback,
        )
        self.datasource.get_data()
        assert (
            self.datasource.get_userdata_raw() == DataResponses.FAKE_USER_DATA
        )
        assert sleep.call_count == 2

    def test_ssh_keys_empty(self):
        """
        get_public_ssh_keys() should return empty list if no ssh key are
        available
        """
        self.datasource.metadata["tags"] = []
        self.datasource.metadata["ssh_public_keys"] = []
        assert self.datasource.get_public_ssh_keys() == []

    def test_ssh_keys_only_tags(self):
        """
        get_public_ssh_keys() should return list of keys available in tags
        """
        self.datasource.metadata["tags"] = [
            "AUTHORIZED_KEY=ssh-rsa_AAAAB3NzaC1yc2EAAAADAQABDDDDD",
            "AUTHORIZED_KEY=ssh-rsa_AAAAB3NzaC1yc2EAAAADAQABCCCCC",
        ]
        self.datasource.metadata["ssh_public_keys"] = []
        ssh_keys = self.datasource.get_public_ssh_keys()
        ssh_keys.sort()
        assert ssh_keys == [
            "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABCCCCC",
            "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABDDDDD",
        ]

    def test_ssh_keys_only_conf(self):
        """
        get_public_ssh_keys() should return list of keys available in
        ssh_public_keys field
        """
        self.datasource.metadata["tags"] = []
        self.datasource.metadata["ssh_public_keys"] = [
            {
                "key": "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABA",
                "fingerprint": "2048 06:ae:...  login (RSA)",
            },
            {
                "key": "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABCCCCC",
                "fingerprint": "2048 06:ff:...  login2 (RSA)",
            },
        ]
        ssh_keys = self.datasource.get_public_ssh_keys()
        ssh_keys.sort()
        assert ssh_keys == [
            "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABA",
            "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABCCCCC",
        ]

    def test_ssh_keys_both(self):
        """
        get_public_ssh_keys() should return a merge of keys available
        in ssh_public_keys and tags
        """
        self.datasource.metadata["tags"] = [
            "AUTHORIZED_KEY=ssh-rsa_AAAAB3NzaC1yc2EAAAADAQABDDDDD",
        ]

        self.datasource.metadata["ssh_public_keys"] = [
            {
                "key": "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABA",
                "fingerprint": "2048 06:ae:...  login (RSA)",
            },
            {
                "key": "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABCCCCC",
                "fingerprint": "2048 06:ff:...  login2 (RSA)",
            },
        ]
        ssh_keys = self.datasource.get_public_ssh_keys()
        ssh_keys.sort()
        assert ssh_keys == [
            "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABA",
            "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABCCCCC",
            "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABDDDDD",
        ]

    @mock.patch("cloudinit.distros.net.find_fallback_nic")
    @mock.patch("cloudinit.util.get_cmdline")
    def test_primary_ipv4_config_ok(self, m_get_cmdline, fallback_nic):
        """
        network_config will only generate IPv4 config if no IPv6 is
        available in the metadata
        """
        m_get_cmdline.return_value = "scaleway"
        fallback_nic.return_value = "ens2"
        self.datasource.ephemeral_fixed_address = "10.10.10.10"
        self.datasource.metadata["public_ips"] = [{"address": "10.10.10.10"}]

        netcfg = self.datasource.network_config
        resp = {
            "version": 2,
            "ethernets": {
                fallback_nic.return_value: {
                    "routes": [
                        {
                            "on-link": True,
                            "to": "169.254.42.42/32",
                            "via": "62.210.0.1",
                        }
                    ],
                    "dhcp4": True,
                },
            },
        }

        assert netcfg == resp

    @mock.patch("cloudinit.distros.net.find_fallback_nic")
    @mock.patch("cloudinit.util.get_cmdline")
    def test_additional_ipv4_config_ok(self, m_get_cmdline, fallback_nic):
        """
        network_config will generate IPv4 config with additional address
        """
        m_get_cmdline.return_value = "scaleway"
        fallback_nic.return_value = "ens2"
        self.datasource.ephemeral_fixed_address = "10.10.10.10"
        self.datasource.metadata["public_ips"] = [
            {
                "address": "10.10.10.10",
                "netmask": "32",
                "family": "inet",
            },
            {
                "address": "20.20.20.20",
                "netmask": "32",
                "family": "inet",
            },
        ]

        netcfg = self.datasource.network_config
        resp = {
            "version": 2,
            "ethernets": {
                fallback_nic.return_value: {
                    "dhcp4": True,
                    "routes": [
                        {
                            "on-link": True,
                            "to": "169.254.42.42/32",
                            "via": "62.210.0.1",
                        }
                    ],
                    "addresses": ("20.20.20.20/32",),
                },
            },
        }
        assert netcfg == resp

    @mock.patch("cloudinit.distros.net.find_fallback_nic")
    @mock.patch("cloudinit.util.get_cmdline")
    def test_primary_ipv6_config_ok(self, m_get_cmdline, fallback_nic):
        """
        Generate network_config with only IPv6
        """
        m_get_cmdline.return_value = "scaleway"
        fallback_nic.return_value = "ens2"
        self.datasource.ephemeral_fixed_address = "10.10.10.10"
        self.datasource.metadata["public_ips"] = [
            {
                "address": "2001:aaa:aaaa:a:aaaa:aaaa:aaaa:1",
                "netmask": "64",
                "gateway": "fe80::ffff:ffff:ffff:fff1",
                "family": "inet6",
            },
        ]

        netcfg = self.datasource.network_config
        resp = {
            "version": 2,
            "ethernets": {
                fallback_nic.return_value: {
                    "addresses": ("2001:aaa:aaaa:a:aaaa:aaaa:aaaa:1/64",),
                    "routes": [
                        {
                            "via": "fe80::ffff:ffff:ffff:fff1",
                            "to": "::/0",
                        }
                    ],
                },
            },
        }

        assert netcfg == resp

    @mock.patch("cloudinit.distros.net.find_fallback_nic")
    @mock.patch("cloudinit.util.get_cmdline")
    def test_primary_ipv4_v6_config_ok(self, m_get_cmdline, fallback_nic):
        """
        Generate network_config with IPv4+IPv6
        """
        m_get_cmdline.return_value = "scaleway"
        fallback_nic.return_value = "ens2"
        self.datasource.ephemeral_fixed_address = "10.10.10.10"
        self.datasource.metadata["public_ips"] = [
            {
                "address": "10.10.10.10",
                "netmask": "32",
                "family": "inet",
            },
            {
                "address": "2001:aaa:aaaa:a:aaaa:aaaa:aaaa:1",
                "netmask": "64",
                "gateway": "fe80::ffff:ffff:ffff:fff1",
                "family": "inet6",
            },
        ]

        netcfg = self.datasource.network_config
        resp = {
            "version": 2,
            "ethernets": {
                fallback_nic.return_value: {
                    "dhcp4": True,
                    "routes": [
                        {
                            "on-link": True,
                            "to": "169.254.42.42/32",
                            "via": "62.210.0.1",
                        },
                        {
                            "via": "fe80::ffff:ffff:ffff:fff1",
                            "to": "::/0",
                        },
                    ],
                    "addresses": ("2001:aaa:aaaa:a:aaaa:aaaa:aaaa:1/64",),
                },
            },
        }

        assert netcfg == resp

    @mock.patch("cloudinit.distros.net.find_fallback_nic")
    @mock.patch("cloudinit.util.get_cmdline")
    def test_primary_ipv6_v4_config_ok(self, m_get_cmdline, fallback_nic):
        """
        Generate network_config with IPv6+IPv4
        """
        m_get_cmdline.return_value = "scaleway"
        fallback_nic.return_value = "ens2"
        self.datasource.ephemeral_fixed_address = "10.10.10.10"
        self.datasource.metadata["public_ips"] = [
            {
                "address": "2001:aaa:aaaa:a:aaaa:aaaa:aaaa:1",
                "netmask": "64",
                "gateway": "fe80::ffff:ffff:ffff:fff1",
                "family": "inet6",
            },
            {
                "address": "10.10.10.10",
                "netmask": "32",
                "family": "inet",
            },
        ]

        netcfg = self.datasource.network_config
        resp = {
            "version": 2,
            "ethernets": {
                fallback_nic.return_value: {
                    "dhcp4": True,
                    "routes": [
                        {
                            "via": "fe80::ffff:ffff:ffff:fff1",
                            "to": "::/0",
                        },
                        {
                            "on-link": True,
                            "to": "169.254.42.42/32",
                            "via": "62.210.0.1",
                        },
                    ],
                    "addresses": ("2001:aaa:aaaa:a:aaaa:aaaa:aaaa:1/64",),
                },
            },
        }

        assert netcfg == resp
