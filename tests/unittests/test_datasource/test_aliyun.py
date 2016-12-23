# This file is part of cloud-init. See LICENSE file for license information.

import functools
import httpretty
import os

from .. import helpers as test_helpers
from cloudinit import helpers
from cloudinit.sources import DataSourceAliYun as ay

DEFAULT_METADATA = {
    'instance-id': 'aliyun-test-vm-00',
    'eipv4': '10.0.0.1',
    'hostname': 'test-hostname',
    'image-id': 'm-test',
    'launch-index': '0',
    'mac': '00:16:3e:00:00:00',
    'network-type': 'vpc',
    'private-ipv4': '192.168.0.1',
    'serial-number': 'test-string',
    'vpc-cidr-block': '192.168.0.0/16',
    'vpc-id': 'test-vpc',
    'vswitch-id': 'test-vpc',
    'vswitch-cidr-block': '192.168.0.0/16',
    'zone-id': 'test-zone-1',
    'ntp-conf': {'ntp_servers': [
                 'ntp1.aliyun.com',
                 'ntp2.aliyun.com',
                 'ntp3.aliyun.com']},
    'source-address': ['http://mirrors.aliyun.com',
                       'http://mirrors.aliyuncs.com'],
    'public-keys': {'key-pair-1': {'openssh-key': 'ssh-rsa AAAAB3...'},
                    'key-pair-2': {'openssh-key': 'ssh-rsa AAAAB3...'}}
}

DEFAULT_USERDATA = """\
#cloud-config

hostname: localhost"""


def register_mock_metaserver(base_url, data):
    def register_helper(register, base_url, body):
        if isinstance(body, str):
            register(base_url, body)
        elif isinstance(body, list):
            register(base_url.rstrip('/'), '\n'.join(body) + '\n')
        elif isinstance(body, dict):
            vals = []
            for k, v in body.items():
                if isinstance(v, (str, list)):
                    suffix = k.rstrip('/')
                else:
                    suffix = k.rstrip('/') + '/'
                vals.append(suffix)
                url = base_url.rstrip('/') + '/' + suffix
                register_helper(register, url, v)
            register(base_url, '\n'.join(vals) + '\n')

    register = functools.partial(httpretty.register_uri, httpretty.GET)
    register_helper(register, base_url, data)


class TestAliYunDatasource(test_helpers.HttprettyTestCase):
    def setUp(self):
        super(TestAliYunDatasource, self).setUp()
        cfg = {'datasource': {'AliYun': {'timeout': '1', 'max_wait': '1'}}}
        distro = {}
        paths = helpers.Paths({})
        self.ds = ay.DataSourceAliYun(cfg, distro, paths)
        self.metadata_address = self.ds.metadata_urls[0]
        self.api_ver = self.ds.api_ver

    @property
    def default_metadata(self):
        return DEFAULT_METADATA

    @property
    def default_userdata(self):
        return DEFAULT_USERDATA

    @property
    def metadata_url(self):
        return os.path.join(self.metadata_address,
                            self.api_ver, 'meta-data') + '/'

    @property
    def userdata_url(self):
        return os.path.join(self.metadata_address,
                            self.api_ver, 'user-data')

    def regist_default_server(self):
        register_mock_metaserver(self.metadata_url, self.default_metadata)
        register_mock_metaserver(self.userdata_url, self.default_userdata)

    def _test_get_data(self):
        self.assertEqual(self.ds.metadata, self.default_metadata)
        self.assertEqual(self.ds.userdata_raw,
                         self.default_userdata.encode('utf8'))

    def _test_get_sshkey(self):
        pub_keys = [v['openssh-key'] for (_, v) in
                    self.default_metadata['public-keys'].items()]
        self.assertEqual(self.ds.get_public_ssh_keys(), pub_keys)

    def _test_get_iid(self):
        self.assertEqual(self.default_metadata['instance-id'],
                         self.ds.get_instance_id())

    def _test_host_name(self):
        self.assertEqual(self.default_metadata['hostname'],
                         self.ds.get_hostname())

    @httpretty.activate
    def test_with_mock_server(self):
        self.regist_default_server()
        self.ds.get_data()
        self._test_get_data()
        self._test_get_sshkey()
        self._test_get_iid()
        self._test_host_name()

    def test_parse_public_keys(self):
        public_keys = {}
        self.assertEqual(ay.parse_public_keys(public_keys), [])

        public_keys = {'key-pair-0': 'ssh-key-0'}
        self.assertEqual(ay.parse_public_keys(public_keys),
                         [public_keys['key-pair-0']])

        public_keys = {'key-pair-0': 'ssh-key-0', 'key-pair-1': 'ssh-key-1'}
        self.assertEqual(set(ay.parse_public_keys(public_keys)),
                         set([public_keys['key-pair-0'],
                             public_keys['key-pair-1']]))

        public_keys = {'key-pair-0': ['ssh-key-0', 'ssh-key-1']}
        self.assertEqual(ay.parse_public_keys(public_keys),
                         public_keys['key-pair-0'])

        public_keys = {'key-pair-0': {'openssh-key': []}}
        self.assertEqual(ay.parse_public_keys(public_keys), [])

        public_keys = {'key-pair-0': {'openssh-key': 'ssh-key-0'}}
        self.assertEqual(ay.parse_public_keys(public_keys),
                         [public_keys['key-pair-0']['openssh-key']])

        public_keys = {'key-pair-0': {'openssh-key': ['ssh-key-0',
                                                      'ssh-key-1']}}
        self.assertEqual(ay.parse_public_keys(public_keys),
                         public_keys['key-pair-0']['openssh-key'])

# vi: ts=4 expandtab
