# Copyright (C) 2014 Yahoo! Inc.
#
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import copy
import httpretty as hp
import json
import re

from cloudinit.tests import helpers as test_helpers

from six.moves.urllib.parse import urlparse
from six import StringIO, text_type

from cloudinit import helpers
from cloudinit import settings
from cloudinit.sources import BrokenMetadata, convert_vendordata, UNSET
from cloudinit.sources import DataSourceOpenStack as ds
from cloudinit.sources.helpers import openstack
from cloudinit import util

BASE_URL = "http://169.254.169.254"
PUBKEY = u'ssh-rsa AAAAB3NzaC1....sIkJhq8wdX+4I3A4cYbYP ubuntu@server-460\n'
EC2_META = {
    'ami-id': 'ami-00000001',
    'ami-launch-index': '0',
    'ami-manifest-path': 'FIXME',
    'hostname': 'sm-foo-test.novalocal',
    'instance-action': 'none',
    'instance-id': 'i-00000001',
    'instance-type': 'm1.tiny',
    'local-hostname': 'sm-foo-test.novalocal',
    'local-ipv4': '0.0.0.0',
    'public-hostname': 'sm-foo-test.novalocal',
    'public-ipv4': '0.0.0.1',
    'reservation-id': 'r-iru5qm4m',
}
USER_DATA = b'#!/bin/sh\necho This is user data\n'
VENDOR_DATA = {
    'magic': '',
}
OSTACK_META = {
    'availability_zone': 'nova',
    'files': [{'content_path': '/content/0000', 'path': '/etc/foo.cfg'},
              {'content_path': '/content/0001', 'path': '/etc/bar/bar.cfg'}],
    'hostname': 'sm-foo-test.novalocal',
    'meta': {'dsmode': 'local', 'my-meta': 'my-value'},
    'name': 'sm-foo-test',
    'public_keys': {'mykey': PUBKEY},
    'uuid': 'b0fa911b-69d4-4476-bbe2-1c92bff6535c',
}
CONTENT_0 = b'This is contents of /etc/foo.cfg\n'
CONTENT_1 = b'# this is /etc/bar/bar.cfg\n'
OS_FILES = {
    'openstack/content/0000': CONTENT_0,
    'openstack/content/0001': CONTENT_1,
    'openstack/latest/meta_data.json': json.dumps(OSTACK_META),
    'openstack/latest/network_data.json': json.dumps(
        {'links': [], 'networks': [], 'services': []}),
    'openstack/latest/user_data': USER_DATA,
    'openstack/latest/vendor_data.json': json.dumps(VENDOR_DATA),
}
EC2_FILES = {
    'latest/user-data': USER_DATA,
}
EC2_VERSIONS = [
    'latest',
]

MOCK_PATH = 'cloudinit.sources.DataSourceOpenStack.'


# TODO _register_uris should leverage test_ec2.register_mock_metaserver.
def _register_uris(version, ec2_files, ec2_meta, os_files):
    """Registers a set of url patterns into httpretty that will mimic the
    same data returned by the openstack metadata service (and ec2 service)."""

    def match_ec2_url(uri, headers):
        path = uri.path.strip("/")
        if len(path) == 0:
            return (200, headers, "\n".join(EC2_VERSIONS))
        path = uri.path.lstrip("/")
        if path in ec2_files:
            return (200, headers, ec2_files.get(path))
        if path == 'latest/meta-data/':
            buf = StringIO()
            for (k, v) in ec2_meta.items():
                if isinstance(v, (list, tuple)):
                    buf.write("%s/" % (k))
                else:
                    buf.write("%s" % (k))
                buf.write("\n")
            return (200, headers, buf.getvalue())
        if path.startswith('latest/meta-data/'):
            value = None
            pieces = path.split("/")
            if path.endswith("/"):
                pieces = pieces[2:-1]
                value = util.get_cfg_by_path(ec2_meta, pieces)
            else:
                pieces = pieces[2:]
                value = util.get_cfg_by_path(ec2_meta, pieces)
            if value is not None:
                return (200, headers, str(value))
        return (404, headers, '')

    def match_os_uri(uri, headers):
        path = uri.path.strip("/")
        if path == 'openstack':
            return (200, headers, "\n".join([openstack.OS_LATEST]))
        path = uri.path.lstrip("/")
        if path in os_files:
            return (200, headers, os_files.get(path))
        return (404, headers, '')

    def get_request_callback(method, uri, headers):
        uri = urlparse(uri)
        path = uri.path.lstrip("/").split("/")
        if path[0] == 'openstack':
            return match_os_uri(uri, headers)
        return match_ec2_url(uri, headers)

    hp.register_uri(hp.GET, re.compile(r'http://169.254.169.254/.*'),
                    body=get_request_callback)


