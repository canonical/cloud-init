import json

from cloudinit import distros, helpers, subp
from cloudinit.sources import DataSourceRbxCloud as ds
from tests.unittests.helpers import CiTestCase, mock, populate_dir

DS_PATH = "cloudinit.sources.DataSourceRbxCloud"

CRYPTO_PASS = (
    "$6$uktth46t$FvpDzFD2iL9YNZIG1Epz7957hJqbH0f"
    "QKhnzcfBcUhEodGAWRqTy7tYG4nEW7SUOYBjxOSFIQW5"
    "tToyGP41.s1"
)

CLOUD_METADATA = {
    "vm": {
        "memory": 4,
        "cpu": 2,
        "name": "vm-image-builder",
        "_id": "5beab44f680cffd11f0e60fc",
    },
    "additionalMetadata": {
        "username": "guru",
        "sshKeys": ["ssh-rsa ..."],
        "password": {"sha512": CRYPTO_PASS},
    },
    "disk": [
        {
            "size": 10,
            "type": "ssd",
            "name": "vm-image-builder-os",
            "_id": "5beab450680cffd11f0e60fe",
        },
        {
            "size": 2,
            "type": "ssd",
            "name": "ubuntu-1804-bionic",
            "_id": "5bef002c680cffd11f107590",
        },
    ],
    "netadp": [
        {
            "ip": [{"address": "62.181.8.174"}],
            "network": {
                "dns": {"nameservers": ["8.8.8.8", "8.8.4.4"]},
                "routing": [],
                "gateway": "62.181.8.1",
                "netmask": "255.255.248.0",
                "name": "public",
                "type": "public",
                "_id": "5784e97be2627505227b578c",
            },
            "speed": 1000,
            "type": "hv",
            "macaddress": "00:15:5D:FF:0F:03",
            "_id": "5beab450680cffd11f0e6102",
        },
        {
            "ip": [{"address": "10.209.78.11"}],
            "network": {
                "dns": {"nameservers": ["9.9.9.9", "8.8.8.8"]},
                "routing": [],
                "gateway": "10.209.78.1",
                "netmask": "255.255.255.0",
                "name": "network-determined-bardeen",
                "type": "private",
                "_id": "5beaec64680cffd11f0e7c31",
            },
            "speed": 1000,
            "type": "hv",
            "macaddress": "00:15:5D:FF:0F:24",
            "_id": "5bec18c6680cffd11f0f0d8b",
        },
    ],
    "dvddrive": [{"iso": {}}],
}


