# Author: Eric Benner <ebenner@vultr.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

# Vultr Metadata API:
# https://www.vultr.com/metadata/

import json

from cloudinit import helpers, settings
from cloudinit.net.dhcp import NoDHCPLeaseError
from cloudinit.sources import DataSourceVultr
from cloudinit.sources.helpers import vultr
from tests.unittests.helpers import CiTestCase, mock

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
    "region": {"regioncode": "EWR"},
    "user-defined": [],
    "startup-script": "echo No configured startup script",
    "raid1-script": "",
    "user-data": [],
    "vendor-data": [
        {
            "package_upgrade": "true",
            "disable_root": 0,
            "ssh_pwauth": 1,
            "chpasswd": {
                "expire": False,
                "list": ["root:$6$S2Smuj.../VqxmIR9Urw0jPZ88i4yvB/"],
            },
            "system_info": {"default_user": {"name": "root"}},
        }
    ],
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
    "instance-v2-id": "29bea708-2e6e-480a-90ad-0e6b5d5ad62f",
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
    "region": {"regioncode": "EWR"},
    "user-defined": [],
    "startup-script": "echo No configured startup script",
    "user-data": [],
    "vendor-data": [
        {
            "package_upgrade": "true",
            "disable_root": 0,
            "ssh_pwauth": 1,
            "chpasswd": {
                "expire": False,
                "list": ["root:$6$SxXx...k2mJNIzZB5vMCDBlYT1"],
            },
            "system_info": {"default_user": {"name": "root"}},
        }
    ],
}

SSH_KEYS_1 = ["ssh-rsa AAAAB3NzaC1y...IQQhv5PAOKaIl+mM3c= test3@key"]

INTERFACES = [
    ["lo", "56:00:03:15:c4:00", "drv", "devid0"],
    ["dummy0", "56:00:03:15:c4:01", "drv", "devid1"],
    ["eth1", "56:00:03:15:c4:02", "drv", "devid2"],
    ["eth0", "56:00:03:15:c4:04", "drv", "devid4"],
    ["eth2", "56:00:03:15:c4:03", "drv", "devid3"],
]

# Expected generated objects

# Expected config
EXPECTED_VULTR_CONFIG = {
    "package_upgrade": "true",
    "disable_root": 0,
    "ssh_pwauth": 1,
    "chpasswd": {
        "expire": False,
        "list": ["root:$6$SxXx...k2mJNIzZB5vMCDBlYT1"],
    },
    "system_info": {"default_user": {"name": "root"}},
}

# Expected network config object from generator
EXPECTED_VULTR_NETWORK_1 = {
    "version": 1,
    "config": [
        {"type": "nameserver", "address": ["108.61.10.10"]},
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
        {"type": "nameserver", "address": ["108.61.10.10"]},
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


EPHERMERAL_USED = ""


class TestDataSourceVultr(CiTestCase):
    def setUp(self):
        super(TestDataSourceVultr, self).setUp()

        # Stored as a dict to make it easier to maintain
        raw1 = json.dumps(VULTR_V1_1["vendor-data"][0])
        raw2 = json.dumps(VULTR_V1_2["vendor-data"][0])

        # Make expected format
        VULTR_V1_1["vendor-data"] = [raw1]
        VULTR_V1_2["vendor-data"] = [raw2]

        self.tmp = self.tmp_dir()

    # Test the datasource itself
    @mock.patch("cloudinit.net.get_interfaces_by_mac")
    @mock.patch("cloudinit.sources.helpers.vultr.is_vultr")
    @mock.patch("cloudinit.sources.helpers.vultr.get_metadata")
    def test_datasource(self, mock_getmeta, mock_isvultr, mock_netmap):
        mock_getmeta.return_value = VULTR_V1_2
        mock_isvultr.return_value = True
        mock_netmap.return_value = INTERFACE_MAP

        source = DataSourceVultr.DataSourceVultr(
            settings.CFG_BUILTIN, None, helpers.Paths({"run_dir": self.tmp})
        )

        # Test for failure
        self.assertEqual(True, source._get_data())

        # Test instance id
        self.assertEqual("42872224", source.metadata["instanceid"])

        # Test hostname
        self.assertEqual("CLOUDINIT_2", source.metadata["local-hostname"])

        # Test ssh keys
        self.assertEqual(SSH_KEYS_1, source.metadata["public-keys"])

        # Test vendor data generation
        orig_val = self.maxDiff
        self.maxDiff = None

        vendordata = source.vendordata_raw

        # Test vendor config
        self.assertEqual(
            EXPECTED_VULTR_CONFIG,
            json.loads(vendordata[0].replace("#cloud-config", "")),
        )

        self.maxDiff = orig_val

        # Test network config generation
        self.assertEqual(EXPECTED_VULTR_NETWORK_2, source.network_config)

    # Test network config generation
    @mock.patch("cloudinit.net.get_interfaces_by_mac")
    def test_network_config(self, mock_netmap):
        mock_netmap.return_value = INTERFACE_MAP
        interf = VULTR_V1_1["interfaces"]

        self.assertEqual(
            EXPECTED_VULTR_NETWORK_1, vultr.generate_network_config(interf)
        )

    # Test Private Networking config generation
    @mock.patch("cloudinit.net.get_interfaces_by_mac")
    def test_private_network_config(self, mock_netmap):
        mock_netmap.return_value = INTERFACE_MAP
        interf = VULTR_V1_2["interfaces"]

        self.assertEqual(
            EXPECTED_VULTR_NETWORK_2, vultr.generate_network_config(interf)
        )

    def ephemeral_init(self, iface="", connectivity_url_data=None):
        global EPHERMERAL_USED
        EPHERMERAL_USED = iface
        if iface == "eth0":
            return
        raise NoDHCPLeaseError("Generic for testing")

    # Test interface seeking to ensure we are able to find the correct one
    @mock.patch("cloudinit.net.dhcp.EphemeralDHCPv4.__init__", ephemeral_init)
    @mock.patch("cloudinit.sources.helpers.vultr.is_vultr")
    @mock.patch("cloudinit.sources.helpers.vultr.read_metadata")
    @mock.patch("cloudinit.net.get_interfaces")
    def test_interface_seek(
        self, mock_get_interfaces, mock_read_metadata, mock_isvultr
    ):
        mock_read_metadata.side_effect = NoDHCPLeaseError(
            "Generic for testing"
        )
        mock_isvultr.return_value = True
        mock_get_interfaces.return_value = INTERFACES

        source = DataSourceVultr.DataSourceVultr(
            settings.CFG_BUILTIN, None, helpers.Paths({"run_dir": self.tmp})
        )

        try:
            source._get_data()
        except Exception:
            pass

        self.assertEqual(EPHERMERAL_USED, INTERFACES[3][0])


# vi: ts=4 expandtab
