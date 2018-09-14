# This file is part of cloud-init. See LICENSE file for license information.

from copy import copy, deepcopy
import json
import os

from cloudinit import helpers
from cloudinit.net import eni
from cloudinit.net import network_state
from cloudinit import settings
from cloudinit.sources import DataSourceConfigDrive as ds
from cloudinit.sources.helpers import openstack
from cloudinit import util

from cloudinit.tests.helpers import CiTestCase, ExitStack, mock, populate_dir


PUBKEY = u'ssh-rsa AAAAB3NzaC1....sIkJhq8wdX+4I3A4cYbYP ubuntu@server-460\n'
EC2_META = {
    'ami-id': 'ami-00000001',
    'ami-launch-index': 0,
    'ami-manifest-path': 'FIXME',
    'block-device-mapping': {
        'ami': 'sda1',
        'ephemeral0': 'sda2',
        'root': '/dev/sda1',
        'swap': 'sda3'},
    'hostname': 'sm-foo-test.novalocal',
    'instance-action': 'none',
    'instance-id': 'i-00000001',
    'instance-type': 'm1.tiny',
    'local-hostname': 'sm-foo-test.novalocal',
    'local-ipv4': None,
    'placement': {'availability-zone': 'nova'},
    'public-hostname': 'sm-foo-test.novalocal',
    'public-ipv4': '',
    'public-keys': {'0': {'openssh-key': PUBKEY}},
    'reservation-id': 'r-iru5qm4m',
    'security-groups': ['default']
}
USER_DATA = b'#!/bin/sh\necho This is user data\n'
OSTACK_META = {
    'availability_zone': 'nova',
    'files': [{'content_path': '/content/0000', 'path': '/etc/foo.cfg'},
              {'content_path': '/content/0001', 'path': '/etc/bar/bar.cfg'}],
    'hostname': 'sm-foo-test.novalocal',
    'meta': {'dsmode': 'local', 'my-meta': 'my-value'},
    'name': 'sm-foo-test',
    'public_keys': {'mykey': PUBKEY},
    'uuid': 'b0fa911b-69d4-4476-bbe2-1c92bff6535c'}

CONTENT_0 = b'This is contents of /etc/foo.cfg\n'
CONTENT_1 = b'# this is /etc/bar/bar.cfg\n'
NETWORK_DATA = {
    'services': [
        {'type': 'dns', 'address': '199.204.44.24'},
        {'type': 'dns', 'address': '199.204.47.54'}
    ],
    'links': [
        {'vif_id': '2ecc7709-b3f7-4448-9580-e1ec32d75bbd',
         'ethernet_mac_address': 'fa:16:3e:69:b0:58',
         'type': 'ovs', 'mtu': None, 'id': 'tap2ecc7709-b3'},
        {'vif_id': '2f88d109-5b57-40e6-af32-2472df09dc33',
         'ethernet_mac_address': 'fa:16:3e:d4:57:ad',
         'type': 'ovs', 'mtu': None, 'id': 'tap2f88d109-5b'},
        {'vif_id': '1a5382f8-04c5-4d75-ab98-d666c1ef52cc',
         'ethernet_mac_address': 'fa:16:3e:05:30:fe',
         'type': 'ovs', 'mtu': None, 'id': 'tap1a5382f8-04', 'name': 'nic0'}
    ],
    'networks': [
        {'link': 'tap2ecc7709-b3', 'type': 'ipv4_dhcp',
         'network_id': '6d6357ac-0f70-4afa-8bd7-c274cc4ea235',
         'id': 'network0'},
        {'link': 'tap2f88d109-5b', 'type': 'ipv4_dhcp',
         'network_id': 'd227a9b3-6960-4d94-8976-ee5788b44f54',
         'id': 'network1'},
        {'link': 'tap1a5382f8-04', 'type': 'ipv4_dhcp',
         'network_id': 'dab2ba57-cae2-4311-a5ed-010b263891f5',
         'id': 'network2'}
    ]
}

