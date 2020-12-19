# Author: Eric Benner <ebenner@vultr.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

# Vultr Metadata API:
# https://www.vultr.com/metadata/

import json

from cloudinit import helpers
from cloudinit import settings
from cloudinit.sources import DataSourceVultr
from cloudinit.sources.helpers import vultr

from cloudinit.tests.helpers import mock, CiTestCase

# Vultr metadata test data
VULTR_ROOT_PASSWORD_1 = "$6$S2SmujFrCbMsobmu$5PPQqWGvBtONTg3NUW/MDhyz7l3lpYEyQ8w9gOJE.RQPlueITLXJRM4DKEbQHdc/VqxmIR9Urw0jPZ88i4yvB/"
VULTR_V1_1 = """
{
    "bgp": {
        "ipv4": {
            "my-address": "",
            "my-asn": "",
            "peer-address": "",
            "peer-asn": ""
        },
        "ipv6": {
            "my-address": "",
            "my-asn": "",
            "peer-address": "",
            "peer-asn": ""
        }
    },
    "hostname": "CLOUDINIT_1",
    "instanceid": "42506325",
    "interfaces": [
        {
            "ipv4": {
                "additional": [
                ],
                "address": "108.61.89.242",
                "gateway": "108.61.89.1",
                "netmask": "255.255.255.0"
            },
            "ipv6": {
                "additional": [
                ],
                "address": "2001:19f0:5:56c2:5400:03ff:fe15:c465",
                "network": "2001:19f0:5:56c2::",
                "prefix": "64"
            },
            "mac": "56:00:03:15:c4:65",
            "network-type": "public"
        }
    ],
    "public-keys": "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCvgL32fARIGLNs2w6Kt/t/jYeVgHLQf4VueOwfMZNhXAqe0183eABr40scKb4zTSre9/zMgQHFs/unptRLzLt/hS7ncyioy95Nllg8qw+u/TS71gPu5RozfB0epNzcFdWwro+ibGW3eZO0bOzV8ENaWAfA734YqTDOOVdJYquiU8iLKTP/Rl0RYmCkgQ2tyYpklWVh8DQOa0nenosYihEBOpTgKjtE98ym63EmMkozbEjgt0d8vXGHLUwZ5JvBCubR8YjJ5lL7wmcLf+nx2Dg2zFhhblsF81N+L4K1yx+s0I77hG6bKhOc1X4KoKJJn4bfH7vtMVsPptdAMsFX8W/FvsRMT7/eZ7PHMahC7d2NGCccL6TIK2vxyJxdMO+88mLockKpgixhsbPSq99NurOQiHOhFH4cityQVtH/3qyr4oDYVscAnZsUk93k+2Z/WCYFfHh5HpfWU6dZFgiZlWsJ7Yt6J7ovDUo/aZZmQc1rxsvqcIQQhv5PAOKaIl+mM1c= test@key\\nssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCvgL32fARIGLNs2w6Kt/t/jYeVgHLQf4VueOwfMZNhXAqe0183eABr40scKb4zTSre9/zMgQHFs/unptRLzLt/hS7ncyioy95Nllg8qw+u/TS71gPu5RozfB0epNzcFdWwro+ibGW3eZO0bOzV8ENaWAfA734YqTDOOVdJYquiU8iLKTP/Rl0RYmCkgQ2tyYpklWVh8DQOa0nenosYihEBOpTgKjtE98ym63EmMkozbEjgt0d8vXGHLUwZ5JvBCubR8YjJ5lL7wmcLf+nx2Dg2zFhhblsF81N+L4K1yx+s0I77hG6bKhOc1X4KoKJJn4bfH7vtMVsPptdAMsFX8W/FvsRMT7/eZ7PHMahC7d2NGCccL6TIK2vxyJxdMO+88mLockKpgixhsbPSq99NurOQiHOhFH4cityQVtH/3qyr4oDYVscAnZsUk93k+2Z/WCYFfHh5HpfWU6dZFgiZlWsJ7Yt6J7ovDUo/aZZmQc1rxsvqcIQQhv5PAOKaIl+mM2c= test2@key\\nssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCvgL32fARIGLNs2w6Kt/t/jYeVgHLQf4VueOwfMZNhXAqe0183eABr40scKb4zTSre9/zMgQHFs/unptRLzLt/hS7ncyioy95Nllg8qw+u/TS71gPu5RozfB0epNzcFdWwro+ibGW3eZO0bOzV8ENaWAfA734YqTDOOVdJYquiU8iLKTP/Rl0RYmCkgQ2tyYpklWVh8DQOa0nenosYihEBOpTgKjtE98ym63EmMkozbEjgt0d8vXGHLUwZ5JvBCubR8YjJ5lL7wmcLf+nx2Dg2zFhhblsF81N+L4K1yx+s0I77hG6bKhOc1X4KoKJJn4bfH7vtMVsPptdAMsFX8W/FvsRMT7/eZ7PHMahC7d2NGCccL6TIK2vxyJxdMO+88mLockKpgixhsbPSq99NurOQiHOhFH4cityQVtH/3qyr4oDYVscAnZsUk93k+2Z/WCYFfHh5HpfWU6dZFgiZlWsJ7Yt6J7ovDUo/aZZmQc1rxsvqcIQQhv5PAOKaIl+mM3c= test3@key\\n",
    "region": {
        "regioncode": "EWR"
    },
    "user-defined": [
    ]
}
"""

