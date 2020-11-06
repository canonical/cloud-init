# This file is part of cloud-init. See LICENSE file for license information.

import json
import os
import shutil
import tempfile


from cloudinit.settings import PER_INSTANCE
from cloudinit.sources import DataSourceConfigDrive as ds
from cloudinit.sources import DataSourceNotFoundException
from cloudinit import safeyaml
from cloudinit import stages
from cloudinit import settings
from cloudinit import util
from cloudinit.tests import helpers
from cloudinit import helpers as cloud_helpers

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


class TestSimpleRun(helpers.FilesystemMockingTestCase):
    def setUp(self):
        super(TestSimpleRun, self).setUp()
        self.new_root = tempfile.mkdtemp()
        self.tmp = self.tmp_dir()
        self.sys_cfg = {'datasource': {'ConfigDrive': {'dsmode': 'local'}}}
        self.paths = cloud_helpers.Paths(
                {'cloud_dir': self.tmp, 'run_dir': self.tmp})
        self.ds = ds.DataSourceConfigDrive

    def _patchIn(self, root):
        self.patchOS(root)
        self.patchUtils(root)

    @helpers.mock.patch('cloudinit.sources.find_source')
    def test_invalid_config_drive_subsequent_boot(self, mock_ds):
        self.addCleanup(shutil.rmtree, self.new_root)
        self.replicateTestRoot('simple_ubuntu', self.new_root)
        cfg = {
            'datasource_list': ['ConfigDrive'],
            'cloud_init_modules': ['write-files'],
            'system_info': {'paths': {'run_dir': self.new_root}}
        }
        orig_find_devs_with = util.find_devs_with
        try:
            # dont' try to lookup for CDs
            util.find_devs_with = lambda path: []
            dsrc = self.ds(sys_cfg=self.sys_cfg, distro=None, paths=self.paths)
            populate_dir(dsrc.seed_dir, CFG_DRIVE_FILES_V2)
            found = dsrc._get_data()
            self.assertTrue(found)
        finally:
            util.find_devs_with = orig_find_devs_with

        ud = helpers.readResource('user_data.1.txt')
        cloud_cfg = safeyaml.dumps(cfg)
        util.ensure_dir(os.path.join(self.new_root, 'etc', 'cloud'))
        util.write_file(os.path.join(self.new_root, 'etc',
                                     'cloud', 'cloud.cfg'), cloud_cfg)
        self._patchIn(self.new_root)
        # simulate fist boot with config drive
        mock_ds.return_value = (dsrc, 'ConfigDrive')
        initer = stages.Init()
        initer.read_cfg()
        initer.initialize()
        initer.fetch()
        initer.instancify()
        initer.update()
        # simulate config drive removal and reboot
        util.del_file(".instance-id")
        mock_ds.reset_mock()
        msg = ("Did not find any data source")
        mock_ds.side_effect = DataSourceNotFoundException(msg)
        initer = stages.Init()
        initer.read_cfg()
        initer.initialize()
        initer.fetch()
        initer.instancify()
        initer.update()