NETWORK_DATA_2 = {
    "services": [
        {"type": "dns", "address": "1.1.1.191"},
        {"type": "dns", "address": "1.1.1.4"}],
    "networks": [
        {"network_id": "d94bbe94-7abc-48d4-9c82-4628ea26164a", "type": "ipv4",
         "netmask": "255.255.255.248", "link": "eth0",
         "routes": [{"netmask": "0.0.0.0", "network": "0.0.0.0",
                     "gateway": "2.2.2.9"}],
         "ip_address": "2.2.2.10", "id": "network0-ipv4"},
        {"network_id": "ca447c83-6409-499b-aaef-6ad1ae995348", "type": "ipv4",
         "netmask": "255.255.255.224", "link": "eth1",
         "routes": [], "ip_address": "3.3.3.24", "id": "network1-ipv4"}],
    "links": [
        {"ethernet_mac_address": "fa:16:3e:dd:50:9a", "mtu": 1500,
         "type": "vif", "id": "eth0", "vif_id": "vif-foo1"},
        {"ethernet_mac_address": "fa:16:3e:a8:14:69", "mtu": 1500,
         "type": "vif", "id": "eth1", "vif_id": "vif-foo2"}]
}

# This network data ha 'tap' or null type for a link.
NETWORK_DATA_3 = {
    "services": [{"type": "dns", "address": "172.16.36.11"},
                 {"type": "dns", "address": "172.16.36.12"}],
    "networks": [
        {"network_id": "7c41450c-ba44-401a-9ab1-1604bb2da51e",
         "type": "ipv4", "netmask": "255.255.255.128",
         "link": "tap77a0dc5b-72", "ip_address": "172.17.48.18",
         "id": "network0",
         "routes": [{"netmask": "0.0.0.0", "network": "0.0.0.0",
                     "gateway": "172.17.48.1"}]},
        {"network_id": "7c41450c-ba44-401a-9ab1-1604bb2da51e",
         "type": "ipv6", "netmask": "ffff:ffff:ffff:ffff::",
         "link": "tap77a0dc5b-72",
         "ip_address": "fdb8:52d0:9d14:0:f816:3eff:fe9f:70d",
         "id": "network1",
         "routes": [{"netmask": "::", "network": "::",
                     "gateway": "fdb8:52d0:9d14::1"}]},
        {"network_id": "1f53cb0e-72d3-47c7-94b9-ff4397c5fe54",
         "type": "ipv4", "netmask": "255.255.255.128",
         "link": "tap7d6b7bec-93", "ip_address": "172.16.48.13",
         "id": "network2",
         "routes": [{"netmask": "0.0.0.0", "network": "0.0.0.0",
                    "gateway": "172.16.48.1"},
                    {"netmask": "255.255.0.0", "network": "172.16.0.0",
                     "gateway": "172.16.48.1"}]}],
    "links": [
        {"ethernet_mac_address": "fa:16:3e:dd:50:9a", "mtu": None,
         "type": "tap", "id": "tap77a0dc5b-72",
         "vif_id": "77a0dc5b-720e-41b7-bfa7-1b2ff62e0d48"},
        {"ethernet_mac_address": "fa:16:3e:a8:14:69", "mtu": None,
         "type": None, "id": "tap7d6b7bec-93",
         "vif_id": "7d6b7bec-93e6-4c03-869a-ddc5014892d5"}
    ]
}