VULTR_ROOT_PASSWORD_2 = "$6$SxXxTd37HQkwxlOM$/z65E0u9ucrHtQBH9y.chMD2GSbKGFKc/QyYkU9WN/pqQ/lOGZL1YmWqYLSe2W/Ik//k2mJNIzZB5vMCDBlYT1"
VULTR_V1_2 = """
{
    "bgp":{
        "ipv4":{
            "my-address":"",
            "my-asn":"",
            "peer-address":"",
            "peer-asn":""
        },
        "ipv6":{
            "my-address":"",
            "my-asn":"",
            "peer-address":"",
            "peer-asn":""
        }
    },
    "hostname":"CLOUDINIT_2",
    "instance-v2-id":"29bea708-2e6e-480a-90ad-0e6b5d5ad62f",
    "instanceid":"42872224",
    "interfaces":[
        {
            "ipv4":{
                "additional":[
                ],
                "address":"45.76.7.171",
                "gateway":"45.76.6.1",
                "netmask":"255.255.254.0"
            },
            "ipv6":{
                "additional":[
                ],
                "address":"2001:19f0:5:28a7:5400:03ff:fe1b:4eca",
                "network":"2001:19f0:5:28a7::",
                "prefix":"64"
            },
            "mac":"56:00:03:1b:4e:ca",
            "network-type":"public"
        },
        {
            "ipv4":{
                "additional":[
                ],
                "address":"10.1.112.3",
                "gateway":"",
                "netmask":"255.255.240.0"
            },
            "ipv6":{
                "additional":[
                ],
                "network":"",
                "prefix":""
            },
            "mac":"5a:00:03:1b:4e:ca",
            "network-type":"private",
            "network-v2-id":"fbbe2b5b-b986-4396-87f5-7246660ccb64",
            "networkid":"net5e7155329d730"
        }
    ],
    "public-keys": "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCvgL32fARIGLNs2w6Kt/t/jYeVgHLQf4VueOwfMZNhXAqe0183eABr40scKb4zTSre9/zMgQHFs/unptRLzLt/hS7ncyioy95Nllg8qw+u/TS71gPu5RozfB0epNzcFdWwro+ibGW3eZO0bOzV8ENaWAfA734YqTDOOVdJYquiU8iLKTP/Rl0RYmCkgQ2tyYpklWVh8DQOa0nenosYihEBOpTgKjtE98ym63EmMkozbEjgt0d8vXGHLUwZ5JvBCubR8YjJ5lL7wmcLf+nx2Dg2zFhhblsF81N+L4K1yx+s0I77hG6bKhOc1X4KoKJJn4bfH7vtMVsPptdAMsFX8W/FvsRMT7/eZ7PHMahC7d2NGCccL6TIK2vxyJxdMO+88mLockKpgixhsbPSq99NurOQiHOhFH4cityQVtH/3qyr4oDYVscAnZsUk93k+2Z/WCYFfHh5HpfWU6dZFgiZlWsJ7Yt6J7ovDUo/aZZmQc1rxsvqcIQQhv5PAOKaIl+mM1c= test@key\\nssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCvgL32fARIGLNs2w6Kt/t/jYeVgHLQf4VueOwfMZNhXAqe0183eABr40scKb4zTSre9/zMgQHFs/unptRLzLt/hS7ncyioy95Nllg8qw+u/TS71gPu5RozfB0epNzcFdWwro+ibGW3eZO0bOzV8ENaWAfA734YqTDOOVdJYquiU8iLKTP/Rl0RYmCkgQ2tyYpklWVh8DQOa0nenosYihEBOpTgKjtE98ym63EmMkozbEjgt0d8vXGHLUwZ5JvBCubR8YjJ5lL7wmcLf+nx2Dg2zFhhblsF81N+L4K1yx+s0I77hG6bKhOc1X4KoKJJn4bfH7vtMVsPptdAMsFX8W/FvsRMT7/eZ7PHMahC7d2NGCccL6TIK2vxyJxdMO+88mLockKpgixhsbPSq99NurOQiHOhFH4cityQVtH/3qyr4oDYVscAnZsUk93k+2Z/WCYFfHh5HpfWU6dZFgiZlWsJ7Yt6J7ovDUo/aZZmQc1rxsvqcIQQhv5PAOKaIl+mM2c= test2@key\\nssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCvgL32fARIGLNs2w6Kt/t/jYeVgHLQf4VueOwfMZNhXAqe0183eABr40scKb4zTSre9/zMgQHFs/unptRLzLt/hS7ncyioy95Nllg8qw+u/TS71gPu5RozfB0epNzcFdWwro+ibGW3eZO0bOzV8ENaWAfA734YqTDOOVdJYquiU8iLKTP/Rl0RYmCkgQ2tyYpklWVh8DQOa0nenosYihEBOpTgKjtE98ym63EmMkozbEjgt0d8vXGHLUwZ5JvBCubR8YjJ5lL7wmcLf+nx2Dg2zFhhblsF81N+L4K1yx+s0I77hG6bKhOc1X4KoKJJn4bfH7vtMVsPptdAMsFX8W/FvsRMT7/eZ7PHMahC7d2NGCccL6TIK2vxyJxdMO+88mLockKpgixhsbPSq99NurOQiHOhFH4cityQVtH/3qyr4oDYVscAnZsUk93k+2Z/WCYFfHh5HpfWU6dZFgiZlWsJ7Yt6J7ovDUo/aZZmQc1rxsvqcIQQhv5PAOKaIl+mM3c= test3@key\\n",
    "region":{
        "regioncode":"EWR"
    },
    "user-defined":[
    ]
}
"""

