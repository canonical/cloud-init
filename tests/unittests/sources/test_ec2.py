# This file is part of cloud-init. See LICENSE file for license information.
# pylint: disable=attribute-defined-outside-init

import copy
import json
import logging
from typing import List
from unittest import mock

import pytest
import requests
import responses

from cloudinit import helpers
from cloudinit.net import netplan
from cloudinit.sources import DataSourceEc2 as ec2
from cloudinit.sources import NicOrder
from tests.unittests.helpers import example_netdev
from tests.unittests.util import MockDistro

DYNAMIC_METADATA = {
    "instance-identity": {
        "document": json.dumps(
            {
                "devpayProductCodes": None,
                "marketplaceProductCodes": ["1abc2defghijklm3nopqrs4tu"],
                "availabilityZone": "us-west-2b",
                "privateIp": "10.158.112.84",
                "version": "2017-09-30",
                "instanceId": "my-identity-id",
                "billingProducts": None,
                "instanceType": "t2.micro",
                "accountId": "123456789012",
                "imageId": "ami-5fb8c835",
                "pendingTime": "2016-11-19T16:32:11Z",
                "architecture": "x86_64",
                "kernelId": None,
                "ramdiskId": None,
                "region": "us-west-2",
            }
        )
    }
}


# collected from api version 2016-09-02/ with
# python3 -c 'import json
# from cloudinit.sources.helpers.ec2 import get_instance_metadata as gm
# print(json.dumps(gm("2016-09-02"), indent=1, sort_keys=True))'
# Note that the MAC addresses have been modified to sort in the opposite order
# to the device-number attribute, to test LP: #1876312
DEFAULT_METADATA = {
    "ami-id": "ami-8b92b4ee",
    "ami-launch-index": "0",
    "ami-manifest-path": "(unknown)",
    "block-device-mapping": {"ami": "/dev/sda1", "root": "/dev/sda1"},
    "hostname": "ip-172-31-31-158.us-east-2.compute.internal",
    "instance-action": "none",
    "instance-id": "i-0a33f80f09c96477f",
    "instance-type": "t2.small",
    "local-hostname": "ip-172-3-3-15.us-east-2.compute.internal",
    "local-ipv4": "172.3.3.15",
    "mac": "06:17:04:d7:26:09",
    "metrics": {"vhostmd": '<?xml version="1.0" encoding="UTF-8"?>'},
    "network": {
        "interfaces": {
            "macs": {
                "06:17:04:d7:26:09": {
                    "device-number": "0",
                    "interface-id": "eni-e44ef49e",
                    "ipv4-associations": {"13.59.77.202": "172.3.3.15"},
                    "ipv6s": "2600:1f16:aeb:b20b:9d87:a4af:5cc9:73dc",
                    "local-hostname": (
                        "ip-172-3-3-15.us-east-2.compute.internal"
                    ),
                    "local-ipv4s": "172.3.3.15",
                    "mac": "06:17:04:d7:26:09",
                    "owner-id": "950047163771",
                    "public-hostname": (
                        "ec2-13-59-77-202.us-east-2.compute.amazonaws.com"
                    ),
                    "public-ipv4s": "13.59.77.202",
                    "security-group-ids": "sg-5a61d333",
                    "security-groups": "wide-open",
                    "subnet-id": "subnet-20b8565b",
                    "subnet-ipv4-cidr-block": "172.31.16.0/20",
                    "subnet-ipv6-cidr-blocks": "2600:1f16:aeb:b20b::/64",
                    "vpc-id": "vpc-87e72bee",
                    "vpc-ipv4-cidr-block": "172.31.0.0/16",
                    "vpc-ipv4-cidr-blocks": "172.31.0.0/16",
                    "vpc-ipv6-cidr-blocks": "2600:1f16:aeb:b200::/56",
                },
                "06:17:04:d7:26:08": {
                    "device-number": "1",  # Only IPv4 local config
                    "interface-id": "eni-e44ef49f",
                    "ipv4-associations": {"": "172.3.3.16"},
                    "ipv6s": "",  # No IPv6 config
                    "local-hostname": (
                        "ip-172-3-3-16.us-east-2.compute.internal"
                    ),
                    "local-ipv4s": "172.3.3.16",
                    "mac": "06:17:04:d7:26:08",
                    "owner-id": "950047163771",
                    "public-hostname": (
                        "ec2-172-3-3-16.us-east-2.compute.amazonaws.com"
                    ),
                    "public-ipv4s": "",  # No public ipv4 config
                    "security-group-ids": "sg-5a61d333",
                    "security-groups": "wide-open",
                    "subnet-id": "subnet-20b8565b",
                    "subnet-ipv4-cidr-block": "172.31.16.0/20",
                    "subnet-ipv6-cidr-blocks": "",
                    "vpc-id": "vpc-87e72bee",
                    "vpc-ipv4-cidr-block": "172.31.0.0/16",
                    "vpc-ipv4-cidr-blocks": "172.31.0.0/16",
                    "vpc-ipv6-cidr-blocks": "",
                },
            }
        }
    },
    "placement": {"availability-zone": "us-east-2b"},
    "profile": "default-hvm",
    "public-hostname": "ec2-13-59-77-202.us-east-2.compute.amazonaws.com",
    "public-ipv4": "13.59.77.202",
    "public-keys": {"brickies": ["ssh-rsa AAAAB3Nz....w== brickies"]},
    "reservation-id": "r-01efbc9996bac1bd6",
    "security-groups": "my-wide-open",
    "services": {"domain": "amazonaws.com", "partition": "aws"},
}

# collected from api version 2018-09-24/ with
# python3 -c 'import json
# from cloudinit.sources.helpers.ec2 import get_instance_metadata as gm
# print(json.dumps(gm("2018-09-24"), indent=1, sort_keys=True))'

NIC1_MD_IPV4_IPV6_MULTI_IP = {
    "device-number": "0",
    "interface-id": "eni-0d6335689899ce9cc",
    "ipv4-associations": {"18.218.219.181": "172.31.44.13"},
    "ipv6s": [
        "2600:1f16:292:100:c187:593c:4349:136",
        "2600:1f16:292:100:f153:12a3:c37c:11f9",
        "2600:1f16:292:100:f152:2222:3333:4444",
    ],
    "local-hostname": "ip-172-31-44-13.us-east-2.compute.internal",
    "local-ipv4s": ["172.31.44.13", "172.31.45.70"],
    "mac": "0a:07:84:3d:6e:38",
    "owner-id": "329910648901",
    "public-hostname": "ec2-18-218-219-181.us-east-2.compute.amazonaws.com",
    "public-ipv4s": "18.218.219.181",
    "security-group-ids": "sg-0c387755222ba8d2e",
    "security-groups": "launch-wizard-4",
    "subnet-id": "subnet-9d7ba0d1",
    "subnet-ipv4-cidr-block": "172.31.32.0/20",
    "subnet_ipv6_cidr_blocks": "2600:1f16:292:100::/64",
    "vpc-id": "vpc-a07f62c8",
    "vpc-ipv4-cidr-block": "172.31.0.0/16",
    "vpc-ipv4-cidr-blocks": "172.31.0.0/16",
    "vpc_ipv6_cidr_blocks": "2600:1f16:292:100::/56",
}

NIC2_MD = {
    "device-number": "1",
    "interface-id": "eni-043cdce36ded5e79f",
    "local-hostname": "ip-172-31-47-221.us-east-2.compute.internal",
    "local-ipv4s": "172.31.47.221",
    "mac": "0a:75:69:92:e2:16",
    "owner-id": "329910648901",
    "security-group-ids": "sg-0d68fef37d8cc9b77",
    "security-groups": "launch-wizard-17",
    "subnet-id": "subnet-9d7ba0d1",
    "subnet-ipv4-cidr-block": "172.31.32.0/20",
    "vpc-id": "vpc-a07f62c8",
    "vpc-ipv4-cidr-block": "172.31.0.0/16",
    "vpc-ipv4-cidr-blocks": "172.31.0.0/16",
}

NIC2_MD_IPV4_IPV6_MULTI_IP = {
    "device-number": "1",
    "interface-id": "eni-043cdce36ded5e79f",
    "ipv6s": [
        "2600:1f16:292:100:c187:593c:4349:136",
        "2600:1f16:292:100:f153:12a3:c37c:11f9",
    ],
    "local-hostname": "ip-172-31-47-221.us-east-2.compute.internal",
    "local-ipv4s": "172.31.47.221",
    "mac": "0a:75:69:92:e2:16",
    "owner-id": "329910648901",
    "security-group-ids": "sg-0d68fef37d8cc9b77",
    "security-groups": "launch-wizard-17",
    "subnet-id": "subnet-9d7ba0d1",
    "subnet-ipv4-cidr-block": "172.31.32.0/20",
    "subnet-ipv6-cidr-blocks": "2600:1f16:292:100::/64",
    "vpc-id": "vpc-a07f62c8",
    "vpc-ipv4-cidr-block": "172.31.0.0/16",
    "vpc-ipv4-cidr-blocks": "172.31.0.0/16",
    "vpc-ipv6-cidr-blocks": "2600:1f16:292:100::/56",
}