BOND_MAC = "fa:16:3e:b3:72:36"
NETWORK_DATA_BOND = {
    "services": [
        {"type": "dns", "address": "1.1.1.191"},
        {"type": "dns", "address": "1.1.1.4"},
    ],
    "networks": [
        {"id": "network2-ipv4", "ip_address": "2.2.2.13",
         "link": "vlan2", "netmask": "255.255.255.248",
         "network_id": "4daf5ce8-38cf-4240-9f1a-04e86d7c6117",
         "type": "ipv4",
         "routes": [{"netmask": "0.0.0.0", "network": "0.0.0.0",
                    "gateway": "2.2.2.9"}]},
        {"id": "network3-ipv4", "ip_address": "10.0.1.5",
         "link": "vlan3", "netmask": "255.255.255.248",
         "network_id": "a9e2f47c-3c43-4782-94d0-e1eeef1c8c9d",
         "type": "ipv4",
         "routes": [{"netmask": "255.255.255.255",
                    "network": "192.168.1.0", "gateway": "10.0.1.1"}]}
    ],
    "links": [
        {"ethernet_mac_address": "0c:c4:7a:34:6e:3c",
         "id": "eth0", "mtu": 1500, "type": "phy"},
        {"ethernet_mac_address": "0c:c4:7a:34:6e:3d",
         "id": "eth1", "mtu": 1500, "type": "phy"},
        {"bond_links": ["eth0", "eth1"],
         "bond_miimon": 100, "bond_mode": "4",
         "bond_xmit_hash_policy": "layer3+4",
         "ethernet_mac_address": BOND_MAC,
         "id": "bond0", "type": "bond"},
        {"ethernet_mac_address": "fa:16:3e:b3:72:30",
         "id": "vlan2", "type": "vlan", "vlan_id": 602,
         "vlan_link": "bond0", "vlan_mac_address": "fa:16:3e:b3:72:30"},
        {"ethernet_mac_address": "fa:16:3e:66:ab:a6",
         "id": "vlan3", "type": "vlan", "vlan_id": 612, "vlan_link": "bond0",
         "vlan_mac_address": "fa:16:3e:66:ab:a6"}
    ]
}

NETWORK_DATA_VLAN = {
    "services": [{"type": "dns", "address": "1.1.1.191"}],
    "networks": [
        {"id": "network1-ipv4", "ip_address": "10.0.1.5",
         "link": "vlan1", "netmask": "255.255.255.248",
         "network_id": "a9e2f47c-3c43-4782-94d0-e1eeef1c8c9d",
         "type": "ipv4",
         "routes": [{"netmask": "255.255.255.255",
                    "network": "192.168.1.0", "gateway": "10.0.1.1"}]}
    ],
    "links": [
        {"ethernet_mac_address": "fa:16:3e:69:b0:58",
         "id": "eth0", "mtu": 1500, "type": "phy"},
        {"ethernet_mac_address": "fa:16:3e:b3:72:30",
         "id": "vlan1", "type": "vlan", "vlan_id": 602,
         "vlan_link": "eth0", "vlan_mac_address": "fa:16:3e:b3:72:30"},
    ]
}

KNOWN_MACS = {
    'fa:16:3e:69:b0:58': 'enp0s1',
    'fa:16:3e:d4:57:ad': 'enp0s2',
    'fa:16:3e:dd:50:9a': 'foo1',
    'fa:16:3e:a8:14:69': 'foo2',
    'fa:16:3e:ed:9a:59': 'foo3',
    '0c:c4:7a:34:6e:3d': 'oeth1',
    '0c:c4:7a:34:6e:3c': 'oeth0',
}

CFG_DRIVE_FILES_V2 = {
    'ec2/2009-04-04/meta-data.json': json.dumps(EC2_META),
    'ec2/2009-04-04/user-data': USER_DATA,
    'ec2/latest/meta-data.json': json.dumps(EC2_META),
    'ec2/latest/user-data': USER_DATA,
    'openstack/2012-08-10/meta_data.json': json.dumps(OSTACK_META),
    'openstack/2012-08-10/user_data': USER_DATA,
    'openstack/content/0000': CONTENT_0,
    'openstack/content/0001': CONTENT_1,
    'openstack/latest/meta_data.json': json.dumps(OSTACK_META),
    'openstack/latest/user_data': USER_DATA,
    'openstack/latest/network_data.json': json.dumps(NETWORK_DATA),
    'openstack/2015-10-15/meta_data.json': json.dumps(OSTACK_META),
    'openstack/2015-10-15/user_data': USER_DATA,
    'openstack/2015-10-15/network_data.json': json.dumps(NETWORK_DATA)}