SSH_KEYS_1 = [
            "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCvgL32fARIGLNs2w6Kt/t/jYeVgHLQf4VueOwfMZNhXAqe0183eABr40scKb4zTSre9/zMgQHFs/unptRLzLt/hS7ncyioy95Nllg8qw+u/TS71gPu5RozfB0epNzcFdWwro+ibGW3eZO0bOzV8ENaWAfA734YqTDOOVdJYquiU8iLKTP/Rl0RYmCkgQ2tyYpklWVh8DQOa0nenosYihEBOpTgKjtE98ym63EmMkozbEjgt0d8vXGHLUwZ5JvBCubR8YjJ5lL7wmcLf+nx2Dg2zFhhblsF81N+L4K1yx+s0I77hG6bKhOc1X4KoKJJn4bfH7vtMVsPptdAMsFX8W/FvsRMT7/eZ7PHMahC7d2NGCccL6TIK2vxyJxdMO+88mLockKpgixhsbPSq99NurOQiHOhFH4cityQVtH/3qyr4oDYVscAnZsUk93k+2Z/WCYFfHh5HpfWU6dZFgiZlWsJ7Yt6J7ovDUo/aZZmQc1rxsvqcIQQhv5PAOKaIl+mM1c= test@key",
            "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCvgL32fARIGLNs2w6Kt/t/jYeVgHLQf4VueOwfMZNhXAqe0183eABr40scKb4zTSre9/zMgQHFs/unptRLzLt/hS7ncyioy95Nllg8qw+u/TS71gPu5RozfB0epNzcFdWwro+ibGW3eZO0bOzV8ENaWAfA734YqTDOOVdJYquiU8iLKTP/Rl0RYmCkgQ2tyYpklWVh8DQOa0nenosYihEBOpTgKjtE98ym63EmMkozbEjgt0d8vXGHLUwZ5JvBCubR8YjJ5lL7wmcLf+nx2Dg2zFhhblsF81N+L4K1yx+s0I77hG6bKhOc1X4KoKJJn4bfH7vtMVsPptdAMsFX8W/FvsRMT7/eZ7PHMahC7d2NGCccL6TIK2vxyJxdMO+88mLockKpgixhsbPSq99NurOQiHOhFH4cityQVtH/3qyr4oDYVscAnZsUk93k+2Z/WCYFfHh5HpfWU6dZFgiZlWsJ7Yt6J7ovDUo/aZZmQc1rxsvqcIQQhv5PAOKaIl+mM2c= test2@key",
            "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCvgL32fARIGLNs2w6Kt/t/jYeVgHLQf4VueOwfMZNhXAqe0183eABr40scKb4zTSre9/zMgQHFs/unptRLzLt/hS7ncyioy95Nllg8qw+u/TS71gPu5RozfB0epNzcFdWwro+ibGW3eZO0bOzV8ENaWAfA734YqTDOOVdJYquiU8iLKTP/Rl0RYmCkgQ2tyYpklWVh8DQOa0nenosYihEBOpTgKjtE98ym63EmMkozbEjgt0d8vXGHLUwZ5JvBCubR8YjJ5lL7wmcLf+nx2Dg2zFhhblsF81N+L4K1yx+s0I77hG6bKhOc1X4KoKJJn4bfH7vtMVsPptdAMsFX8W/FvsRMT7/eZ7PHMahC7d2NGCccL6TIK2vxyJxdMO+88mLockKpgixhsbPSq99NurOQiHOhFH4cityQVtH/3qyr4oDYVscAnZsUk93k+2Z/WCYFfHh5HpfWU6dZFgiZlWsJ7Yt6J7ovDUo/aZZmQc1rxsvqcIQQhv5PAOKaIl+mM3c= test3@key"
]

