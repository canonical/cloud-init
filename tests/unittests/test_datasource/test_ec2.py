# This file is part of cloud-init. See LICENSE file for license information.

import copy
import httpretty
import json
import mock

from cloudinit import helpers
from cloudinit.sources import DataSourceEc2 as ec2
from cloudinit.tests import helpers as test_helpers


DYNAMIC_METADATA = {
    "instance-identity": {
        "document": json.dumps({
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
            "region": "us-west-2"
        })
    }
}


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
                },
                "06:17:04:d7:26:0A": {
                    "device-number": "1",   # Only IPv4 local config
                    "interface-id": "eni-e44ef49f",
                    "ipv4-associations": {"": "172.3.3.16"},
                    "ipv6s": "",  # No IPv6 config
                    "local-hostname": ("ip-172-3-3-16.us-east-2."
                                       "compute.internal"),
                    "local-ipv4s": "172.3.3.16",
                    "mac": "06:17:04:d7:26:0A",
                    "owner-id": "950047163771",
                    "public-hostname": ("ec2-172-3-3-16.us-east-2."
                                        "compute.amazonaws.com"),
                    "public-ipv4s": "",  # No public ipv4 config
                    "security-group-ids": "sg-5a61d333",
                    "security-groups": "wide-open",
                    "subnet-id": "subnet-20b8565b",
                    "subnet-ipv4-cidr-block": "172.31.16.0/20",
                    "subnet-ipv6-cidr-blocks": "",
                    "vpc-id": "vpc-87e72bee",
                    "vpc-ipv4-cidr-block": "172.31.0.0/16",
                    "vpc-ipv4-cidr-blocks": "172.31.0.0/16",
                    "vpc-ipv6-cidr-blocks": ""
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
    "services": {"domain": "amazonaws.com", "partition": "aws"},
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
        if not isinstance(base_url, str):
            register(base_url, body)
            return
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
            register(base_url, 'not found', status=404)

    def myreg(*argc, **kwargs):
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
        self.tmp = self.tmp_dir()

    def data_url(self, version):
        """Return a metadata url based on the version provided."""
        return '/'.join([self.metadata_addr, version, 'meta-data', ''])

    def _patch_add_cleanup(self, mpath, *args, **kwargs):
        p = mock.patch(mpath, *args, **kwargs)
        p.start()
        self.addCleanup(p.stop)

    def _setup_ds(self, sys_cfg, platform_data, md, md_version=None):
        self.uris = []
        distro = {}
        paths = helpers.Paths({'run_dir': self.tmp})
        if sys_cfg is None:
            sys_cfg = {}
        ds = self.datasource(sys_cfg=sys_cfg, distro=distro, paths=paths)
        if not md_version:
            md_version = ds.min_metadata_version
        if platform_data is not None:
            self._patch_add_cleanup(
                "cloudinit.sources.DataSourceEc2._collect_platform_data",
                return_value=platform_data)

        if md:
            all_versions = (
                [ds.min_metadata_version] + ds.extended_metadata_versions)
            for version in all_versions:
                metadata_url = self.data_url(version)
                if version == md_version:
                    # Register all metadata for desired version
                    register_mock_metaserver(metadata_url, md)
                else:
                    instance_id_url = metadata_url + 'instance-id'
                    if version == ds.min_metadata_version:
                        # Add min_metadata_version service availability check
                        register_mock_metaserver(
                            instance_id_url, DEFAULT_METADATA['instance-id'])
                    else:
                        # Register 404s for all unrequested extended versions
                        register_mock_metaserver(instance_id_url, None)
        return ds

    def test_network_config_property_returns_version_1_network_data(self):
        """network_config property returns network version 1 for metadata.

        Only one device is configured even when multiple exist in metadata.
        """
        ds = self._setup_ds(
            platform_data=self.valid_platform_data,
            sys_cfg={'datasource': {'Ec2': {'strict_id': True}}},
            md=DEFAULT_METADATA)
        find_fallback_path = (
            'cloudinit.sources.DataSourceEc2.net.find_fallback_nic')
        with mock.patch(find_fallback_path) as m_find_fallback:
            m_find_fallback.return_value = 'eth9'
            ds.get_data()

        mac1 = '06:17:04:d7:26:09'  # Defined in DEFAULT_METADATA
        expected = {'version': 1, 'config': [
            {'mac_address': '06:17:04:d7:26:09', 'name': 'eth9',
             'subnets': [{'type': 'dhcp4'}, {'type': 'dhcp6'}],
             'type': 'physical'}]}
        patch_path = (
            'cloudinit.sources.DataSourceEc2.net.get_interfaces_by_mac')
        get_interface_mac_path = (
            'cloudinit.sources.DataSourceEc2.net.get_interface_mac')
        with mock.patch(patch_path) as m_get_interfaces_by_mac:
            with mock.patch(find_fallback_path) as m_find_fallback:
                with mock.patch(get_interface_mac_path) as m_get_mac:
                    m_get_interfaces_by_mac.return_value = {mac1: 'eth9'}
                    m_find_fallback.return_value = 'eth9'
                    m_get_mac.return_value = mac1
                    self.assertEqual(expected, ds.network_config)

    def test_network_config_property_set_dhcp4_on_private_ipv4(self):
        """network_config property configures dhcp4 on private ipv4 nics.

        Only one device is configured even when multiple exist in metadata.
        """
        ds = self._setup_ds(
            platform_data=self.valid_platform_data,
            sys_cfg={'datasource': {'Ec2': {'strict_id': True}}},
            md=DEFAULT_METADATA)
        find_fallback_path = (
            'cloudinit.sources.DataSourceEc2.net.find_fallback_nic')
        with mock.patch(find_fallback_path) as m_find_fallback:
            m_find_fallback.return_value = 'eth9'
            ds.get_data()

        mac1 = '06:17:04:d7:26:0A'  # IPv4 only in DEFAULT_METADATA
        expected = {'version': 1, 'config': [
            {'mac_address': '06:17:04:d7:26:0A', 'name': 'eth9',
             'subnets': [{'type': 'dhcp4'}],
             'type': 'physical'}]}
        patch_path = (
            'cloudinit.sources.DataSourceEc2.net.get_interfaces_by_mac')
        get_interface_mac_path = (
            'cloudinit.sources.DataSourceEc2.net.get_interface_mac')
        with mock.patch(patch_path) as m_get_interfaces_by_mac:
            with mock.patch(find_fallback_path) as m_find_fallback:
                with mock.patch(get_interface_mac_path) as m_get_mac:
                    m_get_interfaces_by_mac.return_value = {mac1: 'eth9'}
                    m_find_fallback.return_value = 'eth9'
                    m_get_mac.return_value = mac1
                    self.assertEqual(expected, ds.network_config)

    def test_network_config_property_is_cached_in_datasource(self):
        """network_config property is cached in DataSourceEc2."""
        ds = self._setup_ds(
            platform_data=self.valid_platform_data,
            sys_cfg={'datasource': {'Ec2': {'strict_id': True}}},
            md=DEFAULT_METADATA)
        ds._network_config = {'cached': 'data'}
        self.assertEqual({'cached': 'data'}, ds.network_config)

    @mock.patch('cloudinit.net.dhcp.maybe_perform_dhcp_discovery')
    def test_network_config_cached_property_refreshed_on_upgrade(self, m_dhcp):
        """Refresh the network_config Ec2 cache if network key is absent.

        This catches an upgrade issue where obj.pkl contained stale metadata
        which lacked newly required network key.
        """
        old_metadata = copy.deepcopy(DEFAULT_METADATA)
        old_metadata.pop('network')
        ds = self._setup_ds(
            platform_data=self.valid_platform_data,
            sys_cfg={'datasource': {'Ec2': {'strict_id': True}}},
            md=old_metadata)
        self.assertTrue(ds.get_data())
        # Provide new revision of metadata that contains network data
        register_mock_metaserver(
            'http://169.254.169.254/2009-04-04/meta-data/', DEFAULT_METADATA)
        mac1 = '06:17:04:d7:26:09'  # Defined in DEFAULT_METADATA
        get_interface_mac_path = (
            'cloudinit.sources.DataSourceEc2.net.get_interface_mac')
        ds.fallback_nic = 'eth9'
        with mock.patch(get_interface_mac_path) as m_get_interface_mac:
            m_get_interface_mac.return_value = mac1
            nc = ds.network_config  # Will re-crawl network metadata
            self.assertIsNotNone(nc)
        self.assertIn('Re-crawl of metadata service', self.logs.getvalue())
        expected = {'version': 1, 'config': [
            {'mac_address': '06:17:04:d7:26:09',
             'name': 'eth9',
             'subnets': [{'type': 'dhcp4'}, {'type': 'dhcp6'}],
             'type': 'physical'}]}
        self.assertEqual(expected, ds.network_config)

    def test_ec2_get_instance_id_refreshes_identity_on_upgrade(self):
        """get_instance-id gets DataSourceEc2Local.identity if not present.

        This handles an upgrade case where the old pickled datasource didn't
        set up self.identity, but 'systemctl cloud-init init' runs
        get_instance_id which traces on missing self.identity. lp:1748354.
        """
        self.datasource = ec2.DataSourceEc2Local
        ds = self._setup_ds(
            platform_data=self.valid_platform_data,
            sys_cfg={'datasource': {'Ec2': {'strict_id': False}}},
            md=DEFAULT_METADATA)
        # Mock 404s on all versions except latest
        all_versions = (
            [ds.min_metadata_version] + ds.extended_metadata_versions)
        for ver in all_versions[:-1]:
            register_mock_metaserver(
                'http://169.254.169.254/{0}/meta-data/instance-id'.format(ver),
                None)
        ds.metadata_address = 'http://169.254.169.254'
        register_mock_metaserver(
            '{0}/{1}/meta-data/'.format(ds.metadata_address, all_versions[-1]),
            DEFAULT_METADATA)
        # Register dynamic/instance-identity document which we now read.
        register_mock_metaserver(
            '{0}/{1}/dynamic/'.format(ds.metadata_address, all_versions[-1]),
            DYNAMIC_METADATA)
        ds._cloud_platform = ec2.Platforms.AWS
        # Setup cached metadata on the Datasource
        ds.metadata = DEFAULT_METADATA
        self.assertEqual('my-identity-id', ds.get_instance_id())

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

    def test_valid_platform_with_strict_false(self):
        """Valid platform data should return true with strict_id false."""
        ds = self._setup_ds(
            platform_data=self.valid_platform_data,
            sys_cfg={'datasource': {'Ec2': {'strict_id': False}}},
            md=DEFAULT_METADATA)
        ret = ds.get_data()
        self.assertTrue(ret)

    def test_unknown_platform_with_strict_true(self):
        """Unknown platform data with strict_id true should return False."""
        uuid = 'ab439480-72bf-11d3-91fc-b8aded755F9a'
        ds = self._setup_ds(
            platform_data={'uuid': uuid, 'uuid_source': 'dmi', 'serial': ''},
            sys_cfg={'datasource': {'Ec2': {'strict_id': True}}},
            md=DEFAULT_METADATA)
        ret = ds.get_data()
        self.assertFalse(ret)

    def test_unknown_platform_with_strict_false(self):
        """Unknown platform data with strict_id false should return True."""
        uuid = 'ab439480-72bf-11d3-91fc-b8aded755F9a'
        ds = self._setup_ds(
            platform_data={'uuid': uuid, 'uuid_source': 'dmi', 'serial': ''},
            sys_cfg={'datasource': {'Ec2': {'strict_id': False}}},
            md=DEFAULT_METADATA)
        ret = ds.get_data()
        self.assertTrue(ret)

    def test_ec2_local_returns_false_on_non_aws(self):
        """DataSourceEc2Local returns False when platform is not AWS."""
        self.datasource = ec2.DataSourceEc2Local
        ds = self._setup_ds(
            platform_data=self.valid_platform_data,
            sys_cfg={'datasource': {'Ec2': {'strict_id': False}}},
            md=DEFAULT_METADATA)
        platform_attrs = [
            attr for attr in ec2.Platforms.__dict__.keys()
            if not attr.startswith('__')]
        for attr_name in platform_attrs:
            platform_name = getattr(ec2.Platforms, attr_name)
            if platform_name != 'AWS':
                ds._cloud_platform = platform_name
                ret = ds.get_data()
                self.assertFalse(ret)
                message = (
                    "Local Ec2 mode only supported on ('AWS',),"
                    ' not {0}'.format(platform_name))
                self.assertIn(message, self.logs.getvalue())

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

    @mock.patch('cloudinit.net.dhcp.EphemeralIPv4Network')
    @mock.patch('cloudinit.net.find_fallback_nic')
    @mock.patch('cloudinit.net.dhcp.maybe_perform_dhcp_discovery')
    @mock.patch('cloudinit.sources.DataSourceEc2.util.is_FreeBSD')
    def test_ec2_local_performs_dhcp_on_non_bsd(self, m_is_bsd, m_dhcp,
                                                m_fallback_nic, m_net):
        """Ec2Local returns True for valid platform data on non-BSD with dhcp.

        DataSourceEc2Local will setup initial IPv4 network via dhcp discovery.
        Then the metadata services is crawled for more network config info.
        When the platform data is valid, return True.
        """

        m_fallback_nic.return_value = 'eth9'
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
        m_dhcp.assert_called_once_with('eth9')
        m_net.assert_called_once_with(
            broadcast='192.168.2.255', interface='eth9', ip='192.168.2.9',
            prefix_or_mask='255.255.255.0', router='192.168.2.1')
        self.assertIn('Crawl of metadata service took', self.logs.getvalue())


class TestConvertEc2MetadataNetworkConfig(test_helpers.CiTestCase):

    def setUp(self):
        super(TestConvertEc2MetadataNetworkConfig, self).setUp()
        self.mac1 = '06:17:04:d7:26:09'
        self.network_metadata = {
            'interfaces': {'macs': {
                self.mac1: {'public-ipv4s': '172.31.2.16'}}}}

    def test_convert_ec2_metadata_network_config_skips_absent_macs(self):
        """Any mac absent from metadata is skipped by network config."""
        macs_to_nics = {self.mac1: 'eth9', 'DE:AD:BE:EF:FF:FF': 'vitualnic2'}

        # DE:AD:BE:EF:FF:FF represented by OS but not in metadata
        expected = {'version': 1, 'config': [
            {'mac_address': self.mac1, 'type': 'physical',
             'name': 'eth9', 'subnets': [{'type': 'dhcp4'}]}]}
        self.assertEqual(
            expected,
            ec2.convert_ec2_metadata_network_config(
                self.network_metadata, macs_to_nics))

    def test_convert_ec2_metadata_network_config_handles_only_dhcp6(self):
        """Config dhcp6 when ipv6s is in metadata for a mac."""
        macs_to_nics = {self.mac1: 'eth9'}
        network_metadata_ipv6 = copy.deepcopy(self.network_metadata)
        nic1_metadata = (
            network_metadata_ipv6['interfaces']['macs'][self.mac1])
        nic1_metadata['ipv6s'] = '2620:0:1009:fd00:e442:c88d:c04d:dc85/64'
        nic1_metadata.pop('public-ipv4s')
        expected = {'version': 1, 'config': [
            {'mac_address': self.mac1, 'type': 'physical',
             'name': 'eth9', 'subnets': [{'type': 'dhcp6'}]}]}
        self.assertEqual(
            expected,
            ec2.convert_ec2_metadata_network_config(
                network_metadata_ipv6, macs_to_nics))

    def test_convert_ec2_metadata_network_config_handles_local_dhcp4(self):
        """Config dhcp4 when there are no public addresses in public-ipv4s."""
        macs_to_nics = {self.mac1: 'eth9'}
        network_metadata_ipv6 = copy.deepcopy(self.network_metadata)
        nic1_metadata = (
            network_metadata_ipv6['interfaces']['macs'][self.mac1])
        nic1_metadata['local-ipv4s'] = '172.3.3.15'
        nic1_metadata.pop('public-ipv4s')
        expected = {'version': 1, 'config': [
            {'mac_address': self.mac1, 'type': 'physical',
             'name': 'eth9', 'subnets': [{'type': 'dhcp4'}]}]}
        self.assertEqual(
            expected,
            ec2.convert_ec2_metadata_network_config(
                network_metadata_ipv6, macs_to_nics))

    def test_convert_ec2_metadata_network_config_handles_absent_dhcp4(self):
        """Config dhcp4 on fallback_nic when there are no ipv4 addresses."""
        macs_to_nics = {self.mac1: 'eth9'}
        network_metadata_ipv6 = copy.deepcopy(self.network_metadata)
        nic1_metadata = (
            network_metadata_ipv6['interfaces']['macs'][self.mac1])
        nic1_metadata['public-ipv4s'] = ''

        # When no ipv4 or ipv6 content but fallback_nic set, set dhcp4 config.
        expected = {'version': 1, 'config': [
            {'mac_address': self.mac1, 'type': 'physical',
             'name': 'eth9', 'subnets': [{'type': 'dhcp4'}]}]}
        self.assertEqual(
            expected,
            ec2.convert_ec2_metadata_network_config(
                network_metadata_ipv6, macs_to_nics, fallback_nic='eth9'))

    def test_convert_ec2_metadata_network_config_handles_local_v4_and_v6(self):
        """When dhcp6 is public and dhcp4 is set to local enable both."""
        macs_to_nics = {self.mac1: 'eth9'}
        network_metadata_both = copy.deepcopy(self.network_metadata)
        nic1_metadata = (
            network_metadata_both['interfaces']['macs'][self.mac1])
        nic1_metadata['ipv6s'] = '2620:0:1009:fd00:e442:c88d:c04d:dc85/64'
        nic1_metadata.pop('public-ipv4s')
        nic1_metadata['local-ipv4s'] = '10.0.0.42'  # Local ipv4 only on vpc
        expected = {'version': 1, 'config': [
            {'mac_address': self.mac1, 'type': 'physical',
             'name': 'eth9',
             'subnets': [{'type': 'dhcp4'}, {'type': 'dhcp6'}]}]}
        self.assertEqual(
            expected,
            ec2.convert_ec2_metadata_network_config(
                network_metadata_both, macs_to_nics))

    def test_convert_ec2_metadata_network_config_handles_dhcp4_and_dhcp6(self):
        """Config both dhcp4 and dhcp6 when both vpc-ipv6 and ipv4 exists."""
        macs_to_nics = {self.mac1: 'eth9'}
        network_metadata_both = copy.deepcopy(self.network_metadata)
        nic1_metadata = (
            network_metadata_both['interfaces']['macs'][self.mac1])
        nic1_metadata['ipv6s'] = '2620:0:1009:fd00:e442:c88d:c04d:dc85/64'
        expected = {'version': 1, 'config': [
            {'mac_address': self.mac1, 'type': 'physical',
             'name': 'eth9',
             'subnets': [{'type': 'dhcp4'}, {'type': 'dhcp6'}]}]}
        self.assertEqual(
            expected,
            ec2.convert_ec2_metadata_network_config(
                network_metadata_both, macs_to_nics))

    def test_convert_ec2_metadata_gets_macs_from_get_interfaces_by_mac(self):
        """Convert Ec2 Metadata calls get_interfaces_by_mac by default."""
        expected = {'version': 1, 'config': [
            {'mac_address': self.mac1, 'type': 'physical',
             'name': 'eth9',
             'subnets': [{'type': 'dhcp4'}]}]}
        patch_path = (
            'cloudinit.sources.DataSourceEc2.net.get_interfaces_by_mac')
        with mock.patch(patch_path) as m_get_interfaces_by_mac:
            m_get_interfaces_by_mac.return_value = {self.mac1: 'eth9'}
            self.assertEqual(
                expected,
                ec2.convert_ec2_metadata_network_config(self.network_metadata))

# vi: ts=4 expandtab