class TestConfigDriveDataSource(CiTestCase):

    def setUp(self):
        super(TestConfigDriveDataSource, self).setUp()
        self.add_patch(
            "cloudinit.sources.DataSourceConfigDrive.util.find_devs_with",
            "m_find_devs_with", return_value=[])
        self.tmp = self.tmp_dir()

    def test_ec2_metadata(self):
        populate_dir(self.tmp, CFG_DRIVE_FILES_V2)
        found = ds.read_config_drive(self.tmp)
        self.assertTrue('ec2-metadata' in found)
        ec2_md = found['ec2-metadata']
        self.assertEqual(EC2_META, ec2_md)

    def test_dev_os_remap(self):
        populate_dir(self.tmp, CFG_DRIVE_FILES_V2)
        cfg_ds = ds.DataSourceConfigDrive(settings.CFG_BUILTIN,
                                          None,
                                          helpers.Paths({}))
        found = ds.read_config_drive(self.tmp)
        cfg_ds.metadata = found['metadata']
        name_tests = {
            'ami': '/dev/vda1',
            'root': '/dev/vda1',
            'ephemeral0': '/dev/vda2',
            'swap': '/dev/vda3',
        }
        for name, dev_name in name_tests.items():
            with ExitStack() as mocks:
                provided_name = dev_name[len('/dev/'):]
                provided_name = "s" + provided_name[1:]
                find_mock = mocks.enter_context(
                    mock.patch.object(util, 'find_devs_with',
                                      return_value=[provided_name]))
                # We want os.path.exists() to return False on its first call,
                # and True on its second call.  We use a handy generator as
                # the mock side effect for this.  The mocked function returns
                # what the side effect returns.

                def exists_side_effect():
                    yield False
                    yield True
                exists_mock = mocks.enter_context(
                    mock.patch.object(os.path, 'exists',
                                      side_effect=exists_side_effect()))
                device = cfg_ds.device_name_to_device(name)
                self.assertEqual(dev_name, device)

                find_mock.assert_called_once_with(mock.ANY)
                self.assertEqual(exists_mock.call_count, 2)

    def test_dev_os_map(self):
        populate_dir(self.tmp, CFG_DRIVE_FILES_V2)
        cfg_ds = ds.DataSourceConfigDrive(settings.CFG_BUILTIN,
                                          None,
                                          helpers.Paths({}))
        found = ds.read_config_drive(self.tmp)
        os_md = found['metadata']
        cfg_ds.metadata = os_md
        name_tests = {
            'ami': '/dev/vda1',
            'root': '/dev/vda1',
            'ephemeral0': '/dev/vda2',
            'swap': '/dev/vda3',
        }
        for name, dev_name in name_tests.items():
            with ExitStack() as mocks:
                find_mock = mocks.enter_context(
                    mock.patch.object(util, 'find_devs_with',
                                      return_value=[dev_name]))
                exists_mock = mocks.enter_context(
                    mock.patch.object(os.path, 'exists',
                                      return_value=True))
                device = cfg_ds.device_name_to_device(name)
                self.assertEqual(dev_name, device)

                find_mock.assert_called_once_with(mock.ANY)
                exists_mock.assert_called_once_with(mock.ANY)

    def test_dev_ec2_remap(self):
        populate_dir(self.tmp, CFG_DRIVE_FILES_V2)
        cfg_ds = ds.DataSourceConfigDrive(settings.CFG_BUILTIN,
                                          None,
                                          helpers.Paths({}))
        found = ds.read_config_drive(self.tmp)
        ec2_md = found['ec2-metadata']
        os_md = found['metadata']
        cfg_ds.ec2_metadata = ec2_md
        cfg_ds.metadata = os_md
        name_tests = {
            'ami': '/dev/vda1',
            'root': '/dev/vda1',
            'ephemeral0': '/dev/vda2',
            'swap': '/dev/vda3',
            None: None,
            'bob': None,
            'root2k': None,
        }
        for name, dev_name in name_tests.items():
            # We want os.path.exists() to return False on its first call,
            # and True on its second call.  We use a handy generator as
            # the mock side effect for this.  The mocked function returns
            # what the side effect returns.
            def exists_side_effect():
                yield False
                yield True
            with mock.patch.object(os.path, 'exists',
                                   side_effect=exists_side_effect()):
                device = cfg_ds.device_name_to_device(name)
                self.assertEqual(dev_name, device)
                # We don't assert the call count for os.path.exists() because
                # not all of the entries in name_tests results in two calls to
                # that function.  Specifically, 'root2k' doesn't seem to call
                # it at all.

    def test_dev_ec2_map(self):
        populate_dir(self.tmp, CFG_DRIVE_FILES_V2)
        cfg_ds = ds.DataSourceConfigDrive(settings.CFG_BUILTIN,
                                          None,
                                          helpers.Paths({}))
        found = ds.read_config_drive(self.tmp)
        ec2_md = found['ec2-metadata']
        os_md = found['metadata']
        cfg_ds.ec2_metadata = ec2_md
        cfg_ds.metadata = os_md
        name_tests = {
            'ami': '/dev/sda1',
            'root': '/dev/sda1',
            'ephemeral0': '/dev/sda2',
            'swap': '/dev/sda3',
            None: None,
            'bob': None,
            'root2k': None,
        }
        for name, dev_name in name_tests.items():
            with mock.patch.object(os.path, 'exists', return_value=True):
                device = cfg_ds.device_name_to_device(name)
                self.assertEqual(dev_name, device)

    def test_dir_valid(self):
        """Verify a dir is read as such."""

        populate_dir(self.tmp, CFG_DRIVE_FILES_V2)

        found = ds.read_config_drive(self.tmp)

        expected_md = copy(OSTACK_META)
        expected_md['instance-id'] = expected_md['uuid']
        expected_md['local-hostname'] = expected_md['hostname']

        self.assertEqual(USER_DATA, found['userdata'])
        self.assertEqual(expected_md, found['metadata'])
        self.assertEqual(NETWORK_DATA, found['networkdata'])
        self.assertEqual(found['files']['/etc/foo.cfg'], CONTENT_0)
        self.assertEqual(found['files']['/etc/bar/bar.cfg'], CONTENT_1)

    def test_seed_dir_valid_extra(self):
        """Verify extra files do not affect datasource validity."""

        data = copy(CFG_DRIVE_FILES_V2)
        data["myfoofile.txt"] = "myfoocontent"
        data["openstack/latest/random-file.txt"] = "random-content"

        populate_dir(self.tmp, data)

        found = ds.read_config_drive(self.tmp)

        expected_md = copy(OSTACK_META)
        expected_md['instance-id'] = expected_md['uuid']
        expected_md['local-hostname'] = expected_md['hostname']

        self.assertEqual(expected_md, found['metadata'])

    def test_seed_dir_bad_json_metadata(self):
        """Verify that bad json in metadata raises BrokenConfigDriveDir."""
        data = copy(CFG_DRIVE_FILES_V2)

        data["openstack/2012-08-10/meta_data.json"] = "non-json garbage {}"
        data["openstack/2015-10-15/meta_data.json"] = "non-json garbage {}"
        data["openstack/latest/meta_data.json"] = "non-json garbage {}"

        populate_dir(self.tmp, data)

        self.assertRaises(openstack.BrokenMetadata,
                          ds.read_config_drive, self.tmp)

    def test_seed_dir_no_configdrive(self):
        """Verify that no metadata raises NonConfigDriveDir."""

        my_d = os.path.join(self.tmp, "non-configdrive")
        data = copy(CFG_DRIVE_FILES_V2)
        data["myfoofile.txt"] = "myfoocontent"
        data["openstack/latest/random-file.txt"] = "random-content"
        data["content/foo"] = "foocontent"

        self.assertRaises(openstack.NonReadable,
                          ds.read_config_drive, my_d)

    def test_seed_dir_missing(self):
        """Verify that missing seed_dir raises NonConfigDriveDir."""
        my_d = os.path.join(self.tmp, "nonexistantdirectory")
        self.assertRaises(openstack.NonReadable,
                          ds.read_config_drive, my_d)

    def test_find_candidates(self):
        devs_with_answers = {}

        def my_devs_with(*args, **kwargs):
            criteria = args[0] if len(args) else kwargs.pop('criteria', None)
            return devs_with_answers.get(criteria, [])

        def my_is_partition(dev):
            return dev[-1] in "0123456789" and not dev.startswith("sr")

        try:
            orig_find_devs_with = util.find_devs_with
            util.find_devs_with = my_devs_with

            orig_is_partition = util.is_partition
            util.is_partition = my_is_partition

            devs_with_answers = {"TYPE=vfat": [],
                                 "TYPE=iso9660": ["/dev/vdb"],
                                 "LABEL=config-2": ["/dev/vdb"]}
            self.assertEqual(["/dev/vdb"], ds.find_candidate_devs())

            # add a vfat item
            # zdd reverse sorts after vdb, but config-2 label is preferred
            devs_with_answers['TYPE=vfat'] = ["/dev/zdd"]
            self.assertEqual(["/dev/vdb", "/dev/zdd"],
                             ds.find_candidate_devs())

            # verify that partitions are considered, that have correct label.
            devs_with_answers = {"TYPE=vfat": ["/dev/sda1"],
                                 "TYPE=iso9660": [],
                                 "LABEL=config-2": ["/dev/vdb3"]}
            self.assertEqual(["/dev/vdb3"],
                             ds.find_candidate_devs())

            # Verify that uppercase labels are also found.
            devs_with_answers = {"TYPE=vfat": [],
                                 "TYPE=iso9660": ["/dev/vdb"],
                                 "LABEL=CONFIG-2": ["/dev/vdb"]}
            self.assertEqual(["/dev/vdb"], ds.find_candidate_devs())

        finally:
            util.find_devs_with = orig_find_devs_with
            util.is_partition = orig_is_partition

    @mock.patch('cloudinit.sources.DataSourceConfigDrive.on_first_boot')
    def test_pubkeys_v2(self, on_first_boot):
        """Verify that public-keys work in config-drive-v2."""
        myds = cfg_ds_from_dir(self.tmp, files=CFG_DRIVE_FILES_V2)
        self.assertEqual(myds.get_public_ssh_keys(),
                         [OSTACK_META['public_keys']['mykey']])


