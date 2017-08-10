# This file is part of cloud-init. See LICENSE file for license information.

import httpretty
import mock

from .. import helpers as test_helpers
from cloudinit import helpers
from cloudinit.sources import DataSourceEc2 as ec2


# collected from api version 2016-09-02/ with
# python3 -c 'import json
# from cloudinit.ec2_utils import get_instance_metadata as gm
# print(json.dumps(gm("2016-09-02"), indent=1, sort_keys=True))'
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
    "metrics": {"vhostmd": "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"},
    "network": {
        "interfaces": {
            "macs": {
                "06:17:04:d7:26:09": {
                    "device-number": "0",
                    "interface-id": "eni-e44ef49e",
                    "ipv4-associations": {"13.59.77.202": "172.3.3.15"},
                    "ipv6s": "2600:1f16:aeb:b20b:9d87:a4af:5cc9:73dc",
                    "local-hostname": ("ip-172-3-3-15.us-east-2."
                                       "compute.internal"),
                    "local-ipv4s": "172.3.3.15",
                    "mac": "06:17:04:d7:26:09",
                    "owner-id": "950047163771",
                    "public-hostname": ("ec2-13-59-77-202.us-east-2."
                                        "compute.amazonaws.com"),
                    "public-ipv4s": "13.59.77.202",
                    "security-group-ids": "sg-5a61d333",
                    "security-groups": "wide-open",
                    "subnet-id": "subnet-20b8565b",
                    "subnet-ipv4-cidr-block": "172.31.16.0/20",
                    "subnet-ipv6-cidr-blocks": "2600:1f16:aeb:b20b::/64",
                    "vpc-id": "vpc-87e72bee",
                    "vpc-ipv4-cidr-block": "172.31.0.0/16",
                    "vpc-ipv4-cidr-blocks": "172.31.0.0/16",
                    "vpc-ipv6-cidr-blocks": "2600:1f16:aeb:b200::/56"
                }
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
    "services": {"domain": "amazonaws.com", "partition": "aws"}
}


def _register_ssh_keys(rfunc, base_url, keys_data):
    """handle ssh key inconsistencies.

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
    odd_index = '\n'.join(
        ["{0}={1}".format(n, name)
         for n, name in enumerate(sorted(keys_data))])

    rfunc(base_url, odd_index)
    rfunc(base_url + "/", odd_index)

    for n, name in enumerate(sorted(keys_data)):
        val = keys_data[name]
        if isinstance(val, list):
            val = '\n'.join(val)
        burl = base_url + "/%s" % n
        rfunc(burl, "openssh-key")
        rfunc(burl + "/", "openssh-key")
        rfunc(burl + "/%s/openssh-key" % name, val)
        rfunc(burl + "/%s/openssh-key/" % name, val)


def register_mock_metaserver(base_url, data):
    """Register with httpretty a ec2 metadata like service serving 'data'.

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
    def register_helper(register, base_url, body):
        base_url = base_url.rstrip("/")
        if isinstance(body, str):
            register(base_url, body)
        elif isinstance(body, list):
            register(base_url, '\n'.join(body) + '\n')
            register(base_url + '/', '\n'.join(body) + '\n')
        elif isinstance(body, dict):
            vals = []
            for k, v in body.items():
                if k == 'public-keys':
                    _register_ssh_keys(
                        register, base_url + '/public-keys/', v)
                    continue
                suffix = k.rstrip("/")
                if not isinstance(v, (str, list)):
                    suffix += "/"
                vals.append(suffix)
                url = base_url + '/' + suffix
                register_helper(register, url, v)
            register(base_url, '\n'.join(vals) + '\n')
            register(base_url + '/', '\n'.join(vals) + '\n')
        elif body is None:
            register(base_url, 'not found', status_code=404)

    def myreg(*argc, **kwargs):
        # print("register_url(%s, %s)" % (argc, kwargs))
        return httpretty.register_uri(httpretty.GET, *argc, **kwargs)

    register_helper(myreg, base_url, data)


class TestEc2(test_helpers.HttprettyTestCase):
    with_logs = True

    valid_platform_data = {
        'uuid': 'ec212f79-87d1-2f1d-588f-d86dc0fd5412',
        'uuid_source': 'dmi',
        'serial': 'ec212f79-87d1-2f1d-588f-d86dc0fd5412',
    }

    def setUp(self):
        super(TestEc2, self).setUp()
        self.datasource = ec2.DataSourceEc2
        self.metadata_addr = self.datasource.metadata_urls[0]

    @property
    def metadata_url(self):
        return '/'.join([
            self.metadata_addr,
            self.datasource.min_metadata_version, 'meta-data', ''])

    @property
    def userdata_url(self):
        return '/'.join([
            self.metadata_addr,
            self.datasource.min_metadata_version, 'user-data'])

    def _patch_add_cleanup(self, mpath, *args, **kwargs):
        p = mock.patch(mpath, *args, **kwargs)
        p.start()
        self.addCleanup(p.stop)

    def _setup_ds(self, sys_cfg, platform_data, md, ud=None):
        distro = {}
        paths = helpers.Paths({})
        if sys_cfg is None:
            sys_cfg = {}
        ds = self.datasource(sys_cfg=sys_cfg, distro=distro, paths=paths)
        if platform_data is not None:
            self._patch_add_cleanup(
                "cloudinit.sources.DataSourceEc2._collect_platform_data",
                return_value=platform_data)

        if md:
            register_mock_metaserver(self.metadata_url, md)
            register_mock_metaserver(self.userdata_url, ud)

        return ds

    @httpretty.activate
    @mock.patch('cloudinit.net.dhcp.maybe_perform_dhcp_discovery')
    def test_valid_platform_with_strict_true(self, m_dhcp):
        """Valid platform data should return true with strict_id true."""
        ds = self._setup_ds(
            platform_data=self.valid_platform_data,
            sys_cfg={'datasource': {'Ec2': {'strict_id': True}}},
            md=DEFAULT_METADATA)
        ret = ds.get_data()
        self.assertTrue(ret)
        self.assertEqual(0, m_dhcp.call_count)

    @httpretty.activate
    def test_valid_platform_with_strict_false(self):
        """Valid platform data should return true with strict_id false."""
        ds = self._setup_ds(
            platform_data=self.valid_platform_data,
            sys_cfg={'datasource': {'Ec2': {'strict_id': False}}},
            md=DEFAULT_METADATA)
        ret = ds.get_data()
        self.assertTrue(ret)

    @httpretty.activate
    def test_unknown_platform_with_strict_true(self):
        """Unknown platform data with strict_id true should return False."""
        uuid = 'ab439480-72bf-11d3-91fc-b8aded755F9a'
        ds = self._setup_ds(
            platform_data={'uuid': uuid, 'uuid_source': 'dmi', 'serial': ''},
            sys_cfg={'datasource': {'Ec2': {'strict_id': True}}},
            md=DEFAULT_METADATA)
        ret = ds.get_data()
        self.assertFalse(ret)

    @httpretty.activate
    def test_unknown_platform_with_strict_false(self):
        """Unknown platform data with strict_id false should return True."""
        uuid = 'ab439480-72bf-11d3-91fc-b8aded755F9a'
        ds = self._setup_ds(
            platform_data={'uuid': uuid, 'uuid_source': 'dmi', 'serial': ''},
            sys_cfg={'datasource': {'Ec2': {'strict_id': False}}},
            md=DEFAULT_METADATA)
        ret = ds.get_data()
        self.assertTrue(ret)

    @httpretty.activate
    @mock.patch('cloudinit.sources.DataSourceEc2.util.is_FreeBSD')
    def test_ec2_local_returns_false_on_bsd(self, m_is_freebsd):
        """DataSourceEc2Local returns False on BSD.

        FreeBSD dhclient doesn't support dhclient -sf to run in a sandbox.
        """
        m_is_freebsd.return_value = True
        self.datasource = ec2.DataSourceEc2Local
        ds = self._setup_ds(
            platform_data=self.valid_platform_data,
            sys_cfg={'datasource': {'Ec2': {'strict_id': False}}},
            md=DEFAULT_METADATA)
        ret = ds.get_data()
        self.assertFalse(ret)
        self.assertIn(
            "FreeBSD doesn't support running dhclient with -sf",
            self.logs.getvalue())

    @httpretty.activate
    @mock.patch('cloudinit.net.EphemeralIPv4Network')
    @mock.patch('cloudinit.net.dhcp.maybe_perform_dhcp_discovery')
    @mock.patch('cloudinit.sources.DataSourceEc2.util.is_FreeBSD')
    def test_ec2_local_performs_dhcp_on_non_bsd(self, m_is_bsd, m_dhcp, m_net):
        """Ec2Local returns True for valid platform data on non-BSD with dhcp.

        DataSourceEc2Local will setup initial IPv4 network via dhcp discovery.
        Then the metadata services is crawled for more network config info.
        When the platform data is valid, return True.
        """
        m_is_bsd.return_value = False
        m_dhcp.return_value = [{
            'interface': 'eth9', 'fixed-address': '192.168.2.9',
            'routers': '192.168.2.1', 'subnet-mask': '255.255.255.0',
            'broadcast-address': '192.168.2.255'}]
        self.datasource = ec2.DataSourceEc2Local
        ds = self._setup_ds(
            platform_data=self.valid_platform_data,
            sys_cfg={'datasource': {'Ec2': {'strict_id': False}}},
            md=DEFAULT_METADATA)
        ret = ds.get_data()
        self.assertTrue(ret)
        m_dhcp.assert_called_once_with()
        m_net.assert_called_once_with(
            broadcast='192.168.2.255', interface='eth9', ip='192.168.2.9',
            prefix_or_mask='255.255.255.0', router='192.168.2.1')
        self.assertIn('Crawl of metadata service took', self.logs.getvalue())


# vi: ts=4 expandtab