MULTI_NIC_V6_ONLY_MD = {
    "macs": {
        "02:6b:df:a2:4b:2b": {
            "device-number": "1",
            "interface-id": "eni-0669816d0cf606123",
            "ipv6s": "2600:1f16:67f:f201:8d2e:4d1f:9e80:4ab9",
            "local-hostname": "i-0951b6d0b66337123.us-east-2.compute.internal",
            "mac": "02:6b:df:a2:4b:2b",
            "owner-id": "483410185123",
            "security-group-ids": "sg-0bf34e5c3cde1d123",
            "security-groups": "default",
            "subnet-id": "subnet-0903f279682c66123",
            "subnet-ipv6-cidr-blocks": "2600:1f16:67f:f201:0:0:0:0/64",
            "vpc-id": "vpc-0ac1befb8c824a123",
            "vpc-ipv4-cidr-block": "192.168.0.0/20",
            "vpc-ipv4-cidr-blocks": "192.168.0.0/20",
            "vpc-ipv6-cidr-blocks": "2600:1f16:67f:f200:0:0:0:0/56",
        },
        "02:7c:03:b8:5c:af": {
            "device-number": "0",
            "interface-id": "eni-0f3cddb84c16e1123",
            "ipv6s": "2600:1f16:67f:f201:6613:29a2:dbf7:2f1f",
            "local-hostname": "i-0951b6d0b66337123.us-east-2.compute.internal",
            "mac": "02:7c:03:b8:5c:af",
            "owner-id": "483410185123",
            "security-group-ids": "sg-0bf34e5c3cde1d123",
            "security-groups": "default",
            "subnet-id": "subnet-0903f279682c66123",
            "subnet-ipv6-cidr-blocks": "2600:1f16:67f:f201:0:0:0:0/64",
            "vpc-id": "vpc-0ac1befb8c824a123",
            "vpc-ipv4-cidr-block": "192.168.0.0/20",
            "vpc-ipv4-cidr-blocks": "192.168.0.0/20",
            "vpc-ipv6-cidr-blocks": "2600:1f16:67f:f200:0:0:0:0/56",
        },
    }
}

SECONDARY_IP_METADATA_2018_09_24 = {
    "ami-id": "ami-0986c2ac728528ac2",
    "ami-launch-index": "0",
    "ami-manifest-path": "(unknown)",
    "block-device-mapping": {"ami": "/dev/sda1", "root": "/dev/sda1"},
    "events": {"maintenance": {"history": "[]", "scheduled": "[]"}},
    "hostname": "ip-172-31-44-13.us-east-2.compute.internal",
    "identity-credentials": {
        "ec2": {
            "info": {
                "AccountId": "329910648901",
                "Code": "Success",
                "LastUpdated": "2019-07-06T14:22:56Z",
            }
        }
    },
    "instance-action": "none",
    "instance-id": "i-069e01e8cc43732f8",
    "instance-type": "t2.micro",
    "local-hostname": "ip-172-31-44-13.us-east-2.compute.internal",
    "local-ipv4": "172.31.44.13",
    "mac": "0a:07:84:3d:6e:38",
    "metrics": {"vhostmd": '<?xml version="1.0" encoding="UTF-8"?>'},
    "network": {
        "interfaces": {
            "macs": {
                "0a:07:84:3d:6e:38": NIC1_MD_IPV4_IPV6_MULTI_IP,
            }
        }
    },
    "placement": {"availability-zone": "us-east-2c"},
    "profile": "default-hvm",
    "public-hostname": "ec2-18-218-219-181.us-east-2.compute.amazonaws.com",
    "public-ipv4": "18.218.219.181",
    "public-keys": {"yourkeyname,e": ["ssh-rsa AAAAW...DZ yourkeyname"]},
    "reservation-id": "r-09b4917135cdd33be",
    "security-groups": "launch-wizard-4",
    "services": {"domain": "amazonaws.com", "partition": "aws"},
}

M_PATH = "cloudinit.sources.DataSourceEc2."
M_PATH_NET = "cloudinit.sources.DataSourceEc2.net."

TAGS_METADATA_2021_03_23: dict = {
    **DEFAULT_METADATA,
    "tags": {
        "instance": {
            "Environment": "production",
            "Application": "test",
            "TagWithoutValue": "",
        }
    },
}


@pytest.fixture(autouse=True)
def disable_is_resolvable():
    with mock.patch("cloudinit.sources.DataSourceEc2.util.is_resolvable"):
        yield


def _register_ssh_keys(rfunc, base_url, keys_data):
    r"""handle ssh key inconsistencies.

    public-keys in the ec2 metadata is inconsistently formated compared
    to other entries.
    Given keys_data of {name1: pubkey1, name2: pubkey2}

    This registers the following urls:
       base_url                 0={name1}\n1={name2} # (for each name)
       base_url/                0={name1}\n1={name2} # (for each name)
       base_url/0               openssh-key
       base_url/0/              openssh-key
       base_url/0/openssh-key   {pubkey1}
       base_url/0/openssh-key/  {pubkey1}
       ...
    """

    base_url = base_url.rstrip("/")
    odd_index = "\n".join(
        ["{0}={1}".format(n, name) for n, name in enumerate(sorted(keys_data))]
    )

    rfunc(base_url, odd_index)
    rfunc(base_url + "/", odd_index)

    for n, name in enumerate(sorted(keys_data)):
        val = keys_data[name]
        if isinstance(val, list):
            val = "\n".join(val)
        burl = base_url + "/%s" % n
        rfunc(burl, "openssh-key")
        rfunc(burl + "/", "openssh-key")
        rfunc(burl + "/%s/openssh-key" % name, val)
        rfunc(burl + "/%s/openssh-key/" % name, val)


def register_mock_metaserver(base_url, data, responses_mock=None):
    r"""Register with responses a ec2 metadata like service serving 'data'.

    If given a dictionary, it will populate urls under base_url for
    that dictionary.  For example, input of
       {"instance-id": "i-abc", "mac": "00:16:3e:00:00:00"}
    populates
       base_url  with 'instance-id\nmac'
       base_url/ with 'instance-id\nmac'
       base_url/instance-id with i-abc
       base_url/mac with 00:16:3e:00:00:00
    In the index, references to lists or dictionaries have a trailing /.
    """
    responses_mock = responses_mock or responses

    def register_helper(base_url, body):
        if not isinstance(base_url, str):
            register(base_url, body)
            return
        base_url = base_url.rstrip("/")
        if isinstance(body, str):
            register(base_url, body)
        elif isinstance(body, list):
            register(base_url, "\n".join(body) + "\n")
            register(base_url + "/", "\n".join(body) + "\n")
        elif isinstance(body, dict):
            vals = []
            for k, v in body.items():
                if k == "public-keys":
                    _register_ssh_keys(register, base_url + "/public-keys/", v)
                    continue
                suffix = k.rstrip("/")
                if not isinstance(v, (str, list)):
                    suffix += "/"
                vals.append(suffix)
                url = base_url + "/" + suffix
                register_helper(url, v)
            register(base_url, "\n".join(vals) + "\n")
            register(base_url + "/", "\n".join(vals) + "\n")
        elif body is None:
            register(base_url, "not found", status=404)

    def register(url, body, status=200):
        method = responses.PUT if "latest/api/token" in url else responses.GET
        return responses_mock.add(method, url, body, status=status)

    register_helper(base_url, data)