def _read_metadata_service():
    return ds.read_metadata_service(BASE_URL, retries=0, timeout=0.1)


class TestOpenStackDataSource(test_helpers.HttprettyTestCase):

    with_logs = True
    VERSION = 'latest'

    def setUp(self):
        super(TestOpenStackDataSource, self).setUp()
        self.tmp = self.tmp_dir()

    def test_successful(self):
        _register_uris(self.VERSION, EC2_FILES, EC2_META, OS_FILES)
        f = _read_metadata_service()
        self.assertEqual(VENDOR_DATA, f.get('vendordata'))
        self.assertEqual(CONTENT_0, f['files']['/etc/foo.cfg'])
        self.assertEqual(CONTENT_1, f['files']['/etc/bar/bar.cfg'])
        self.assertEqual(2, len(f['files']))
        self.assertEqual(USER_DATA, f.get('userdata'))
        self.assertEqual(EC2_META, f.get('ec2-metadata'))
        self.assertEqual(2, f.get('version'))
        metadata = f['metadata']
        self.assertEqual('nova', metadata.get('availability_zone'))
        self.assertEqual('sm-foo-test.novalocal', metadata.get('hostname'))
        self.assertEqual('sm-foo-test.novalocal',
                         metadata.get('local-hostname'))
        self.assertEqual('sm-foo-test', metadata.get('name'))
        self.assertEqual('b0fa911b-69d4-4476-bbe2-1c92bff6535c',
                         metadata.get('uuid'))
        self.assertEqual('b0fa911b-69d4-4476-bbe2-1c92bff6535c',
                         metadata.get('instance-id'))

    def test_no_ec2(self):
        _register_uris(self.VERSION, {}, {}, OS_FILES)
        f = _read_metadata_service()
        self.assertEqual(VENDOR_DATA, f.get('vendordata'))
        self.assertEqual(CONTENT_0, f['files']['/etc/foo.cfg'])
        self.assertEqual(CONTENT_1, f['files']['/etc/bar/bar.cfg'])
        self.assertEqual(USER_DATA, f.get('userdata'))
        self.assertEqual({}, f.get('ec2-metadata'))
        self.assertEqual(2, f.get('version'))

    def test_bad_metadata(self):
        os_files = copy.deepcopy(OS_FILES)
        for k in list(os_files.keys()):
            if k.endswith('meta_data.json'):
                os_files.pop(k, None)
        _register_uris(self.VERSION, {}, {}, os_files)
        self.assertRaises(openstack.NonReadable, _read_metadata_service)

    def test_bad_uuid(self):
        os_files = copy.deepcopy(OS_FILES)
        os_meta = copy.deepcopy(OSTACK_META)
        os_meta.pop('uuid')
        for k in list(os_files.keys()):
            if k.endswith('meta_data.json'):
                os_files[k] = json.dumps(os_meta)
        _register_uris(self.VERSION, {}, {}, os_files)
        self.assertRaises(BrokenMetadata, _read_metadata_service)

    def test_userdata_empty(self):
        os_files = copy.deepcopy(OS_FILES)
        for k in list(os_files.keys()):
            if k.endswith('user_data'):
                os_files.pop(k, None)
        _register_uris(self.VERSION, {}, {}, os_files)
        f = _read_metadata_service()
        self.assertEqual(VENDOR_DATA, f.get('vendordata'))
        self.assertEqual(CONTENT_0, f['files']['/etc/foo.cfg'])
        self.assertEqual(CONTENT_1, f['files']['/etc/bar/bar.cfg'])
        self.assertFalse(f.get('userdata'))

    def test_vendordata_empty(self):
        os_files = copy.deepcopy(OS_FILES)
        for k in list(os_files.keys()):
            if k.endswith('vendor_data.json'):
                os_files.pop(k, None)
        _register_uris(self.VERSION, {}, {}, os_files)
        f = _read_metadata_service()
        self.assertEqual(CONTENT_0, f['files']['/etc/foo.cfg'])
        self.assertEqual(CONTENT_1, f['files']['/etc/bar/bar.cfg'])
        self.assertFalse(f.get('vendordata'))

    def test_vendordata_invalid(self):
        os_files = copy.deepcopy(OS_FILES)
        for k in list(os_files.keys()):
            if k.endswith('vendor_data.json'):
                os_files[k] = '{'  # some invalid json
        _register_uris(self.VERSION, {}, {}, os_files)
        self.assertRaises(BrokenMetadata, _read_metadata_service)

    def test_metadata_invalid(self):
        os_files = copy.deepcopy(OS_FILES)
        for k in list(os_files.keys()):
            if k.endswith('meta_data.json'):
                os_files[k] = '{'  # some invalid json
        _register_uris(self.VERSION, {}, {}, os_files)
        self.assertRaises(BrokenMetadata, _read_metadata_service)

    @test_helpers.mock.patch('cloudinit.net.dhcp.maybe_perform_dhcp_discovery')
    def test_datasource(self, m_dhcp):
        _register_uris(self.VERSION, EC2_FILES, EC2_META, OS_FILES)
        ds_os = ds.DataSourceOpenStack(
            settings.CFG_BUILTIN, None, helpers.Paths({'run_dir': self.tmp}))
        self.assertIsNone(ds_os.version)
        mock_path = MOCK_PATH + 'detect_openstack'
        with test_helpers.mock.patch(mock_path) as m_detect_os:
            m_detect_os.return_value = True
            found = ds_os.get_data()
        self.assertTrue(found)
        self.assertEqual(2, ds_os.version)
        md = dict(ds_os.metadata)
        md.pop('instance-id', None)
        md.pop('local-hostname', None)
        self.assertEqual(OSTACK_META, md)
        self.assertEqual(EC2_META, ds_os.ec2_metadata)
        self.assertEqual(USER_DATA, ds_os.userdata_raw)
        self.assertEqual(2, len(ds_os.files))
        self.assertEqual(VENDOR_DATA, ds_os.vendordata_pure)
        self.assertIsNone(ds_os.vendordata_raw)
        m_dhcp.assert_not_called()

    @hp.activate
    @test_helpers.mock.patch('cloudinit.net.dhcp.EphemeralIPv4Network')
    @test_helpers.mock.patch('cloudinit.net.dhcp.maybe_perform_dhcp_discovery')
    def test_local_datasource(self, m_dhcp, m_net):
        """OpenStackLocal calls EphemeralDHCPNetwork and gets instance data."""
        _register_uris(self.VERSION, EC2_FILES, EC2_META, OS_FILES)
        ds_os_local = ds.DataSourceOpenStackLocal(
            settings.CFG_BUILTIN, None, helpers.Paths({'run_dir': self.tmp}))
        ds_os_local._fallback_interface = 'eth9'  # Monkey patch for dhcp
        m_dhcp.return_value = [{
            'interface': 'eth9', 'fixed-address': '192.168.2.9',
            'routers': '192.168.2.1', 'subnet-mask': '255.255.255.0',
            'broadcast-address': '192.168.2.255'}]

        self.assertIsNone(ds_os_local.version)
        mock_path = MOCK_PATH + 'detect_openstack'
        with test_helpers.mock.patch(mock_path) as m_detect_os:
            m_detect_os.return_value = True
            found = ds_os_local.get_data()
        self.assertTrue(found)
        self.assertEqual(2, ds_os_local.version)
        md = dict(ds_os_local.metadata)
        md.pop('instance-id', None)
        md.pop('local-hostname', None)
        self.assertEqual(OSTACK_META, md)
        self.assertEqual(EC2_META, ds_os_local.ec2_metadata)
        self.assertEqual(USER_DATA, ds_os_local.userdata_raw)
        self.assertEqual(2, len(ds_os_local.files))
        self.assertEqual(VENDOR_DATA, ds_os_local.vendordata_pure)
        self.assertIsNone(ds_os_local.vendordata_raw)
        m_dhcp.assert_called_with('eth9')

    def test_bad_datasource_meta(self):
        os_files = copy.deepcopy(OS_FILES)
        for k in list(os_files.keys()):
            if k.endswith('meta_data.json'):
                os_files[k] = '{'  # some invalid json
        _register_uris(self.VERSION, {}, {}, os_files)
        ds_os = ds.DataSourceOpenStack(settings.CFG_BUILTIN,
                                       None,
                                       helpers.Paths({'run_dir': self.tmp}))
        self.assertIsNone(ds_os.version)
        mock_path = MOCK_PATH + 'detect_openstack'
        with test_helpers.mock.patch(mock_path) as m_detect_os:
            m_detect_os.return_value = True
            found = ds_os.get_data()
        self.assertFalse(found)
        self.assertIsNone(ds_os.version)
        self.assertIn(
            'InvalidMetaDataException: Broken metadata address'
            ' http://169.254.169.25',
            self.logs.getvalue())

    def test_no_datasource(self):
        os_files = copy.deepcopy(OS_FILES)
        for k in list(os_files.keys()):
            if k.endswith('meta_data.json'):
                os_files.pop(k)
        _register_uris(self.VERSION, {}, {}, os_files)
        ds_os = ds.DataSourceOpenStack(settings.CFG_BUILTIN,
                                       None,
                                       helpers.Paths({'run_dir': self.tmp}))
        ds_os.ds_cfg = {
            'max_wait': 0,
            'timeout': 0,
        }
        self.assertIsNone(ds_os.version)
        mock_path = MOCK_PATH + 'detect_openstack'
        with test_helpers.mock.patch(mock_path) as m_detect_os:
            m_detect_os.return_value = True
            found = ds_os.get_data()
        self.assertFalse(found)
        self.assertIsNone(ds_os.version)

    def test_network_config_disabled_by_datasource_config(self):
        """The network_config can be disabled from datasource config."""
        mock_path = MOCK_PATH + 'openstack.convert_net_json'
        ds_os = ds.DataSourceOpenStack(
            settings.CFG_BUILTIN, None, helpers.Paths({'run_dir': self.tmp}))
        ds_os.ds_cfg = {'apply_network_config': False}
        sample_json = {'links': [{'ethernet_mac_address': 'mymac'}],
                       'networks': [], 'services': []}
        ds_os.network_json = sample_json  # Ignore this content from metadata
        with test_helpers.mock.patch(mock_path) as m_convert_json:
            self.assertIsNone(ds_os.network_config)
        m_convert_json.assert_not_called()

    def test_network_config_from_network_json(self):
        """The datasource gets network_config from network_data.json."""
        mock_path = MOCK_PATH + 'openstack.convert_net_json'
        example_cfg = {'version': 1, 'config': []}
        ds_os = ds.DataSourceOpenStack(
            settings.CFG_BUILTIN, None, helpers.Paths({'run_dir': self.tmp}))
        sample_json = {'links': [{'ethernet_mac_address': 'mymac'}],
                       'networks': [], 'services': []}
        ds_os.network_json = sample_json
        with test_helpers.mock.patch(mock_path) as m_convert_json:
            m_convert_json.return_value = example_cfg
            self.assertEqual(example_cfg, ds_os.network_config)
        self.assertIn(
            'network config provided via network_json', self.logs.getvalue())
        m_convert_json.assert_called_with(sample_json, known_macs=None)

    def test_network_config_cached(self):
        """The datasource caches the network_config property."""
        mock_path = MOCK_PATH + 'openstack.convert_net_json'
        example_cfg = {'version': 1, 'config': []}
        ds_os = ds.DataSourceOpenStack(
            settings.CFG_BUILTIN, None, helpers.Paths({'run_dir': self.tmp}))
        ds_os._network_config = example_cfg
        with test_helpers.mock.patch(mock_path) as m_convert_json:
            self.assertEqual(example_cfg, ds_os.network_config)
        m_convert_json.assert_not_called()

    def test_disabled_datasource(self):
        os_files = copy.deepcopy(OS_FILES)
        os_meta = copy.deepcopy(OSTACK_META)
        os_meta['meta'] = {
            'dsmode': 'disabled',
        }
        for k in list(os_files.keys()):
            if k.endswith('meta_data.json'):
                os_files[k] = json.dumps(os_meta)
        _register_uris(self.VERSION, {}, {}, os_files)
        ds_os = ds.DataSourceOpenStack(settings.CFG_BUILTIN,
                                       None,
                                       helpers.Paths({'run_dir': self.tmp}))
        ds_os.ds_cfg = {
            'max_wait': 0,
            'timeout': 0,
        }
        self.assertIsNone(ds_os.version)
        mock_path = MOCK_PATH + 'detect_openstack'
        with test_helpers.mock.patch(mock_path) as m_detect_os:
            m_detect_os.return_value = True
            found = ds_os.get_data()
        self.assertFalse(found)
        self.assertIsNone(ds_os.version)

    @hp.activate
    def test_wb__crawl_metadata_does_not_persist(self):
        """_crawl_metadata returns current metadata and does not cache."""
        _register_uris(self.VERSION, EC2_FILES, EC2_META, OS_FILES)
        ds_os = ds.DataSourceOpenStack(
            settings.CFG_BUILTIN, None, helpers.Paths({'run_dir': self.tmp}))
        crawled_data = ds_os._crawl_metadata()
        self.assertEqual(UNSET, ds_os.ec2_metadata)
        self.assertIsNone(ds_os.userdata_raw)
        self.assertEqual(0, len(ds_os.files))
        self.assertIsNone(ds_os.vendordata_raw)
        self.assertEqual(
            ['dsmode', 'ec2-metadata', 'files', 'metadata', 'networkdata',
             'userdata', 'vendordata', 'version'],
            sorted(crawled_data.keys()))
        self.assertEqual('local', crawled_data['dsmode'])
        self.assertEqual(EC2_META, crawled_data['ec2-metadata'])
        self.assertEqual(2, len(crawled_data['files']))
        md = copy.deepcopy(crawled_data['metadata'])
        md.pop('instance-id')
        md.pop('local-hostname')
        self.assertEqual(OSTACK_META, md)
        self.assertEqual(
            json.loads(OS_FILES['openstack/latest/network_data.json']),
            crawled_data['networkdata'])
        self.assertEqual(USER_DATA, crawled_data['userdata'])
        self.assertEqual(VENDOR_DATA, crawled_data['vendordata'])
        self.assertEqual(2, crawled_data['version'])