# Expected generated objects

# Expected config object from generator
EXPECTED_VULTR_CONFIG_1 = {
    'package_upgrade': 'true',
    'disable_root': 0,
    'packages': [
            'ethtool'
    ],
    'ssh_pwauth': 1,
    'chpasswd': {
        'expire': False,
        'list': [
            'root:$6$S2SmujFrCbMsobmu$5PPQqWGvBtONTg3NUW/MDhyz7l3lpYEyQ8w9gOJE.RQPlueITLXJRM4DKEbQHdc/VqxmIR9Urw0jPZ88i4yvB/'
        ]
    },
    'runcmd': [
        'ethtool -L eth0 combined $(nproc --all)'
    ],
    'system_info': {
        'default_user': {
            'name': 'root'
        }
    },
    'network': {
        'version': 1,
        'config': [
            {
                'type': 'nameserver',
                'address': ['108.61.10.10']
            },
            {
                'name': 'eth0',
                'type': 'physical',
                'mac_address': '56:00:03:15:c4:65',
                'accept-ra': 1,
                'subnets': [
                    {'type': 'dhcp', 'control': 'auto'},
                    {'type': 'dhcp6', 'control': 'auto'}
                ]
            }
        ]
    }
}

EXPECTED_VULTR_CONFIG_2 = {
    'package_upgrade': 'true',
    'disable_root': 0,
    'packages': [
            'ethtool'
    ],
    'ssh_pwauth': 1,
    'chpasswd': {
        'expire': False,
        'list': [
            'root:$6$SxXxTd37HQkwxlOM$/z65E0u9ucrHtQBH9y.chMD2GSbKGFKc/QyYkU9WN/pqQ/lOGZL1YmWqYLSe2W/Ik//k2mJNIzZB5vMCDBlYT1'
        ]
    },
    'runcmd': [
        'ethtool -L eth0 combined $(nproc --all)',
        'ethtool -L eth1 combined $(nproc --all)',
        'ip addr add 10.1.112.3/20 dev eth1',
        'ip link set dev eth1 up'
    ],
    'system_info': {
        'default_user': {
            'name': 'root'
        }
    },
    'network': {
        'version': 1,
        'config': [
            {
                'type': 'nameserver',
                'address': ['108.61.10.10']
            },
            {
                'name': 'eth0',
                'type': 'physical',
                'mac_address': '56:00:03:1b:4e:ca',
                'accept-ra': 1,
                'subnets': [
                    {'type': 'dhcp', 'control': 'auto'},
                    {'type': 'dhcp6', 'control': 'auto'}
                ]
            },
            {
                'name': 'eth1',
                'type': 'physical',
                'mac_address': '5a:00:03:1b:4e:ca',
                'accept-ra': 1,
                'subnets': [
                    {
                        "type": "static",
                        "control": "auto",
                        "address": "10.1.112.3",
                        "netmask": "255.255.240.0"
                    }
                ],
            }
        ]
    }
}