class TestEc2:
    datasource = ec2.DataSourceEc2
    metadata_addr = datasource.metadata_urls[0]

    valid_platform_data = {
        "uuid": "ec212f79-87d1-2f1d-588f-d86dc0fd5412",
        "serial": "ec212f79-87d1-2f1d-588f-d86dc0fd5412",
    }

    def data_url(self, version, data_item="meta-data"):
        """Return a metadata url based on the version provided."""
        return "/".join([self.metadata_addr, version, data_item])

    def _setup_ds(
        self,
        sys_cfg,
        platform_data,
        md,
        *,
        mocker,
        tmpdir,
        md_version=None,
        distro=None
    ):
        self.uris = []
        distro = distro or mock.MagicMock()
        distro.get_tmp_exec_path = tmpdir
        paths = helpers.Paths({"run_dir": tmpdir})
        if sys_cfg is None:
            sys_cfg = {}
        ds = self.datasource(sys_cfg=sys_cfg, distro=distro, paths=paths)
        mocker.patch("time.sleep")
        if not md_version:
            md_version = ds.min_metadata_version
        if platform_data is not None:
            mocker.patch(
                "cloudinit.sources.DataSourceEc2._collect_platform_data",
                return_value=platform_data,
            )

        if md:
            all_versions = [
                ds.min_metadata_version
            ] + ds.extended_metadata_versions
            token_url = self.data_url("latest", data_item="api/token")
            register_mock_metaserver(token_url, "API-TOKEN", responses)
            for version in all_versions:
                metadata_url = self.data_url(version) + "/"
                if version == md_version:
                    # Register all metadata for desired version
                    register_mock_metaserver(
                        metadata_url,
                        md.get("md", DEFAULT_METADATA),
                        responses,
                    )
                    userdata_url = self.data_url(
                        version, data_item="user-data"
                    )
                    register_mock_metaserver(
                        userdata_url, md.get("ud", ""), responses
                    )
                    identity_url = self.data_url(
                        version, data_item="dynamic/instance-identity"
                    )
                    register_mock_metaserver(
                        identity_url,
                        md.get("id", DYNAMIC_METADATA),
                        responses,
                    )
                else:
                    instance_id_url = metadata_url + "instance-id"
                    if version == ds.min_metadata_version:
                        # Add min_metadata_version service availability check
                        register_mock_metaserver(
                            instance_id_url,
                            DEFAULT_METADATA["instance-id"],
                            responses,
                        )
                    else:
                        # Register 404s for all unrequested extended versions
                        register_mock_metaserver(
                            instance_id_url, None, responses
                        )
        return ds

    @responses.activate
    def test_network_config_property_returns_version_2_network_data(
        self, mocker, tmpdir
    ):
        """network_config property returns network version 2 for metadata"""
        ds = self._setup_ds(
            platform_data=self.valid_platform_data,
            sys_cfg={"datasource": {"Ec2": {"strict_id": True}}},
            md={"md": DEFAULT_METADATA},
            mocker=mocker,
            tmpdir=tmpdir,
        )
        find_fallback_path = M_PATH_NET + "find_fallback_nic"
        with mock.patch(find_fallback_path) as m_find_fallback:
            m_find_fallback.return_value = "eth9"
            ds.get_data()

        mac1 = "06:17:04:d7:26:09"  # Defined in DEFAULT_METADATA
        expected = {
            "version": 2,
            "ethernets": {
                "eth9": {
                    "match": {"macaddress": "06:17:04:d7:26:09"},
                    "set-name": "eth9",
                    "dhcp4": True,
                    "dhcp6": True,
                }
            },
        }
        patch_path = M_PATH_NET + "get_interfaces_by_mac"
        get_interface_mac_path = M_PATH_NET + "get_interface_mac"
        with mock.patch(patch_path) as m_get_interfaces_by_mac:
            with mock.patch(find_fallback_path) as m_find_fallback:
                with mock.patch(get_interface_mac_path) as m_get_mac:
                    m_get_interfaces_by_mac.return_value = {mac1: "eth9"}
                    m_find_fallback.return_value = "eth9"
                    m_get_mac.return_value = mac1
                    assert expected == ds.network_config

    @responses.activate
    def test_network_config_property_set_dhcp4(self, mocker, tmpdir):
        """network_config property configures dhcp4 on nics with local-ipv4s.

        Only one device is configured based on get_interfaces_by_mac even when
        multiple MACs exist in metadata.
        """
        ds = self._setup_ds(
            platform_data=self.valid_platform_data,
            sys_cfg={"datasource": {"Ec2": {"strict_id": True}}},
            md={"md": DEFAULT_METADATA},
            mocker=mocker,
            tmpdir=tmpdir,
        )
        find_fallback_path = M_PATH_NET + "find_fallback_nic"
        with mock.patch(find_fallback_path) as m_find_fallback:
            m_find_fallback.return_value = "eth9"
            ds.get_data()

        mac1 = "06:17:04:d7:26:08"  # IPv4 only in DEFAULT_METADATA
        expected = {
            "version": 2,
            "ethernets": {
                "eth9": {
                    "match": {"macaddress": mac1.lower()},
                    "set-name": "eth9",
                    "dhcp4": True,
                    "dhcp6": False,
                }
            },
        }
        patch_path = M_PATH_NET + "get_interfaces_by_mac"
        get_interface_mac_path = M_PATH_NET + "get_interface_mac"
        with mock.patch(patch_path) as m_get_interfaces_by_mac:
            with mock.patch(find_fallback_path) as m_find_fallback:
                with mock.patch(get_interface_mac_path) as m_get_mac:
                    dhcp_client = ds.distro.dhcp_client
                    dhcp_client.dhcp_discovery.return_value = {
                        "routers": "172.31.1.0"
                    }
                    m_get_interfaces_by_mac.return_value = {mac1: "eth9"}
                    m_find_fallback.return_value = "eth9"
                    m_get_mac.return_value = mac1
                    assert expected == ds.network_config

    @responses.activate
    def test_network_config_property_secondary_private_ips(
        self, mocker, tmpdir
    ):
        """network_config property configures any secondary ipv4 addresses.

        Only one device is configured based on get_interfaces_by_mac even when
        multiple MACs exist in metadata.
        """
        ds = self._setup_ds(
            platform_data=self.valid_platform_data,
            sys_cfg={"datasource": {"Ec2": {"strict_id": True}}},
            md={"md": SECONDARY_IP_METADATA_2018_09_24},
            mocker=mocker,
            tmpdir=tmpdir,
        )
        find_fallback_path = M_PATH_NET + "find_fallback_nic"
        with mock.patch(find_fallback_path) as m_find_fallback:
            m_find_fallback.return_value = "eth9"
            ds.get_data()

        mac1 = "0a:07:84:3d:6e:38"  # 1 secondary IPv4 and 2 secondary IPv6
        expected = {
            "version": 2,
            "ethernets": {
                "eth9": {
                    "match": {"macaddress": mac1},
                    "set-name": "eth9",
                    "addresses": [
                        "172.31.45.70/20",
                        "2600:1f16:292:100:f152:2222:3333:4444/128",
                        "2600:1f16:292:100:f153:12a3:c37c:11f9/128",
                    ],
                    "dhcp4": True,
                    "dhcp6": True,
                }
            },
        }
        patch_path = M_PATH_NET + "get_interfaces_by_mac"
        get_interface_mac_path = M_PATH_NET + "get_interface_mac"
        with mock.patch(patch_path) as m_get_interfaces_by_mac:
            with mock.patch(find_fallback_path) as m_find_fallback:
                with mock.patch(get_interface_mac_path) as m_get_mac:
                    m_get_interfaces_by_mac.return_value = {mac1: "eth9"}
                    m_find_fallback.return_value = "eth9"
                    m_get_mac.return_value = mac1
                    assert expected == ds.network_config

    @responses.activate
    def test_network_config_property_is_cached_in_datasource(
        self, mocker, tmpdir
    ):
        """network_config property is cached in DataSourceEc2."""
        ds = self._setup_ds(
            platform_data=self.valid_platform_data,
            sys_cfg={"datasource": {"Ec2": {"strict_id": True}}},
            md={"md": DEFAULT_METADATA},
            mocker=mocker,
            tmpdir=tmpdir,
        )
        ds._network_config = {"cached": "data"}
        assert {"cached": "data"} == ds.network_config

    @responses.activate
    @mock.patch("cloudinit.net.dhcp.maybe_perform_dhcp_discovery")
    def test_network_config_cached_property_refreshed_on_upgrade(
        self, m_dhcp, caplog, mocker, tmpdir
    ):
        """Refresh the network_config Ec2 cache if network key is absent.

        This catches an upgrade issue where obj.pkl contained stale metadata
        which lacked newly required network key.
        """
        old_metadata = copy.deepcopy(DEFAULT_METADATA)
        old_metadata.pop("network")
        ds = self._setup_ds(
            platform_data=self.valid_platform_data,
            sys_cfg={"datasource": {"Ec2": {"strict_id": True}}},
            md={"md": old_metadata},
            mocker=mocker,
            tmpdir=tmpdir,
        )
        assert True is ds.get_data()

        def _remove_md(resp_list: List) -> None:
            for index, url in enumerate(resp_list):
                try:
                    url = url.url
                except AttributeError:
                    # Can be removed when Bionic is EOL
                    url = url["url"]
                if url.startswith(
                    "http://169.254.169.254/2009-04-04/meta-data/"
                ):
                    del resp_list[index]

        # Workaround https://github.com/getsentry/responses/issues/212
        if hasattr(responses, "_urls"):
            # Can be removed when Bionic is EOL
            _remove_md(responses._urls)
        elif hasattr(responses, "_default_mock") and hasattr(
            responses._default_mock, "_urls"
        ):
            # Can be removed when Bionic is EOL
            _remove_md(responses._default_mock._urls)
        elif hasattr(responses, "_matches"):
            # Can be removed when Focal is EOL
            _remove_md(responses._matches)
        elif hasattr(responses, "_default_mock") and hasattr(
            responses._default_mock, "_matches"
        ):
            # Can be removed when Focal is EOL
            _remove_md(responses._default_mock._matches)

        # Provide new revision of metadata that contains network data
        register_mock_metaserver(
            "http://169.254.169.254/2009-04-04/meta-data/",
            DEFAULT_METADATA,
            responses,
        )
        mac1 = "06:17:04:d7:26:09"  # Defined in DEFAULT_METADATA
        get_interface_mac_path = M_PATH_NET + "get_interfaces_by_mac"
        ds.distro.fallback_nic = "eth9"
        with mock.patch(get_interface_mac_path) as m_get_interfaces_by_mac:
            m_get_interfaces_by_mac.return_value = {mac1: "eth9"}
            nc = ds.network_config  # Will re-crawl network metadata
        assert None is not nc
        assert "Refreshing stale metadata from prior to upgrade" in caplog.text
        expected = {
            "version": 2,
            "ethernets": {
                "eth9": {
                    "match": {"macaddress": mac1},
                    "set-name": "eth9",
                    "dhcp4": True,
                    "dhcp6": True,
                }
            },
        }
        assert expected == ds.network_config

    @responses.activate
    def test_ec2_get_instance_id_refreshes_identity_on_upgrade(
        self, mocker, tmpdir
    ):
        """get_instance-id gets DataSourceEc2Local.identity if not present.

        This handles an upgrade case where the old pickled datasource didn't
        set up self.identity, but 'systemctl cloud-init init' runs
        get_instance_id which traces on missing self.identity. lp:1748354.
        """
        self.datasource = ec2.DataSourceEc2Local
        ds = self._setup_ds(
            platform_data=self.valid_platform_data,
            sys_cfg={"datasource": {"Ec2": {"strict_id": False}}},
            md={"md": DEFAULT_METADATA},
            mocker=mocker,
            tmpdir=tmpdir,
        )
        # Mock 404s on all versions except latest
        all_versions = [
            ds.min_metadata_version
        ] + ds.extended_metadata_versions
        for ver in all_versions[:-1]:
            register_mock_metaserver(
                "http://[fd00:ec2::254]/{0}/meta-data/instance-id".format(ver),
                None,
                responses,
            )

        ds.metadata_address = "http://[fd00:ec2::254]"
        register_mock_metaserver(
            "{0}/{1}/meta-data/".format(ds.metadata_address, all_versions[-1]),
            DEFAULT_METADATA,
            responses,
        )
        # Register dynamic/instance-identity document which we now read.
        register_mock_metaserver(
            "{0}/{1}/dynamic/".format(ds.metadata_address, all_versions[-1]),
            DYNAMIC_METADATA,
            responses,
        )
        ds._cloud_name = ec2.CloudNames.AWS
        # Setup cached metadata on the Datasource
        ds.metadata = DEFAULT_METADATA
        assert "my-identity-id" == ds.get_instance_id()

    @responses.activate
    def test_classic_instance_true(self, mocker, tmpdir):
        """If no vpc-id in metadata, is_classic_instance must return true."""
        md_copy = copy.deepcopy(DEFAULT_METADATA)
        ifaces_md = md_copy.get("network", {}).get("interfaces", {})
        for _mac, mac_data in ifaces_md.get("macs", {}).items():
            if "vpc-id" in mac_data:
                del mac_data["vpc-id"]

        ds = self._setup_ds(
            platform_data=self.valid_platform_data,
            sys_cfg={"datasource": {"Ec2": {"strict_id": False}}},
            md={"md": md_copy},
            mocker=mocker,
            tmpdir=tmpdir,
        )
        assert True is ds.get_data()
        assert True is ds.is_classic_instance()

    @responses.activate
    def test_classic_instance_false(self, mocker, tmpdir):
        """If vpc-id in metadata, is_classic_instance must return false."""
        ds = self._setup_ds(
            platform_data=self.valid_platform_data,
            sys_cfg={"datasource": {"Ec2": {"strict_id": False}}},
            md={"md": DEFAULT_METADATA},
            mocker=mocker,
            tmpdir=tmpdir,
        )
        assert True is ds.get_data()
        assert False is ds.is_classic_instance()

    @responses.activate
    def test_aws_inaccessible_imds_service_fails_with_retries(
        self, mocker, tmpdir
    ):
        """Inaccessibility of http://169.254.169.254 are retried."""
        ds = self._setup_ds(
            platform_data=self.valid_platform_data,
            sys_cfg={"datasource": {"Ec2": {"strict_id": False}}},
            md=None,
            tmpdir=tmpdir,
            mocker=mocker,
        )

        conn_error = requests.exceptions.ConnectionError(
            "[Errno 113] no route to host"
        )

        mock_success = mock.MagicMock(contents=b"fakesuccess")
        mock_success.ok.return_value = True

        with mock.patch("cloudinit.url_helper.readurl") as m_readurl:
            # yikes, this endpoint needs help
            m_readurl.side_effect = (
                conn_error,
                conn_error,
                mock_success,
            )
            with mock.patch("cloudinit.url_helper.time.sleep"):
                assert True is ds.wait_for_metadata_service()

        # Just one /latest/api/token request
        assert 3 == len(m_readurl.call_args_list)
        for readurl_call in m_readurl.call_args_list:
            assert "latest/api/token" in readurl_call[0][0]

    @responses.activate
    def test_aws_token_403_fails_without_retries(self, caplog, mocker, tmpdir):
        """Verify that 403s fetching AWS tokens are not retried."""
        ds = self._setup_ds(
            platform_data=self.valid_platform_data,
            sys_cfg={"datasource": {"Ec2": {"strict_id": False}}},
            md=None,
            mocker=mocker,
            tmpdir=tmpdir,
        )

        token_url = self.data_url("latest", data_item="api/token")
        responses.add(responses.PUT, token_url, status=403)
        assert False is ds.get_data()
        # Just one /latest/api/token request
        expected_logs = [
            (
                mock.ANY,
                logging.WARNING,
                "Ec2 IMDS endpoint returned a 403 error. HTTP endpoint is"
                " disabled. Aborting.",
            ),
            (
                mock.ANY,
                logging.WARNING,
                "IMDS's HTTP endpoint is probably disabled",
            ),
        ]
        for log in expected_logs:
            assert log in caplog.record_tuples

    @responses.activate
    def test_aws_token_redacted(self, caplog, mocker, tmpdir):
        """Verify that aws tokens are redacted when logged."""
        ds = self._setup_ds(
            platform_data=self.valid_platform_data,
            sys_cfg={"datasource": {"Ec2": {"strict_id": False}}},
            md={"md": DEFAULT_METADATA},
            mocker=mocker,
            tmpdir=tmpdir,
        )
        assert True is ds.get_data()
        all_logs = caplog.text.splitlines()
        REDACT_TTL = "'X-aws-ec2-metadata-token-ttl-seconds': 'REDACTED'"
        REDACT_TOK = "'X-aws-ec2-metadata-token': 'REDACTED'"
        logs_with_redacted_ttl = [log for log in all_logs if REDACT_TTL in log]
        logs_with_redacted = [log for log in all_logs if REDACT_TOK in log]
        logs_with_token = [log for log in all_logs if "API-TOKEN" in log]
        assert 1 == len(logs_with_redacted_ttl)
        assert 83 == len(logs_with_redacted)
        assert 0 == len(logs_with_token)

    @responses.activate
    @mock.patch("cloudinit.net.dhcp.maybe_perform_dhcp_discovery")
    def test_valid_platform_with_strict_true(self, m_dhcp, mocker, tmpdir):
        """Valid platform data should return true with strict_id true."""
        ds = self._setup_ds(
            platform_data=self.valid_platform_data,
            sys_cfg={"datasource": {"Ec2": {"strict_id": True}}},
            md={"md": DEFAULT_METADATA},
            mocker=mocker,
            tmpdir=tmpdir,
        )
        ret = ds.get_data()
        assert True is ret
        assert 0 == m_dhcp.call_count
        assert "aws" == ds.cloud_name
        assert "ec2" == ds.platform_type
        assert "metadata (%s)" % ds.metadata_address == ds.subplatform

    @responses.activate
    def test_valid_platform_with_strict_false(self, mocker, tmpdir):
        """Valid platform data should return true with strict_id false."""
        ds = self._setup_ds(
            platform_data=self.valid_platform_data,
            sys_cfg={"datasource": {"Ec2": {"strict_id": False}}},
            md={"md": DEFAULT_METADATA},
            mocker=mocker,
            tmpdir=tmpdir,
        )
        ret = ds.get_data()
        assert True is ret

    @responses.activate
    def test_unknown_platform_with_strict_true(self, mocker, tmpdir):
        """Unknown platform data with strict_id true should return False."""
        uuid = "ab439480-72bf-11d3-91fc-b8aded755F9a"
        ds = self._setup_ds(
            platform_data={"uuid": uuid, "serial": ""},
            sys_cfg={"datasource": {"Ec2": {"strict_id": True}}},
            md={"md": DEFAULT_METADATA},
            mocker=mocker,
            tmpdir=tmpdir,
        )
        ret = ds.get_data()
        assert False is ret

    @responses.activate
    def test_unknown_platform_with_strict_false(self, mocker, tmpdir):
        """Unknown platform data with strict_id false should return True."""
        uuid = "ab439480-72bf-11d3-91fc-b8aded755F9a"
        ds = self._setup_ds(
            platform_data={"uuid": uuid, "serial": ""},
            sys_cfg={"datasource": {"Ec2": {"strict_id": False}}},
            md={"md": DEFAULT_METADATA},
            mocker=mocker,
            tmpdir=tmpdir,
        )
        ret = ds.get_data()
        assert True is ret

    @responses.activate
    def test_ec2_local_returns_false_on_non_aws(self, caplog, mocker, tmpdir):
        """DataSourceEc2Local returns False when platform is not AWS."""
        self.datasource = ec2.DataSourceEc2Local
        ds = self._setup_ds(
            platform_data=self.valid_platform_data,
            sys_cfg={"datasource": {"Ec2": {"strict_id": False}}},
            md={"md": DEFAULT_METADATA},
            mocker=mocker,
            tmpdir=tmpdir,
        )
        platform_attrs = [
            attr
            for attr in ec2.CloudNames.__dict__.keys()
            if not attr.startswith("__")
        ]
        for attr_name in platform_attrs:
            platform_name = getattr(ec2.CloudNames, attr_name)
            if platform_name not in ["aws", "outscale"]:
                ds._cloud_name = platform_name
                ret = ds.get_data()
                assert "ec2" == ds.platform_type
                assert False is ret
                message = (
                    "Local Ec2 mode only supported on ('aws', 'outscale'),"
                    " not {0}".format(platform_name)
                )
                assert message in caplog.text

    @mock.patch("cloudinit.sources.DataSourceEc2.util.is_FreeBSD")
    def test_ec2_local_returns_false_on_bsd(
        self, m_is_freebsd, caplog, mocker, tmpdir
    ):
        """DataSourceEc2Local returns False on BSD.

        FreeBSD dhclient doesn't support dhclient -sf to run in a sandbox.
        """
        m_is_freebsd.return_value = True
        self.datasource = ec2.DataSourceEc2Local
        ds = self._setup_ds(
            platform_data=self.valid_platform_data,
            sys_cfg={"datasource": {"Ec2": {"strict_id": False}}},
            md={"md": DEFAULT_METADATA},
            mocker=mocker,
            tmpdir=tmpdir,
        )
        ret = ds.get_data()
        assert False is ret
        assert (
            "FreeBSD doesn't support running dhclient with -sf" in caplog.text
        )

    @responses.activate
    @pytest.mark.usefixtures("disable_netdev_info")
    @mock.patch("cloudinit.net.ephemeral.EphemeralIPv6Network")
    @mock.patch("cloudinit.net.ephemeral.EphemeralIPv4Network")
    @mock.patch("cloudinit.distros.net.find_fallback_nic")
    @mock.patch("cloudinit.net.ephemeral.maybe_perform_dhcp_discovery")
    @mock.patch("cloudinit.sources.DataSourceEc2.util.is_FreeBSD")
    def test_ec2_local_performs_dhcp_on_non_bsd(
        self,
        m_is_bsd,
        m_dhcp,
        m_fallback_nic,
        m_net4,
        m_net6,
        caplog,
        mocker,
        tmpdir,
        disable_netdev_info,
    ):
        """Ec2Local returns True for valid platform data on non-BSD with dhcp.

        DataSourceEc2Local will setup initial IPv4 network via dhcp discovery.
        Then the metadata services is crawled for more network config info.
        When the platform data is valid, return True.
        """

        m_fallback_nic.return_value = "eth9"
        m_is_bsd.return_value = False
        m_dhcp.return_value = {
            "interface": "eth9",
            "fixed-address": "192.168.2.9",
            "routers": "192.168.2.1",
            "subnet-mask": "255.255.255.0",
            "broadcast-address": "192.168.2.255",
        }
        self.datasource = ec2.DataSourceEc2Local
        ds = self._setup_ds(
            platform_data=self.valid_platform_data,
            sys_cfg={"datasource": {"Ec2": {"strict_id": False}}},
            md={"md": DEFAULT_METADATA},
            distro=MockDistro("", {}, {}),
            mocker=mocker,
            tmpdir=tmpdir,
        )

        ret = ds.get_data()
        assert True is ret
        m_dhcp.assert_called_once_with(ds.distro, "eth9", None)
        m_net4.assert_called_once_with(
            ds.distro,
            broadcast="192.168.2.255",
            interface_addrs_before_dhcp=example_netdev,
            interface="eth9",
            ip="192.168.2.9",
            prefix_or_mask="255.255.255.0",
            router="192.168.2.1",
            static_routes=None,
        )
        assert "Crawl of metadata service " in caplog.text

    @responses.activate
    def test_get_instance_tags(self, mocker, tmpdir):
        ds = self._setup_ds(
            platform_data=self.valid_platform_data,
            sys_cfg={"datasource": {"Ec2": {"strict_id": False}}},
            md={"md": TAGS_METADATA_2021_03_23},
            mocker=mocker,
            tmpdir=tmpdir,
        )
        assert True is ds.get_data()
        assert "tags" in ds.metadata
        assert "instance" in ds.metadata["tags"]
        instance_tags = ds.metadata["tags"]["instance"]
        assert instance_tags["Application"] == "test"
        assert instance_tags["Environment"] == "production"