class TestNetJson(CiTestCase):
    def setUp(self):
        super(TestNetJson, self).setUp()
        self.tmp = self.tmp_dir()
        self.maxDiff = None

    @mock.patch('cloudinit.sources.DataSourceConfigDrive.on_first_boot')
    def test_network_data_is_found(self, on_first_boot):
        """Verify that network_data is present in ds in config-drive-v2."""
        myds = cfg_ds_from_dir(self.tmp, files=CFG_DRIVE_FILES_V2)
        self.assertIsNotNone(myds.network_json)

    @mock.patch('cloudinit.sources.DataSourceConfigDrive.on_first_boot')
    def test_network_config_is_converted(self, on_first_boot):
        """Verify that network_data is converted and present on ds object."""
        myds = cfg_ds_from_dir(self.tmp, files=CFG_DRIVE_FILES_V2)
        network_config = openstack.convert_net_json(NETWORK_DATA,
                                                    known_macs=KNOWN_MACS)
        self.assertEqual(myds.network_config, network_config)

    def test_network_config_conversions(self):
        """Tests a bunch of input network json and checks the
           expected conversions."""
        in_datas = [
            NETWORK_DATA,
            {
                'services': [{'type': 'dns', 'address': '172.19.0.12'}],
                'networks': [{
                    'network_id': 'dacd568d-5be6-4786-91fe-750c374b78b4',
                    'type': 'ipv4',
                    'netmask': '255.255.252.0',
                    'link': 'tap1a81968a-79',
                    'routes': [{
                        'netmask': '0.0.0.0',
                        'network': '0.0.0.0',
                        'gateway': '172.19.3.254',
                    }],
                    'ip_address': '172.19.1.34',
                    'id': 'network0',
                }],
                'links': [{
                    'type': 'bridge',
                    'vif_id': '1a81968a-797a-400f-8a80-567f997eb93f',
                    'ethernet_mac_address': 'fa:16:3e:ed:9a:59',
                    'id': 'tap1a81968a-79',
                    'mtu': None,
                }],
            },
        ]
        out_datas = [
            {
                'version': 1,
                'config': [
                    {
                        'subnets': [{'type': 'dhcp4'}],
                        'type': 'physical',
                        'mac_address': 'fa:16:3e:69:b0:58',
                        'name': 'enp0s1',
                        'mtu': None,
                    },
                    {
                        'subnets': [{'type': 'dhcp4'}],
                        'type': 'physical',
                        'mac_address': 'fa:16:3e:d4:57:ad',
                        'name': 'enp0s2',
                        'mtu': None,
                    },
                    {
                        'subnets': [{'type': 'dhcp4'}],
                        'type': 'physical',
                        'mac_address': 'fa:16:3e:05:30:fe',
                        'name': 'nic0',
                        'mtu': None,
                    },
                    {
                        'type': 'nameserver',
                        'address': '199.204.44.24',
                    },
                    {
                        'type': 'nameserver',
                        'address': '199.204.47.54',
                    }
                ],

            },
            {
                'version': 1,
                'config': [
                    {
                        'name': 'foo3',
                        'mac_address': 'fa:16:3e:ed:9a:59',
                        'mtu': None,
                        'type': 'physical',
                        'subnets': [
                            {
                                'address': '172.19.1.34',
                                'netmask': '255.255.252.0',
                                'type': 'static',
                                'ipv4': True,
                                'routes': [{
                                    'gateway': '172.19.3.254',
                                    'netmask': '0.0.0.0',
                                    'network': '0.0.0.0',
                                }],
                            }
                        ]
                    },
                    {
                        'type': 'nameserver',
                        'address': '172.19.0.12',
                    }
                ],
            },
        ]
        for in_data, out_data in zip(in_datas, out_datas):
            conv_data = openstack.convert_net_json(in_data,
                                                   known_macs=KNOWN_MACS)
            self.assertEqual(out_data, conv_data)