# Expected network config object from generator
EXPECTED_VULTR_NETWORK_1 = {
    'version': 1,
    'config': [
        {
            'type': 'nameserver',
            'address': ['108.61.10.10']
        },
        {
            'name': 'eth0',
            'type': 'physical',
            'mac_address': '56:00:03:15:c4:65',
            'accept-ra': 1,
            'subnets': [
                {'type': 'dhcp', 'control': 'auto'},
                {'type': 'dhcp6', 'control': 'auto'}
            ],
        }
    ]
}

EXPECTED_VULTR_NETWORK_2 = {
    'version': 1,
    'config': [
        {
            'type': 'nameserver',
            'address': ['108.61.10.10']
        },
        {
            'name': 'eth0',
            'type': 'physical',
            'mac_address': '56:00:03:1b:4e:ca',
            'accept-ra': 1,
            'subnets': [
                {'type': 'dhcp', 'control': 'auto'},
                {'type': 'dhcp6', 'control': 'auto'}
            ],
        },
        {
            'name': 'eth1',
            'type': 'physical',
            'mac_address': '5a:00:03:1b:4e:ca',
            'accept-ra': 1,
            'subnets': [
                {
                    "type": "static",
                    "control": "auto",
                    "address": "10.1.112.3",
                    "netmask": "255.255.240.0"
                }
            ],
        }
    ]
}


INTERFACE_MAP = {
    '56:00:03:15:c4:65': 'eth0',
    '56:00:03:1b:4e:ca': 'eth0',
    '5a:00:03:1b:4e:ca': 'eth1'
}