class TestGetSecondaryAddresses:
    mac = "06:17:04:d7:26:ff"

    def test_md_with_no_secondary_addresses(self):
        """Empty list is returned when nic metadata contains no secondary ip"""
        assert [] == ec2.get_secondary_addresses(NIC2_MD, self.mac)

    def test_md_with_secondary_v4_and_v6_addresses(self):
        """All secondary addresses are returned from nic metadata"""
        assert [
            "172.31.45.70/20",
            "2600:1f16:292:100:f152:2222:3333:4444/128",
            "2600:1f16:292:100:f153:12a3:c37c:11f9/128",
        ] == ec2.get_secondary_addresses(NIC1_MD_IPV4_IPV6_MULTI_IP, self.mac)

    def test_invalid_ipv4_ipv6_cidr_metadata_logged_with_defaults(
        self, caplog
    ):
        """Any invalid subnet-ipv(4|6)-cidr-block values use defaults"""
        invalid_cidr_md = copy.deepcopy(NIC1_MD_IPV4_IPV6_MULTI_IP)
        invalid_cidr_md["subnet-ipv4-cidr-block"] = "something-unexpected"
        invalid_cidr_md["subnet-ipv6-cidr-block"] = "not/sure/what/this/is"
        assert [
            "172.31.45.70/24",
            "2600:1f16:292:100:f152:2222:3333:4444/128",
            "2600:1f16:292:100:f153:12a3:c37c:11f9/128",
        ] == ec2.get_secondary_addresses(invalid_cidr_md, self.mac)
        expected_logs = [
            (
                mock.ANY,
                logging.WARNING,
                "Could not parse subnet-ipv4-cidr-block"
                " something-unexpected for mac 06:17:04:d7:26:ff."
                " ipv4 network config prefix defaults to /24",
            ),
            (
                mock.ANY,
                logging.WARNING,
                "Could not parse subnet-ipv6-cidr-block"
                " not/sure/what/this/is for mac 06:17:04:d7:26:ff."
                " ipv6 network config prefix defaults to /128",
            ),
        ]
        for log in expected_logs:
            assert log in caplog.record_tuples