class TestVendorDataLoading(test_helpers.TestCase):
    def cvj(self, data):
        return convert_vendordata(data)

    def test_vd_load_none(self):
        # non-existant vendor-data should return none
        self.assertIsNone(self.cvj(None))

    def test_vd_load_string(self):
        self.assertEqual(self.cvj("foobar"), "foobar")

    def test_vd_load_list(self):
        data = [{'foo': 'bar'}, 'mystring', list(['another', 'list'])]
        self.assertEqual(self.cvj(data), data)

    def test_vd_load_dict_no_ci(self):
        self.assertIsNone(self.cvj({'foo': 'bar'}))

    def test_vd_load_dict_ci_dict(self):
        self.assertRaises(ValueError, self.cvj,
                          {'foo': 'bar', 'cloud-init': {'x': 1}})

    def test_vd_load_dict_ci_string(self):
        data = {'foo': 'bar', 'cloud-init': 'VENDOR_DATA'}
        self.assertEqual(self.cvj(data), data['cloud-init'])

    def test_vd_load_dict_ci_list(self):
        data = {'foo': 'bar', 'cloud-init': ['VD_1', 'VD_2']}
        self.assertEqual(self.cvj(data), data['cloud-init'])


@test_helpers.mock.patch(MOCK_PATH + 'util.is_x86')
class TestDetectOpenStack(test_helpers.CiTestCase):

    def test_detect_openstack_non_intel_x86(self, m_is_x86):
        """Return True on non-intel platforms because dmi isn't conclusive."""
        m_is_x86.return_value = False
        self.assertTrue(
            ds.detect_openstack(), 'Expected detect_openstack == True')

    @test_helpers.mock.patch(MOCK_PATH + 'util.get_proc_env')
    @test_helpers.mock.patch(MOCK_PATH + 'util.read_dmi_data')
    def test_not_detect_openstack_intel_x86_ec2(self, m_dmi, m_proc_env,
                                                m_is_x86):
        """Return False on EC2 platforms."""
        m_is_x86.return_value = True
        # No product_name in proc/1/environ
        m_proc_env.return_value = {'HOME': '/'}

        def fake_dmi_read(dmi_key):
            if dmi_key == 'system-product-name':
                return 'HVM domU'  # Nothing 'openstackish' on EC2
            if dmi_key == 'chassis-asset-tag':
                return ''  # Empty string on EC2
            assert False, 'Unexpected dmi read of %s' % dmi_key

        m_dmi.side_effect = fake_dmi_read
        self.assertFalse(
            ds.detect_openstack(), 'Expected detect_openstack == False on EC2')
        m_proc_env.assert_called_with(1)

    @test_helpers.mock.patch(MOCK_PATH + 'util.read_dmi_data')
    def test_detect_openstack_intel_product_name_compute(self, m_dmi,
                                                         m_is_x86):
        """Return True on OpenStack compute and nova instances."""
        m_is_x86.return_value = True
        openstack_product_names = ['OpenStack Nova', 'OpenStack Compute']

        for product_name in openstack_product_names:
            m_dmi.return_value = product_name
            self.assertTrue(
                ds.detect_openstack(), 'Failed to detect_openstack')

    @test_helpers.mock.patch(MOCK_PATH + 'util.read_dmi_data')
    def test_detect_openstack_opentelekomcloud_chassis_asset_tag(self, m_dmi,
                                                                 m_is_x86):
        """Return True on OpenStack reporting OpenTelekomCloud asset-tag."""
        m_is_x86.return_value = True

        def fake_dmi_read(dmi_key):
            if dmi_key == 'system-product-name':
                return 'HVM domU'  # Nothing 'openstackish' on OpenTelekomCloud
            if dmi_key == 'chassis-asset-tag':
                return 'OpenTelekomCloud'
            assert False, 'Unexpected dmi read of %s' % dmi_key

        m_dmi.side_effect = fake_dmi_read
        self.assertTrue(
            ds.detect_openstack(),
            'Expected detect_openstack == True on OpenTelekomCloud')

    @test_helpers.mock.patch(MOCK_PATH + 'util.read_dmi_data')
    def test_detect_openstack_oraclecloud_chassis_asset_tag(self, m_dmi,
                                                            m_is_x86):
        """Return True on OpenStack reporting Oracle cloud asset-tag."""
        m_is_x86.return_value = True

        def fake_dmi_read(dmi_key):
            if dmi_key == 'system-product-name':
                return 'Standard PC (i440FX + PIIX, 1996)'  # No match
            if dmi_key == 'chassis-asset-tag':
                return 'OracleCloud.com'
            assert False, 'Unexpected dmi read of %s' % dmi_key

        m_dmi.side_effect = fake_dmi_read
        self.assertTrue(
            ds.detect_openstack(accept_oracle=True),
            'Expected detect_openstack == True on OracleCloud.com')
        self.assertFalse(
            ds.detect_openstack(accept_oracle=False),
            'Expected detect_openstack == False.')

    @test_helpers.mock.patch(MOCK_PATH + 'util.get_proc_env')
    @test_helpers.mock.patch(MOCK_PATH + 'util.read_dmi_data')
    def test_detect_openstack_by_proc_1_environ(self, m_dmi, m_proc_env,
                                                m_is_x86):
        """Return True when nova product_name specified in /proc/1/environ."""
        m_is_x86.return_value = True
        # Nova product_name in proc/1/environ
        m_proc_env.return_value = {
            'HOME': '/', 'product_name': 'OpenStack Nova'}

        def fake_dmi_read(dmi_key):
            if dmi_key == 'system-product-name':
                return 'HVM domU'  # Nothing 'openstackish'
            if dmi_key == 'chassis-asset-tag':
                return ''  # Nothin 'openstackish'
            assert False, 'Unexpected dmi read of %s' % dmi_key

        m_dmi.side_effect = fake_dmi_read
        self.assertTrue(
            ds.detect_openstack(),
            'Expected detect_openstack == True on OpenTelekomCloud')
        m_proc_env.assert_called_with(1)