class TestDataSourceVultr(CiTestCase):
    def setUp(self):
        super(TestDataSourceVultr, self).setUp()
        self.tmp = self.tmp_dir()


    # Test the datasource itself
    @mock.patch('cloudinit.net.get_interfaces_by_mac')
    @mock.patch('cloudinit.sources.helpers.vultr.is_vultr')
    @mock.patch('cloudinit.sources.helpers.vultr.get_metadata')
    def test_datasource(self, mock_getmeta, mock_isvultr, mock_netmap):
        mock_getmeta.return_value = {
            "enabled": True,
            "v1": json.loads(VULTR_V1_2),
            "root-password": VULTR_ROOT_PASSWORD_2,
            "user-data": "",
            "ssh-keys": '\n'.join(SSH_KEYS_1),
            "startup-script": ""
        }
        mock_isvultr.return_value = True
        mock_netmap.return_value = INTERFACE_MAP

        source = DataSourceVultr.DataSourceVultr(settings.CFG_BUILTIN, None, helpers.Paths({'run_dir': self.tmp}))

        # Test for failure
        self.assertEqual(True, source._get_data())

        # Test instance id
        self.assertEqual("42872224", source.metadata['instanceid'])

        # Test hostname
        self.assertEqual("CLOUDINIT_2", source.metadata['local-hostname'])

        # Test ssh keys
        self.assertEqual(SSH_KEYS_1, source.metadata['public-keys'])

        # Test vendor data generation
        orig_val = self.maxDiff
        self.maxDiff = None
        self.assertEqual("#cloud-config\n" + json.dumps(EXPECTED_VULTR_CONFIG_2), source.vendordata_raw)
        self.maxDiff = orig_val

        # Test network config generation
        self.assertEqual(EXPECTED_VULTR_NETWORK_2, source.network_config)

        # Test network config generation when nothing has changed
        self.assertEqual(None, source.network_config)


    # Test overall config generation
    @mock.patch('cloudinit.net.get_interfaces_by_mac')
    @mock.patch('cloudinit.sources.helpers.vultr.get_metadata')
    def test_get_data_1(self, mock_getmeta, mock_netmap):
        mock_getmeta.return_value = {
            "enabled": True,
            "user-data": "",
            "startup-script": "",
            "v1": json.loads(VULTR_V1_1),
            "root-password": VULTR_ROOT_PASSWORD_1
        }

        mock_netmap.return_value = INTERFACE_MAP

        # Test data
        self.assertEqual(EXPECTED_VULTR_CONFIG_1, vultr.generate_config({}))


    # Test overall config generation
    @mock.patch('cloudinit.net.get_interfaces_by_mac')
    @mock.patch('cloudinit.sources.helpers.vultr.get_metadata')
    def test_get_data_2(self, mock_getmeta, mock_netmap):
        mock_getmeta.return_value = {
            "enabled": True,
            "user-data": "",
            "startup-script": "",
            "v1": json.loads(VULTR_V1_2),
            "root-password": VULTR_ROOT_PASSWORD_2
        }

        mock_netmap.return_value = INTERFACE_MAP

        # Test data with private networking
        self.assertEqual(EXPECTED_VULTR_CONFIG_2, vultr.generate_config({}))


    # Test network config generation
    @mock.patch('cloudinit.net.get_interfaces_by_mac')
    @mock.patch('cloudinit.sources.helpers.vultr.get_metadata')
    def test_network_config(self, mock_getmeta, mock_netmap):
        mock_getmeta.return_value = {
            "enabled": True,
            "v1": json.loads(VULTR_V1_1)
        }

        mock_netmap.return_value = INTERFACE_MAP

        self.assertEqual(EXPECTED_VULTR_NETWORK_1, vultr.generate_network_config({}))


    # Test Private Networking config generation
    @mock.patch('cloudinit.net.get_interfaces_by_mac')
    @mock.patch('cloudinit.sources.helpers.vultr.get_metadata')
    def test_private_network_config(self, mock_getmeta, mock_netmap):
        mock_getmeta.return_value = {
            "enabled": True,
            "v1": json.loads(VULTR_V1_2)
        }

        mock_netmap.return_value = INTERFACE_MAP

        self.assertEqual(EXPECTED_VULTR_NETWORK_2, vultr.generate_network_config({}))

# vi: ts=4 expandtab