class TestBuildNicOrder:
    @pytest.mark.parametrize(
        ["macs_metadata", "macs_to_nics", "default_nic_order", "expected"],
        [
            pytest.param({}, {}, NicOrder.MAC, {}, id="all_empty"),
            pytest.param(
                {}, {}, NicOrder.NIC_NAME, {}, id="all_empty_sort_by_nic_name"
            ),
            pytest.param(
                {},
                {"0a:f7:8d:96:f2:a1": "eth0"},
                NicOrder.MAC,
                {},
                id="empty_macs_metadata",
            ),
            pytest.param(
                {
                    "0a:0d:dd:44:cd:7b": {
                        "device-number": "0",
                        "mac": "0a:0d:dd:44:cd:7b",
                    }
                },
                {},
                NicOrder.MAC,
                {},
                id="empty_macs",
            ),
            pytest.param(
                {
                    "0a:0d:dd:44:cd:7b": {
                        "mac": "0a:0d:dd:44:cd:7b",
                    },
                    "0a:f7:8d:96:f2:a1": {
                        "mac": "0a:f7:8d:96:f2:a1",
                    },
                },
                {"0a:f7:8d:96:f2:a1": "eth0", "0a:0d:dd:44:cd:7b": "eth1"},
                NicOrder.MAC,
                {"0a:0d:dd:44:cd:7b": 0, "0a:f7:8d:96:f2:a1": 1},
                id="no-device-number-info",
            ),
            pytest.param(
                {
                    "0a:0d:dd:44:cd:7b": {
                        "mac": "0a:0d:dd:44:cd:7b",
                    },
                    "0a:f7:8d:96:f2:a1": {
                        "mac": "0a:f7:8d:96:f2:a1",
                    },
                },
                {"0a:f7:8d:96:f2:a1": "eth0"},
                NicOrder.MAC,
                {"0a:f7:8d:96:f2:a1": 0},
                id="no-device-number-info-subset",
            ),
            pytest.param(
                {
                    "0a:0d:dd:44:cd:7b": {
                        "device-number": "0",
                        "mac": "0a:0d:dd:44:cd:7b",
                    },
                    "0a:f7:8d:96:f2:a1": {
                        "device-number": "1",
                        "mac": "0a:f7:8d:96:f2:a1",
                    },
                },
                {"0a:0d:dd:44:cd:7b": "eth0", "0a:f7:8d:96:f2:a1": "eth1"},
                NicOrder.MAC,
                {"0a:0d:dd:44:cd:7b": 0, "0a:f7:8d:96:f2:a1": 1},
                id="device-numbers",
            ),
            pytest.param(
                {
                    "0a:0d:dd:44:cd:7b": {
                        "network-card": "0",
                        "device-number": "0",
                        "mac": "0a:0d:dd:44:cd:7b",
                    },
                    "0a:f7:8d:96:f2:a1": {
                        "network-card": "1",
                        "device-number": "1",
                        "mac": "0a:f7:8d:96:f2:a1",
                    },
                    "0a:f7:8d:96:f2:a2": {
                        "network-card": "2",
                        "device-number": "1",
                        "mac": "0a:f7:8d:96:f2:a1",
                    },
                },
                {
                    "0a:0d:dd:44:cd:7b": "eth0",
                    "0a:f7:8d:96:f2:a1": "eth1",
                    "0a:f7:8d:96:f2:a2": "eth2",
                },
                NicOrder.MAC,
                {
                    "0a:0d:dd:44:cd:7b": 0,
                    "0a:f7:8d:96:f2:a1": 1,
                    "0a:f7:8d:96:f2:a2": 2,
                },
                id="network-cardes",
            ),
            pytest.param(
                {
                    "0a:0d:dd:44:cd:7b": {
                        "network-card": "0",
                        "device-number": "0",
                        "mac": "0a:0d:dd:44:cd:7b",
                    },
                    "0a:f7:8d:96:f2:a1": {
                        "network-card": "1",
                        "device-number": "1",
                        "mac": "0a:f7:8d:96:f2:a1",
                    },
                    "0a:f7:8d:96:f2:a2": {
                        "device-number": "1",
                        "mac": "0a:f7:8d:96:f2:a2",
                    },
                },
                {
                    "0a:0d:dd:44:cd:7b": "eth0",
                    "0a:f7:8d:96:f2:a1": "eth1",
                    "0a:f7:8d:96:f2:a2": "eth2",
                },
                NicOrder.MAC,
                {
                    "0a:0d:dd:44:cd:7b": 0,
                    "0a:f7:8d:96:f2:a1": 1,
                    "0a:f7:8d:96:f2:a2": 2,
                },
                id="network-card-partially-missing",
            ),
            pytest.param(
                {
                    "0a:0d:dd:44:cd:7b": {
                        "mac": "0a:0d:dd:44:cd:7b",
                    },
                    "0a:f7:8d:96:f2:a1": {
                        "mac": "0a:f7:8d:96:f2:a1",
                    },
                },
                {"0a:f7:8d:96:f2:a9": "eth0"},
                NicOrder.MAC,
                {},
                id="macs-not-in-md",
            ),
            pytest.param(
                {},
                {"0a:f7:8d:96:f2:a1": "eth0"},
                NicOrder.NIC_NAME,
                {},
                id="empty_macs_metadata_sort_by_nic_name",
            ),
            pytest.param(
                {
                    "0a:0d:dd:44:cd:7b": {
                        "device-number": "0",
                        "mac": "0a:0d:dd:44:cd:7b",
                    }
                },
                {},
                NicOrder.NIC_NAME,
                {},
                id="empty_macs_sort_by_nic_name",
            ),
            pytest.param(
                {
                    "0a:0d:dd:44:cd:7b": {
                        "mac": "0a:0d:dd:44:cd:7b",
                    },
                    "0a:f7:8d:96:f2:a1": {
                        "mac": "0a:f7:8d:96:f2:a1",
                    },
                },
                {"0a:f7:8d:96:f2:a1": "eth0", "0a:0d:dd:44:cd:7b": "eth1"},
                NicOrder.NIC_NAME,
                {"0a:f7:8d:96:f2:a1": 0, "0a:0d:dd:44:cd:7b": 1},
                id="no-device-number-info-sort-by-nic-name",
            ),
            pytest.param(
                {
                    "0a:0d:dd:44:cd:7b": {
                        "mac": "0a:0d:dd:44:cd:7b",
                    },
                    "0a:f7:8d:96:f2:a1": {
                        "mac": "0a:f7:8d:96:f2:a1",
                    },
                },
                {"0a:f7:8d:96:f2:a1": "eth0"},
                NicOrder.NIC_NAME,
                {"0a:f7:8d:96:f2:a1": 0},
                id="no-device-number-info-subset-sort-by-nic-name",
            ),
            pytest.param(
                {
                    "0a:0d:dd:44:cd:7b": {
                        "device-number": "0",
                        "mac": "0a:0d:dd:44:cd:7b",
                    },
                    "0a:f7:8d:96:f2:a1": {
                        "device-number": "1",
                        "mac": "0a:f7:8d:96:f2:a1",
                    },
                },
                {"0a:0d:dd:44:cd:7b": "eth0", "0a:f7:8d:96:f2:a1": "eth1"},
                NicOrder.NIC_NAME,
                {"0a:0d:dd:44:cd:7b": 0, "0a:f7:8d:96:f2:a1": 1},
                id="device-numbers-sort-by-nic-name",
            ),
            pytest.param(
                {
                    "0a:0d:dd:44:cd:7b": {
                        "network-card": "1",
                        "device-number": "1",
                        "mac": "0a:0d:dd:44:cd:7b",
                    },
                    "0a:f7:8d:96:f2:a1": {
                        "network-card": "0",
                        "device-number": "0",
                        "mac": "0a:f7:8d:96:f2:a1",
                    },
                    "0a:f7:8d:96:f2:a2": {
                        "network-card": "2",
                        "device-number": "1",
                        "mac": "0a:f7:8d:96:f2:a1",
                    },
                },
                {
                    "0a:f7:8d:96:f2:a1": "eth0",
                    "0a:0d:dd:44:cd:7b": "eth1",
                    "0a:f7:8d:96:f2:a2": "eth2",
                },
                NicOrder.MAC,
                {
                    "0a:f7:8d:96:f2:a1": 0,
                    "0a:0d:dd:44:cd:7b": 1,
                    "0a:f7:8d:96:f2:a2": 2,
                },
                id="network-cardes-sort-by-nic-name",
            ),
            pytest.param(
                {
                    "0a:0d:dd:44:cd:7b": {
                        "network-card": "0",
                        "device-number": "0",
                        "mac": "0a:0d:dd:44:cd:7b",
                    },
                    "0a:f7:8d:96:f2:a1": {
                        "network-card": "1",
                        "device-number": "1",
                        "mac": "0a:f7:8d:96:f2:a1",
                    },
                    "0a:f7:8d:96:f2:a2": {
                        "device-number": "1",
                        "mac": "0a:f7:8d:96:f2:a2",
                    },
                },
                {
                    "0a:0d:dd:44:cd:7b": "eth0",
                    "0a:f7:8d:96:f2:a1": "eth1",
                    "0a:f7:8d:96:f2:a2": "eth2",
                },
                NicOrder.NIC_NAME,
                {
                    "0a:0d:dd:44:cd:7b": 0,
                    "0a:f7:8d:96:f2:a1": 1,
                    "0a:f7:8d:96:f2:a2": 2,
                },
                id="network-card-partially-missing-sort-by-nic-name",
            ),
            pytest.param(
                {
                    "0a:0d:dd:44:cd:7b": {
                        "mac": "0a:0d:dd:44:cd:7b",
                    },
                    "0a:f7:8d:96:f2:a1": {
                        "mac": "0a:f7:8d:96:f2:a1",
                    },
                },
                {"0a:f7:8d:96:f2:a9": "eth0"},
                NicOrder.NIC_NAME,
                {},
                id="macs-not-in-md-sort-by-nic-name",
            ),
            pytest.param(
                {
                    "0a:0d:dd:44:cd:7b": {
                        "mac": "0a:0d:dd:44:cd:7b",
                    },
                    "0a:f7:8d:96:f2:a1": {
                        "mac": "0a:f7:8d:96:f2:a1",
                    },
                    "0a:f7:8d:96:f2:a2": {
                        "mac": "0a:f7:8d:96:f2:a1",
                    },
                },
                {
                    "0a:f7:8d:96:f2:a1": "eth0",
                    "0a:0d:dd:44:cd:7b": "eth1",
                    "0a:f7:8d:96:f2:a2": "eth2",
                },
                NicOrder.NIC_NAME,
                {
                    "0a:f7:8d:96:f2:a1": 0,
                    "0a:0d:dd:44:cd:7b": 1,
                    "0a:f7:8d:96:f2:a2": 2,
                },
                id="no-device-number-info-subset-sort-by-nic-name",
            ),
        ],
    )
    def test_build_nic_order(
        self, macs_metadata, macs_to_nics, default_nic_order, expected
    ):
        assert expected == ec2._build_nic_order(
            macs_metadata, macs_to_nics, default_nic_order
        )