class TestConvertNetworkData(CiTestCase):
    def setUp(self):
        super(TestConvertNetworkData, self).setUp()
        self.tmp = self.tmp_dir()

    def _getnames_in_config(self, ncfg):
        return set([n['name'] for n in ncfg['config']
                    if n['type'] == 'physical'])

    def test_conversion_fills_names(self):
        ncfg = openstack.convert_net_json(NETWORK_DATA, known_macs=KNOWN_MACS)
        expected = set(['nic0', 'enp0s1', 'enp0s2'])
        found = self._getnames_in_config(ncfg)
        self.assertEqual(found, expected)

    @mock.patch('cloudinit.net.get_interfaces_by_mac')
    def test_convert_reads_system_prefers_name(self, get_interfaces_by_mac):
        macs = KNOWN_MACS.copy()
        macs.update({'fa:16:3e:05:30:fe': 'foonic1',
                     'fa:16:3e:69:b0:58': 'ens1'})
        get_interfaces_by_mac.return_value = macs

        ncfg = openstack.convert_net_json(NETWORK_DATA)
        expected = set(['nic0', 'ens1', 'enp0s2'])
        found = self._getnames_in_config(ncfg)
        self.assertEqual(found, expected)

    def test_convert_raises_value_error_on_missing_name(self):
        macs = {'aa:aa:aa:aa:aa:00': 'ens1'}
        self.assertRaises(ValueError, openstack.convert_net_json,
                          NETWORK_DATA, known_macs=macs)

    def test_conversion_with_route(self):
        ncfg = openstack.convert_net_json(NETWORK_DATA_2,
                                          known_macs=KNOWN_MACS)
        # not the best test, but see that we get a route in the
        # network config and that it gets rendered to an ENI file
        routes = []
        for n in ncfg['config']:
            for s in n.get('subnets', []):
                routes.extend(s.get('routes', []))
        self.assertIn(
            {'network': '0.0.0.0', 'netmask': '0.0.0.0', 'gateway': '2.2.2.9'},
            routes)
        eni_renderer = eni.Renderer()
        eni_renderer.render_network_state(
            network_state.parse_net_config_data(ncfg), target=self.tmp)
        with open(os.path.join(self.tmp, "etc",
                               "network", "interfaces"), 'r') as f:
            eni_rendering = f.read()
            self.assertIn("route add default gw 2.2.2.9", eni_rendering)

    def test_conversion_with_tap(self):
        ncfg = openstack.convert_net_json(NETWORK_DATA_3,
                                          known_macs=KNOWN_MACS)
        physicals = set()
        for i in ncfg['config']:
            if i.get('type') == "physical":
                physicals.add(i['name'])
        self.assertEqual(physicals, set(('foo1', 'foo2')))

    def test_bond_conversion(self):
        # light testing of bond conversion and eni rendering of bond
        ncfg = openstack.convert_net_json(NETWORK_DATA_BOND,
                                          known_macs=KNOWN_MACS)
        eni_renderer = eni.Renderer()

        eni_renderer.render_network_state(
            network_state.parse_net_config_data(ncfg), target=self.tmp)
        with open(os.path.join(self.tmp, "etc",
                               "network", "interfaces"), 'r') as f:
            eni_rendering = f.read()

        # Verify there are expected interfaces in the net config.
        interfaces = sorted(
            [i['name'] for i in ncfg['config']
             if i['type'] in ('vlan', 'bond', 'physical')])
        self.assertEqual(
            sorted(["oeth0", "oeth1", "bond0", "bond0.602", "bond0.612"]),
            interfaces)

        words = eni_rendering.split()
        # 'eth0' and 'eth1' are the ids. because their mac adresses
        # map to other names, we should not see them in the ENI
        self.assertNotIn('eth0', words)
        self.assertNotIn('eth1', words)

        # oeth0 and oeth1 are the interface names for eni.
        # bond0 will be generated for the bond. Each should be auto.
        self.assertIn("auto oeth0", eni_rendering)
        self.assertIn("auto oeth1", eni_rendering)
        self.assertIn("auto bond0", eni_rendering)
        # The bond should have the given mac address
        pos = eni_rendering.find("auto bond0")
        self.assertIn(BOND_MAC, eni_rendering[pos:])

    def test_vlan(self):
        # light testing of vlan config conversion and eni rendering
        ncfg = openstack.convert_net_json(NETWORK_DATA_VLAN,
                                          known_macs=KNOWN_MACS)
        eni_renderer = eni.Renderer()
        eni_renderer.render_network_state(
            network_state.parse_net_config_data(ncfg), target=self.tmp)
        with open(os.path.join(self.tmp, "etc",
                               "network", "interfaces"), 'r') as f:
            eni_rendering = f.read()

        self.assertIn("iface enp0s1", eni_rendering)
        self.assertIn("address 10.0.1.5", eni_rendering)
        self.assertIn("auto enp0s1.602", eni_rendering)

    def test_mac_addrs_can_be_upper_case(self):
        # input mac addresses on rackspace may be upper case
        my_netdata = deepcopy(NETWORK_DATA)
        for link in my_netdata['links']:
            link['ethernet_mac_address'] = link['ethernet_mac_address'].upper()

        ncfg = openstack.convert_net_json(my_netdata, known_macs=KNOWN_MACS)
        config_name2mac = {}
        for n in ncfg['config']:
            if n['type'] == 'physical':
                config_name2mac[n['name']] = n['mac_address']

        expected = {'nic0': 'fa:16:3e:05:30:fe', 'enp0s1': 'fa:16:3e:69:b0:58',
                    'enp0s2': 'fa:16:3e:d4:57:ad'}
        self.assertEqual(expected, config_name2mac)


