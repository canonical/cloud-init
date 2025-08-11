# Author: Eric Benner <ebenner@vultr.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

# Vultr Metadata API:
# https://www.vultr.com/metadata/

import copy
import json

import pytest

from cloudinit import settings
from cloudinit.net.dhcp import NoDHCPLeaseError
from cloudinit.sources import DataSourceVultr
from cloudinit.sources.helpers import vultr
from tests.unittests.helpers import mock

VENDOR_DATA = """\
#cloud-config
package_upgrade: true
disable_root: 0
ssh_pwauth: 1
chpasswd:
  expire: false
  list:
  - root:$6$SxXx...k2mJNIzZB5vMCDBlYT1
"""

# Vultr metadata test data
VULTR_V1_1 = {
    "bgp": {
        "ipv4": {
            "my-address": "",
            "my-asn": "",
            "peer-address": "",
            "peer-asn": "",
        },
        "ipv6": {
            "my-address": "",
            "my-asn": "",
            "peer-address": "",
            "peer-asn": "",
        },
    },
    "hostname": "CLOUDINIT_1",
    "local-hostname": "CLOUDINIT_1",
    "instance-v2-id": "29bea708-2e6e-480a-90ad-0e6b5d5ad62f",
    "instance-id": "29bea708-2e6e-480a-90ad-0e6b5d5ad62f",
    "instanceid": "42506325",
    "interfaces": [
        {
            "ipv4": {
                "additional": [],
                "address": "108.61.89.242",
                "gateway": "108.61.89.1",
                "netmask": "255.255.255.0",
            },
            "ipv6": {
                "additional": [],
                "address": "2001:19f0:5:56c2:5400:03ff:fe15:c465",
                "network": "2001:19f0:5:56c2::",
                "prefix": "64",
            },
            "mac": "56:00:03:15:c4:65",
            "network-type": "public",
        }
    ],
    "public-keys": ["ssh-rsa AAAAB3NzaC1y...IQQhv5PAOKaIl+mM3c= test3@key"],
    "region": {"regioncode": "EWR", "countrycode": "US"},
    "user-defined": [],
    "startup-script": "echo No configured startup script",
    "raid1-script": "",
    "user-data": [],
    "vendor-data": VENDOR_DATA,
}

VULTR_V1_2 = {
    "bgp": {
        "ipv4": {
            "my-address": "",
            "my-asn": "",
            "peer-address": "",
            "peer-asn": "",
        },
        "ipv6": {
            "my-address": "",
            "my-asn": "",
            "peer-address": "",
            "peer-asn": "",
        },
    },
    "hostname": "CLOUDINIT_2",
    "local-hostname": "CLOUDINIT_2",
    "instance-v2-id": "29bea708-2e6e-480a-90ad-0e6b5d5ad62f",
    "instance-id": "29bea708-2e6e-480a-90ad-0e6b5d5ad62f",
    "instanceid": "42872224",
    "interfaces": [
        {
            "ipv4": {
                "additional": [],
                "address": "45.76.7.171",
                "gateway": "45.76.6.1",
                "netmask": "255.255.254.0",
            },
            "ipv6": {
                "additional": [
                    {"network": "2002:19f0:5:28a7::", "prefix": "64"}
                ],
                "address": "2001:19f0:5:28a7:5400:03ff:fe1b:4eca",
                "network": "2001:19f0:5:28a7::",
                "prefix": "64",
            },
            "mac": "56:00:03:1b:4e:ca",
            "network-type": "public",
        },
        {
            "ipv4": {
                "additional": [],
                "address": "10.1.112.3",
                "gateway": "",
                "netmask": "255.255.240.0",
            },
            "ipv6": {"additional": [], "network": "", "prefix": ""},
            "mac": "5a:00:03:1b:4e:ca",
            "network-type": "private",
            "network-v2-id": "fbbe2b5b-b986-4396-87f5-7246660ccb64",
            "networkid": "net5e7155329d730",
        },
    ],
    "public-keys": ["ssh-rsa AAAAB3NzaC1y...IQQhv5PAOKaIl+mM3c= test3@key"],
    "region": {"regioncode": "EWR", "countrycode": "US"},
    "user-defined": [],
    "startup-script": "echo No configured startup script",
    "user-data": [],
    "vendor-data": VENDOR_DATA,
}