class TestConvertEc2MetadataNetworkConfig:
    MAC1 = "06:17:04:d7:26:09"

    @classmethod
    def get_network_metadata(cls):
        interface_dict = copy.deepcopy(
            DEFAULT_METADATA["network"]["interfaces"]["macs"][cls.MAC1]
        )
        # These tests are written assuming the base interface doesn't have IPv6
        interface_dict.pop("ipv6s")
        return {"interfaces": {"macs": {cls.MAC1: interface_dict}}}

    def test_convert_ec2_metadata_network_config_skips_absent_macs(self):
        """Any mac absent from metadata is skipped by network config."""
        macs_to_nics = {self.MAC1: "eth9", "DE:AD:BE:EF:FF:FF": "vitualnic2"}

        # DE:AD:BE:EF:FF:FF represented by OS but not in metadata
        expected = {
            "version": 2,
            "ethernets": {
                "eth9": {
                    "match": {"macaddress": self.MAC1},
                    "set-name": "eth9",
                    "dhcp4": True,
                    "dhcp6": False,
                }
            },
        }
        distro = mock.Mock()
        assert expected == ec2.convert_ec2_metadata_network_config(
            self.get_network_metadata(), distro, macs_to_nics
        )

    def test_convert_ec2_metadata_network_config_handles_only_dhcp6(self):
        """Config dhcp6 when ipv6s is in metadata for a mac."""
        macs_to_nics = {self.MAC1: "eth9"}
        network_metadata_ipv6 = copy.deepcopy(self.get_network_metadata())
        nic1_metadata = network_metadata_ipv6["interfaces"]["macs"][self.MAC1]
        nic1_metadata["ipv6s"] = "2620:0:1009:fd00:e442:c88d:c04d:dc85/64"
        nic1_metadata.pop("public-ipv4s")
        expected = {
            "version": 2,
            "ethernets": {
                "eth9": {
                    "match": {"macaddress": self.MAC1},
                    "set-name": "eth9",
                    "dhcp4": True,
                    "dhcp6": True,
                }
            },
        }
        distro = mock.Mock()
        assert expected == ec2.convert_ec2_metadata_network_config(
            network_metadata_ipv6, distro, macs_to_nics
        )

    def test_convert_ec2_metadata_network_config_local_only_dhcp4(self):
        """Config dhcp4 when there are no public addresses in public-ipv4s."""
        macs_to_nics = {self.MAC1: "eth9"}
        network_metadata_ipv6 = copy.deepcopy(self.get_network_metadata())
        nic1_metadata = network_metadata_ipv6["interfaces"]["macs"][self.MAC1]
        nic1_metadata["local-ipv4s"] = "172.3.3.15"
        nic1_metadata.pop("public-ipv4s")
        expected = {
            "version": 2,
            "ethernets": {
                "eth9": {
                    "match": {"macaddress": self.MAC1},
                    "set-name": "eth9",
                    "dhcp4": True,
                    "dhcp6": False,
                }
            },
        }
        distro = mock.Mock()
        assert expected == ec2.convert_ec2_metadata_network_config(
            network_metadata_ipv6, distro, macs_to_nics
        )

    def test_convert_ec2_metadata_network_config_handles_absent_dhcp4(self):
        """Config dhcp4 on fallback_nic when there are no ipv4 addresses."""
        macs_to_nics = {self.MAC1: "eth9"}
        network_metadata_ipv6 = copy.deepcopy(self.get_network_metadata())
        nic1_metadata = network_metadata_ipv6["interfaces"]["macs"][self.MAC1]
        nic1_metadata["public-ipv4s"] = ""

        # When no ipv4 or ipv6 content but fallback_nic set, set dhcp4 config.
        expected = {
            "version": 2,
            "ethernets": {
                "eth9": {
                    "match": {"macaddress": self.MAC1},
                    "set-name": "eth9",
                    "dhcp4": True,
                    "dhcp6": False,
                }
            },
        }
        distro = mock.Mock()
        assert expected == ec2.convert_ec2_metadata_network_config(
            network_metadata_ipv6, distro, macs_to_nics
        )

    def test_convert_ec2_metadata_network_config_handles_local_v4_and_v6(self):
        """When ipv6s and local-ipv4s are non-empty, enable dhcp6 and dhcp4."""
        macs_to_nics = {self.MAC1: "eth9"}
        network_metadata_both = copy.deepcopy(self.get_network_metadata())
        nic1_metadata = network_metadata_both["interfaces"]["macs"][self.MAC1]
        nic1_metadata["ipv6s"] = "2620:0:1009:fd00:e442:c88d:c04d:dc85/64"
        nic1_metadata.pop("public-ipv4s")
        nic1_metadata["local-ipv4s"] = "10.0.0.42"  # Local ipv4 only on vpc
        expected = {
            "version": 2,
            "ethernets": {
                "eth9": {
                    "match": {"macaddress": self.MAC1},
                    "set-name": "eth9",
                    "dhcp4": True,
                    "dhcp6": True,
                }
            },
        }
        distro = mock.Mock()
        assert expected == ec2.convert_ec2_metadata_network_config(
            network_metadata_both, distro, macs_to_nics
        )

    def test_convert_ec2_metadata_network_config_multi_nics_ipv4(self):
        """DHCP route-metric increases on secondary NICs for IPv4 and IPv6.
        Source-routing configured for secondary NICs (routing-policy and extra
        routing table)."""
        mac2 = "06:17:04:d7:26:08"
        macs_to_nics = {self.MAC1: "eth9", mac2: "eth10"}
        network_metadata_both = copy.deepcopy(self.get_network_metadata())
        # Add 2nd nic info
        network_metadata_both["interfaces"]["macs"][mac2] = NIC2_MD
        nic1_metadata = network_metadata_both["interfaces"]["macs"][self.MAC1]
        nic1_metadata["ipv6s"] = "2620:0:1009:fd00:e442:c88d:c04d:dc85/64"
        nic1_metadata.pop("public-ipv4s")  # No public-ipv4 IPs in cfg
        nic1_metadata["local-ipv4s"] = "10.0.0.42"  # Local ipv4 only on vpc
        expected = {
            "version": 2,
            "ethernets": {
                "eth9": {
                    "match": {"macaddress": self.MAC1},
                    "set-name": "eth9",
                    "dhcp4": True,
                    "dhcp4-overrides": {"route-metric": 100},
                    "dhcp6": True,
                    "dhcp6-overrides": {"route-metric": 100},
                },
                "eth10": {
                    "match": {"macaddress": mac2},
                    "set-name": "eth10",
                    "dhcp4": True,
                    "dhcp4-overrides": {
                        "route-metric": 200,
                        "use-routes": True,
                    },
                    "dhcp6": False,
                    "routes": [
                        # via DHCP gateway
                        {"to": "0.0.0.0/0", "via": "172.31.1.0", "table": 101},
                        # to NIC2_MD["subnet-ipv4-cidr-block"]
                        {"to": "172.31.32.0/20", "table": 101},
                    ],
                    "routing-policy": [
                        # NIC2_MD["local-ipv4s"]
                        {"from": "172.31.47.221", "table": 101}
                    ],
                },
            },
        }
        distro = mock.Mock()
        distro.network_renderer = netplan.Renderer()
        distro.dhcp_client.dhcp_discovery.return_value = {
            "routers": "172.31.1.0"
        }
        assert expected == ec2.convert_ec2_metadata_network_config(
            network_metadata_both, distro, macs_to_nics
        )

    def test_convert_ec2_metadata_network_config_multi_nics_ipv4_ipv6_multi_ip(
        self,
    ):
        """DHCP route-metric increases on secondary NICs for IPv4 and IPv6.
        Source-routing configured for secondary NICs (routing-policy and extra
        routing table)."""
        mac2 = "06:17:04:d7:26:08"
        macs_to_nics = {self.MAC1: "eth9", mac2: "eth10"}
        network_metadata_both = copy.deepcopy(self.get_network_metadata())
        # Add 2nd nic info
        network_metadata_both["interfaces"]["macs"][
            mac2
        ] = NIC2_MD_IPV4_IPV6_MULTI_IP
        nic1_metadata = network_metadata_both["interfaces"]["macs"][self.MAC1]
        nic1_metadata["ipv6s"] = "2620:0:1009:fd00:e442:c88d:c04d:dc85/64"
        nic1_metadata.pop("public-ipv4s")  # No public-ipv4 IPs in cfg
        nic1_metadata["local-ipv4s"] = "10.0.0.42"  # Local ipv4 only on vpc
        expected = {
            "version": 2,
            "ethernets": {
                "eth9": {
                    "dhcp4": True,
                    "dhcp4-overrides": {"route-metric": 100},
                    "dhcp6": True,
                    "match": {"macaddress": "06:17:04:d7:26:09"},
                    "set-name": "eth9",
                    "dhcp6-overrides": {"route-metric": 100},
                },
                "eth10": {
                    "dhcp4": True,
                    "dhcp4-overrides": {
                        "route-metric": 200,
                        "use-routes": True,
                    },
                    "dhcp6": True,
                    "match": {"macaddress": "06:17:04:d7:26:08"},
                    "set-name": "eth10",
                    "routes": [
                        # via DHCP gateway
                        {"to": "0.0.0.0/0", "via": "172.31.1.0", "table": 101},
                        # to NIC2_MD["subnet-ipv4-cidr-block"]
                        {"to": "172.31.32.0/20", "table": 101},
                        # to NIC2_MD["subnet-ipv6-cidr-blocks"]
                        {"to": "2600:1f16:292:100::/64", "table": 101},
                    ],
                    "routing-policy": [
                        # NIC2_MD["local-ipv4s"]
                        {"from": "172.31.47.221", "table": 101},
                        {
                            "from": "2600:1f16:292:100:c187:593c:4349:136",
                            "table": 101,
                        },
                        {
                            "from": "2600:1f16:292:100:f153:12a3:c37c:11f9",
                            "table": 101,
                        },
                    ],
                    "dhcp6-overrides": {
                        "route-metric": 200,
                        "use-routes": True,
                    },
                    "addresses": ["2600:1f16:292:100:f153:12a3:c37c:11f9/128"],
                },
            },
        }
        distro = mock.Mock()
        distro.network_renderer = netplan.Renderer()
        distro.dhcp_client.dhcp_discovery.return_value = {
            "routers": "172.31.1.0"
        }
        assert expected == ec2.convert_ec2_metadata_network_config(
            network_metadata_both, distro, macs_to_nics
        )

    def test_convert_ec2_metadata_network_config_multi_nics_ipv6_only(self):
        """Like above, but only ipv6s are present in metadata."""
        macs_to_nics = {
            "02:7c:03:b8:5c:af": "eth0",
            "02:6b:df:a2:4b:2b": "eth1",
        }
        mac_data = copy.deepcopy(MULTI_NIC_V6_ONLY_MD)
        network_metadata = {"interfaces": mac_data}
        expected = {
            "version": 2,
            "ethernets": {
                "eth0": {
                    "dhcp4": True,
                    "dhcp4-overrides": {"route-metric": 100},
                    "dhcp6": True,
                    "match": {"macaddress": "02:7c:03:b8:5c:af"},
                    "set-name": "eth0",
                    "dhcp6-overrides": {"route-metric": 100},
                },
                "eth1": {
                    "dhcp4": True,
                    "dhcp4-overrides": {
                        "route-metric": 200,
                        "use-routes": True,
                    },
                    "dhcp6": True,
                    "match": {"macaddress": "02:6b:df:a2:4b:2b"},
                    "set-name": "eth1",
                    "routes": [
                        {"to": "2600:1f16:67f:f201:0:0:0:0/64", "table": 101},
                    ],
                    "routing-policy": [
                        {
                            "from": "2600:1f16:67f:f201:8d2e:4d1f:9e80:4ab9",
                            "table": 101,
                        },
                    ],
                    "dhcp6-overrides": {
                        "route-metric": 200,
                        "use-routes": True,
                    },
                },
            },
        }
        distro = mock.Mock()
        distro.network_renderer = netplan.Renderer()
        assert expected == ec2.convert_ec2_metadata_network_config(
            network_metadata, distro, macs_to_nics
        )
        distro.dhcp_client.dhcp_discovery.assert_not_called()

    def test_convert_ec2_metadata_network_config_handles_dhcp4_and_dhcp6(self):
        """Config both dhcp4 and dhcp6 when both vpc-ipv6 and ipv4 exists."""
        macs_to_nics = {self.MAC1: "eth9"}
        network_metadata_both = copy.deepcopy(self.get_network_metadata())
        nic1_metadata = network_metadata_both["interfaces"]["macs"][self.MAC1]
        nic1_metadata["ipv6s"] = "2620:0:1009:fd00:e442:c88d:c04d:dc85/64"
        expected = {
            "version": 2,
            "ethernets": {
                "eth9": {
                    "match": {"macaddress": self.MAC1},
                    "set-name": "eth9",
                    "dhcp4": True,
                    "dhcp6": True,
                }
            },
        }
        distro = mock.Mock()
        assert expected == ec2.convert_ec2_metadata_network_config(
            network_metadata_both, distro, macs_to_nics
        )

    def test_convert_ec2_metadata_gets_macs_from_get_interfaces_by_mac(self):
        """Convert Ec2 Metadata calls get_interfaces_by_mac by default."""
        expected = {
            "version": 2,
            "ethernets": {
                "eth9": {
                    "match": {"macaddress": self.MAC1},
                    "set-name": "eth9",
                    "dhcp4": True,
                    "dhcp6": False,
                }
            },
        }
        patch_path = M_PATH_NET + "get_interfaces_by_mac"
        distro = mock.Mock()
        with mock.patch(patch_path) as m_get_interfaces_by_mac:
            m_get_interfaces_by_mac.return_value = {self.MAC1: "eth9"}
            assert expected == ec2.convert_ec2_metadata_network_config(
                self.get_network_metadata(), distro
            )