class TestRbxDataSource(CiTestCase):
    parsed_user = None
    allowed_subp = ["bash"]

    def _fetch_distro(self, kind):
        cls = distros.fetch(kind)
        paths = helpers.Paths({})
        return cls(kind, {}, paths)

    def setUp(self):
        super(TestRbxDataSource, self).setUp()
        self.tmp = self.tmp_dir()
        self.paths = helpers.Paths(
            {"cloud_dir": self.tmp, "run_dir": self.tmp}
        )

        # defaults for few tests
        self.ds = ds.DataSourceRbxCloud
        self.seed_dir = self.paths.seed_dir
        self.sys_cfg = {"datasource": {"RbxCloud": {"dsmode": "local"}}}

    def test_seed_read_user_data_callback_empty_file(self):
        populate_user_metadata(self.seed_dir, "")
        populate_cloud_metadata(self.seed_dir, {})
        results = ds.read_user_data_callback(self.seed_dir)

        self.assertIsNone(results)

    def test_seed_read_user_data_callback_valid_disk(self):
        populate_user_metadata(self.seed_dir, "")
        populate_cloud_metadata(self.seed_dir, CLOUD_METADATA)
        results = ds.read_user_data_callback(self.seed_dir)

        self.assertNotEqual(results, None)
        self.assertTrue("userdata" in results)
        self.assertTrue("metadata" in results)
        self.assertTrue("cfg" in results)

    def test_seed_read_user_data_callback_userdata(self):
        userdata = "#!/bin/sh\nexit 1"
        populate_user_metadata(self.seed_dir, userdata)
        populate_cloud_metadata(self.seed_dir, CLOUD_METADATA)

        results = ds.read_user_data_callback(self.seed_dir)

        self.assertNotEqual(results, None)
        self.assertTrue("userdata" in results)
        self.assertEqual(results["userdata"], userdata)

    def test_generate_network_config(self):
        expected = {
            "version": 1,
            "config": [
                {
                    "subnets": [
                        {
                            "control": "auto",
                            "dns_nameservers": ["8.8.8.8", "8.8.4.4"],
                            "netmask": "255.255.248.0",
                            "address": "62.181.8.174",
                            "type": "static",
                            "gateway": "62.181.8.1",
                        }
                    ],
                    "type": "physical",
                    "name": "eth0",
                    "mac_address": "00:15:5d:ff:0f:03",
                },
                {
                    "subnets": [
                        {
                            "control": "auto",
                            "dns_nameservers": ["9.9.9.9", "8.8.8.8"],
                            "netmask": "255.255.255.0",
                            "address": "10.209.78.11",
                            "type": "static",
                            "gateway": "10.209.78.1",
                        }
                    ],
                    "type": "physical",
                    "name": "eth1",
                    "mac_address": "00:15:5d:ff:0f:24",
                },
            ],
        }
        self.assertTrue(
            ds.generate_network_config(CLOUD_METADATA["netadp"]), expected
        )

    @mock.patch(DS_PATH + ".subp.subp")
    def test_gratuitous_arp_run_standard_arping(self, m_subp):
        """Test handle run arping & parameters."""
        items = [
            {"destination": "172.17.0.2", "source": "172.16.6.104"},
            {
                "destination": "172.17.0.2",
                "source": "172.16.6.104",
            },
        ]
        ds.gratuitous_arp(items, self._fetch_distro("ubuntu"))
        self.assertEqual(
            [
                mock.call(
                    ["arping", "-c", "2", "-S", "172.16.6.104", "172.17.0.2"]
                ),
                mock.call(
                    ["arping", "-c", "2", "-S", "172.16.6.104", "172.17.0.2"]
                ),
            ],
            m_subp.call_args_list,
        )

    @mock.patch(DS_PATH + ".subp.subp")
    def test_handle_rhel_like_arping(self, m_subp):
        """Test handle on RHEL-like distros."""
        items = [
            {
                "source": "172.16.6.104",
                "destination": "172.17.0.2",
            }
        ]
        ds.gratuitous_arp(items, self._fetch_distro("fedora"))
        self.assertEqual(
            [
                mock.call(
                    ["arping", "-c", "2", "-s", "172.16.6.104", "172.17.0.2"]
                )
            ],
            m_subp.call_args_list,
        )

    @mock.patch(
        DS_PATH + ".subp.subp", side_effect=subp.ProcessExecutionError()
    )
    def test_continue_on_arping_error(self, m_subp):
        """Continue when command error"""
        items = [
            {"destination": "172.17.0.2", "source": "172.16.6.104"},
            {
                "destination": "172.17.0.2",
                "source": "172.16.6.104",
            },
        ]
        ds.gratuitous_arp(items, self._fetch_distro("ubuntu"))
        self.assertEqual(
            [
                mock.call(
                    ["arping", "-c", "2", "-S", "172.16.6.104", "172.17.0.2"]
                ),
                mock.call(
                    ["arping", "-c", "2", "-S", "172.16.6.104", "172.17.0.2"]
                ),
            ],
            m_subp.call_args_list,
        )


def populate_cloud_metadata(path, data):
    populate_dir(path, {"cloud.json": json.dumps(data)})


def populate_user_metadata(path, data):
    populate_dir(path, {"user.data": data})