SSH_KEYS_1 = ["ssh-rsa AAAAB3NzaC1y...IQQhv5PAOKaIl+mM3c= test3@key"]

CLOUD_INTERFACES = {
    "version": 1,
    "config": [
        {
            "type": "nameserver",
            "address": ["108.61.10.10", "2001:19f0:300:1704::6"],
        },
        {
            "type": "physical",
            "mac_address": "56:00:03:1b:4e:ca",
            "accept-ra": 1,
            "subnets": [
                {"type": "dhcp", "control": "auto"},
                {"type": "ipv6_slaac", "control": "auto"},
                {
                    "type": "static6",
                    "control": "auto",
                    "address": "2002:19f0:5:28a7::/64",
                },
            ],
        },
        {
            "type": "physical",
            "mac_address": "5a:00:03:1b:4e:ca",
            "subnets": [
                {
                    "type": "static",
                    "control": "auto",
                    "address": "10.1.112.3",
                    "netmask": "255.255.240.0",
                }
            ],
        },
    ],
}

INTERFACES = ["lo", "dummy0", "eth1", "eth0", "eth2"]

ORDERED_INTERFACES = ["eth0", "eth1", "eth2"]

FILTERED_INTERFACES = ["eth1", "eth2", "eth0"]

# Expected network config object from generator
EXPECTED_VULTR_NETWORK_1 = {
    "version": 1,
    "config": [
        {
            "type": "nameserver",
            "address": ["108.61.10.10", "2001:19f0:300:1704::6"],
        },
        {
            "name": "eth0",
            "type": "physical",
            "mac_address": "56:00:03:15:c4:65",
            "accept-ra": 1,
            "subnets": [
                {"type": "dhcp", "control": "auto"},
                {"type": "ipv6_slaac", "control": "auto"},
            ],
        },
    ],
}

EXPECTED_VULTR_NETWORK_2 = {
    "version": 1,
    "config": [
        {
            "type": "nameserver",
            "address": ["108.61.10.10", "2001:19f0:300:1704::6"],
        },
        {
            "name": "eth0",
            "type": "physical",
            "mac_address": "56:00:03:1b:4e:ca",
            "accept-ra": 1,
            "subnets": [
                {"type": "dhcp", "control": "auto"},
                {"type": "ipv6_slaac", "control": "auto"},
                {
                    "type": "static6",
                    "control": "auto",
                    "address": "2002:19f0:5:28a7::/64",
                },
            ],
        },
        {
            "name": "eth1",
            "type": "physical",
            "mac_address": "5a:00:03:1b:4e:ca",
            "subnets": [
                {
                    "type": "static",
                    "control": "auto",
                    "address": "10.1.112.3",
                    "netmask": "255.255.240.0",
                }
            ],
        },
    ],
}


INTERFACE_MAP = {
    "56:00:03:15:c4:65": "eth0",
    "56:00:03:1b:4e:ca": "eth0",
    "5a:00:03:1b:4e:ca": "eth1",
}