def cfg_ds_from_dir(base_d, files=None):
    run = os.path.join(base_d, "run")
    os.mkdir(run)
    cfg_ds = ds.DataSourceConfigDrive(
        settings.CFG_BUILTIN, None, helpers.Paths({'run_dir': run}))
    cfg_ds.seed_dir = os.path.join(base_d, "seed")
    if files:
        populate_dir(cfg_ds.seed_dir, files)
    cfg_ds.known_macs = KNOWN_MACS.copy()
    if not cfg_ds.get_data():
        raise RuntimeError("Data source did not extract itself from"
                           " seed directory %s" % cfg_ds.seed_dir)
    return cfg_ds


def populate_ds_from_read_config(cfg_ds, source, results):
    """Patch the DataSourceConfigDrive from the results of
    read_config_drive_dir hopefully in line with what it would have
    if cfg_ds.get_data had been successfully called"""
    cfg_ds.source = source
    cfg_ds.metadata = results.get('metadata')
    cfg_ds.ec2_metadata = results.get('ec2-metadata')
    cfg_ds.userdata_raw = results.get('userdata')
    cfg_ds.version = results.get('version')
    cfg_ds.network_json = results.get('networkdata')
    cfg_ds._network_config = openstack.convert_net_json(
        cfg_ds.network_json, known_macs=KNOWN_MACS)


# vi: ts=4 expandtab