class TestMetadataReader(test_helpers.HttprettyTestCase):
    """Test the MetadataReader."""
    burl = 'http://169.254.169.254/'
    md_base = {
        'availability_zone': 'myaz1',
        'hostname': 'sm-foo-test.novalocal',
        "keys": [{"data": PUBKEY, "name": "brickies", "type": "ssh"}],
        'launch_index': 0,
        'name': 'sm-foo-test',
        'public_keys': {'mykey': PUBKEY},
        'project_id': '6a103f813b774b9fb15a4fcd36e1c056',
        'uuid': 'b0fa911b-69d4-4476-bbe2-1c92bff6535c'}

    def register(self, path, body=None, status=200):
        content = (body if not isinstance(body, text_type)
                   else body.encode('utf-8'))
        hp.register_uri(
            hp.GET, self.burl + "openstack" + path, status=status,
            body=content)

    def register_versions(self, versions):
        self.register("", '\n'.join(versions))
        self.register("/", '\n'.join(versions))

    def register_version(self, version, data):
        content = '\n'.join(sorted(data.keys()))
        self.register(version, content)
        self.register(version + "/", content)
        for path, content in data.items():
            self.register("/%s/%s" % (version, path), content)
            self.register("/%s/%s" % (version, path), content)
        if 'user_data' not in data:
            self.register("/%s/user_data" % version, "nodata", status=404)

    def test__find_working_version(self):
        """Test a working version ignores unsupported."""
        unsup = "2016-11-09"
        self.register_versions(
            [openstack.OS_FOLSOM, openstack.OS_LIBERTY, unsup,
             openstack.OS_LATEST])
        self.assertEqual(
            openstack.OS_LIBERTY,
            openstack.MetadataReader(self.burl)._find_working_version())

    def test__find_working_version_uses_latest(self):
        """'latest' should be used if no supported versions."""
        unsup1, unsup2 = ("2016-11-09", '2017-06-06')
        self.register_versions([unsup1, unsup2, openstack.OS_LATEST])
        self.assertEqual(
            openstack.OS_LATEST,
            openstack.MetadataReader(self.burl)._find_working_version())

    def test_read_v2_os_ocata(self):
        """Validate return value of read_v2 for os_ocata data."""
        md = copy.deepcopy(self.md_base)
        md['devices'] = []
        network_data = {'links': [], 'networks': [], 'services': []}
        vendor_data = {}
        vendor_data2 = {"static": {}}

        data = {
            'meta_data.json': json.dumps(md),
            'network_data.json': json.dumps(network_data),
            'vendor_data.json': json.dumps(vendor_data),
            'vendor_data2.json': json.dumps(vendor_data2),
        }

        self.register_versions([openstack.OS_OCATA, openstack.OS_LATEST])
        self.register_version(openstack.OS_OCATA, data)

        mock_read_ec2 = test_helpers.mock.MagicMock(
            return_value={'instance-id': 'unused-ec2'})
        expected_md = copy.deepcopy(md)
        expected_md.update(
            {'instance-id': md['uuid'], 'local-hostname': md['hostname']})
        expected = {
            'userdata': '',  # Annoying, no user-data results in empty string.
            'version': 2,
            'metadata': expected_md,
            'vendordata': vendor_data,
            'networkdata': network_data,
            'ec2-metadata': mock_read_ec2.return_value,
            'files': {},
        }
        reader = openstack.MetadataReader(self.burl)
        reader._read_ec2_metadata = mock_read_ec2
        self.assertEqual(expected, reader.read_v2())
        self.assertEqual(1, mock_read_ec2.call_count)


# vi: ts=4 expandtab