class TestDataSourceVultr:
    @pytest.fixture
    def source(self, paths, tmp_path):
        distro = mock.MagicMock()
        distro.get_tmp_exec_path.return_value = str(tmp_path)
        return DataSourceVultr.DataSourceVultr(
            settings.CFG_BUILTIN, distro, paths
        )

    # Test the datasource itself
    @mock.patch("cloudinit.net.get_interfaces_by_mac")
    @mock.patch("cloudinit.sources.helpers.vultr.is_vultr")
    @mock.patch("cloudinit.sources.helpers.vultr.get_metadata")
    def test_datasource(self, mock_getmeta, mock_isvultr, mock_netmap, source):
        mock_getmeta.return_value = VULTR_V1_2
        mock_isvultr.return_value = True
        mock_netmap.return_value = INTERFACE_MAP

        assert True is source._get_data()
        assert "42872224" == source.metadata["instanceid"]
        assert "CLOUDINIT_2" == source.metadata["local-hostname"]
        assert SSH_KEYS_1 == source.metadata["public-keys"]
        assert VENDOR_DATA == source.vendordata_raw
        assert EXPECTED_VULTR_NETWORK_2 == source.network_config

    def _get_metadata(self):
        # Create v1_3
        vultr_v1_3 = VULTR_V1_2.copy()
        vultr_v1_3["cloud_interfaces"] = CLOUD_INTERFACES.copy()
        vultr_v1_3["interfaces"] = []
        vultr_v1_3["vendor-data"] = copy.deepcopy(VULTR_V1_2["vendor-data"])

        return vultr_v1_3

    # Test the datasource with new network config type
    @mock.patch("cloudinit.net.get_interfaces_by_mac")
    @mock.patch("cloudinit.sources.helpers.vultr.is_vultr")
    @mock.patch("cloudinit.sources.helpers.vultr.get_metadata")
    def test_datasource_cloud_interfaces(
        self, mock_getmeta, mock_isvultr, mock_netmap, source
    ):
        mock_getmeta.return_value = self._get_metadata()
        mock_isvultr.return_value = True
        mock_netmap.return_value = INTERFACE_MAP

        source._get_data()

        # Test network config generation
        assert EXPECTED_VULTR_NETWORK_2 == source.network_config

    # Test network config generation
    @mock.patch("cloudinit.net.get_interfaces_by_mac")
    def test_network_config(self, mock_netmap):
        mock_netmap.return_value = INTERFACE_MAP
        interf = VULTR_V1_1["interfaces"]

        assert EXPECTED_VULTR_NETWORK_1 == vultr.generate_network_config(
            interf
        )

    # Test Private Networking config generation
    @mock.patch("cloudinit.net.get_interfaces_by_mac")
    def test_private_network_config(self, mock_netmap):
        mock_netmap.return_value = INTERFACE_MAP
        interf = copy.deepcopy(VULTR_V1_2["interfaces"])

        # Test configuring
        assert EXPECTED_VULTR_NETWORK_2 == vultr.generate_network_config(
            interf
        )

        # Test unconfigured
        interf[1]["unconfigured"] = True
        expected = copy.deepcopy(EXPECTED_VULTR_NETWORK_2)
        expected["config"].pop(2)
        assert expected == vultr.generate_network_config(interf)

    # Override ephemeral for proper unit testing
    def override_enter(self):
        return

    # Override ephemeral for proper unit testing
    def override_exit(self, excp_type, excp_value, excp_traceback):
        return

    # Test interface seeking to ensure we are able to find the correct one
    @mock.patch(
        "cloudinit.net.ephemeral.EphemeralDHCPv4.__init__",
        side_effect=(NoDHCPLeaseError("Generic for testing"), None),
    )
    @mock.patch(
        "cloudinit.net.ephemeral.EphemeralDHCPv4.__enter__", override_enter
    )
    @mock.patch(
        "cloudinit.net.ephemeral.EphemeralDHCPv4.__exit__", override_exit
    )
    @mock.patch("cloudinit.sources.helpers.vultr.is_vultr")
    @mock.patch("cloudinit.sources.helpers.vultr.read_metadata")
    @mock.patch("cloudinit.sources.helpers.vultr.get_interface_list")
    def test_interface_seek(
        self,
        mock_interface_list,
        mock_read_metadata,
        mock_isvultr,
        mock_eph_init,
        source,
    ):
        mock_read_metadata.return_value = json.dumps(VULTR_V1_1)
        mock_isvultr.return_value = True
        mock_interface_list.return_value = FILTERED_INTERFACES

        source.get_metadata()

        assert mock_eph_init.call_args[1]["iface"] == FILTERED_INTERFACES[1]