class TestIdentifyPlatform:
    def collmock(self, **kwargs):
        """return non-special _collect_platform_data updated with changes."""
        unspecial = {
            "asset_tag": "3857-0037-2746-7462-1818-3997-77",
            "serial": "H23-C4J3JV-R6",
            "uuid": "81c7e555-6471-4833-9551-1ab366c4cfd2",
            "vendor": "tothecloud",
            "product_name": "cloudproduct",
        }
        unspecial.update(**kwargs)
        return unspecial

    @mock.patch("cloudinit.sources.DataSourceEc2._collect_platform_data")
    def test_identify_aws(self, m_collect):
        """aws should be identified if uuid starts with ec2"""
        m_collect.return_value = self.collmock(
            uuid="ec2E1916-9099-7CAF-FD21-012345ABCDEF"
        )
        assert ec2.CloudNames.AWS == ec2.identify_platform()

    @mock.patch("cloudinit.sources.DataSourceEc2._collect_platform_data")
    def test_identify_aws_endian(self, m_collect):
        """aws should be identified if uuid starts with ec2"""
        m_collect.return_value = self.collmock(
            uuid="45E12AEC-DCD1-B213-94ED-012345ABCDEF"
        )
        assert ec2.CloudNames.AWS == ec2.identify_platform()

    @mock.patch("cloudinit.sources.DataSourceEc2._collect_platform_data")
    def test_identify_aliyun(self, m_collect):
        """aliyun should be identified if product name equals to
        Alibaba Cloud ECS
        """
        m_collect.return_value = self.collmock(
            product_name="Alibaba Cloud ECS"
        )
        assert ec2.CloudNames.ALIYUN == ec2.identify_platform()

    @mock.patch("cloudinit.sources.DataSourceEc2._collect_platform_data")
    def test_identify_zstack(self, m_collect):
        """zstack should be identified if chassis-asset-tag
        ends in .zstack.io
        """
        m_collect.return_value = self.collmock(asset_tag="123456.zstack.io")
        assert ec2.CloudNames.ZSTACK == ec2.identify_platform()

    @mock.patch("cloudinit.sources.DataSourceEc2._collect_platform_data")
    def test_identify_zstack_full_domain_only(self, m_collect):
        """zstack asset-tag matching should match only on
        full domain boundary.
        """
        m_collect.return_value = self.collmock(asset_tag="123456.buzzstack.io")
        assert ec2.CloudNames.UNKNOWN == ec2.identify_platform()

    @mock.patch("cloudinit.sources.DataSourceEc2._collect_platform_data")
    def test_identify_e24cloud(self, m_collect):
        """e24cloud identified if vendor is e24cloud"""
        m_collect.return_value = self.collmock(vendor="e24cloud")
        assert ec2.CloudNames.E24CLOUD == ec2.identify_platform()

    @mock.patch("cloudinit.sources.DataSourceEc2._collect_platform_data")
    def test_identify_e24cloud_negative(self, m_collect):
        """e24cloud identified if vendor is e24cloud"""
        m_collect.return_value = self.collmock(vendor="e24cloudyday")
        assert ec2.CloudNames.UNKNOWN == ec2.identify_platform()

    # Outscale
    @mock.patch("cloudinit.sources.DataSourceEc2._collect_platform_data")
    def test_identify_outscale(self, m_collect):
        """Should return true if the dmi product data has expected value."""
        m_collect.return_value = self.collmock(
            vendor="3DS Outscale".lower(),
            product_name="3DS Outscale VM".lower(),
        )
        assert ec2.CloudNames.OUTSCALE == ec2.identify_platform()

    @mock.patch("cloudinit.sources.DataSourceEc2._collect_platform_data")
    def test_false_on_wrong_sys_vendor(self, m_collect):
        """Should return false on empty value returned."""
        m_collect.return_value = self.collmock(
            vendor="Not 3DS Outscale".lower(),
            product_name="3DS Outscale VM".lower(),
        )
        assert ec2.CloudNames.UNKNOWN == ec2.identify_platform()

    @mock.patch("cloudinit.sources.DataSourceEc2._collect_platform_data")
    def test_false_on_wrong_product_name(self, m_collect):
        """Should return false on an unrelated string."""
        m_collect.return_value = self.collmock(
            vendor="3DS Outscale".lower(),
            product_name="Not 3DS Outscale VM".lower(),
        )
        assert ec2.CloudNames.UNKNOWN == ec2.identify_platform()
