# Copyright (C) 2014 Yahoo! Inc.
#
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import copy
import json
import re

from .. import helpers as test_helpers

from six.moves.urllib.parse import urlparse
from six import StringIO

from cloudinit import helpers
from cloudinit import settings
from cloudinit.sources import convert_vendordata
from cloudinit.sources import DataSourceOpenStack as ds
from cloudinit.sources.helpers import openstack
from cloudinit import util

hp = test_helpers.import_httpretty()

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
    'openstack/latest/user_data': USER_DATA,
    'openstack/latest/vendor_data.json': json.dumps(VENDOR_DATA),
}
EC2_FILES = {
    'latest/user-data': USER_DATA,
}
EC2_VERSIONS = [
    'latest',
]


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
    VERSION = 'latest'

    @hp.activate
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

    @hp.activate
    def test_no_ec2(self):
        _register_uris(self.VERSION, {}, {}, OS_FILES)
        f = _read_metadata_service()
        self.assertEqual(VENDOR_DATA, f.get('vendordata'))
        self.assertEqual(CONTENT_0, f['files']['/etc/foo.cfg'])
        self.assertEqual(CONTENT_1, f['files']['/etc/bar/bar.cfg'])
        self.assertEqual(USER_DATA, f.get('userdata'))
        self.assertEqual({}, f.get('ec2-metadata'))
        self.assertEqual(2, f.get('version'))

    @hp.activate
    def test_bad_metadata(self):
        os_files = copy.deepcopy(OS_FILES)
        for k in list(os_files.keys()):
            if k.endswith('meta_data.json'):
                os_files.pop(k, None)
        _register_uris(self.VERSION, {}, {}, os_files)
        self.assertRaises(openstack.NonReadable, _read_metadata_service)

    @hp.activate
    def test_bad_uuid(self):
        os_files = copy.deepcopy(OS_FILES)
        os_meta = copy.deepcopy(OSTACK_META)
        os_meta.pop('uuid')
        for k in list(os_files.keys()):
            if k.endswith('meta_data.json'):
                os_files[k] = json.dumps(os_meta)
        _register_uris(self.VERSION, {}, {}, os_files)
        self.assertRaises(openstack.BrokenMetadata, _read_metadata_service)

    @hp.activate
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

    @hp.activate
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

    @hp.activate
    def test_vendordata_invalid(self):
        os_files = copy.deepcopy(OS_FILES)
        for k in list(os_files.keys()):
            if k.endswith('vendor_data.json'):
                os_files[k] = '{'  # some invalid json
        _register_uris(self.VERSION, {}, {}, os_files)
        self.assertRaises(openstack.BrokenMetadata, _read_metadata_service)

    @hp.activate
    def test_metadata_invalid(self):
        os_files = copy.deepcopy(OS_FILES)
        for k in list(os_files.keys()):
            if k.endswith('meta_data.json'):
                os_files[k] = '{'  # some invalid json
        _register_uris(self.VERSION, {}, {}, os_files)
        self.assertRaises(openstack.BrokenMetadata, _read_metadata_service)

    @hp.activate
    def test_datasource(self):
        _register_uris(self.VERSION, EC2_FILES, EC2_META, OS_FILES)
        ds_os = ds.DataSourceOpenStack(settings.CFG_BUILTIN,
                                       None,
                                       helpers.Paths({}))
        self.assertIsNone(ds_os.version)
        found = ds_os.get_data(timeout=0.1, retries=0)
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
        self.assertEqual(ds_os.vendordata_raw, None)

    @hp.activate
    def test_bad_datasource_meta(self):
        os_files = copy.deepcopy(OS_FILES)
        for k in list(os_files.keys()):
            if k.endswith('meta_data.json'):
                os_files[k] = '{'  # some invalid json
        _register_uris(self.VERSION, {}, {}, os_files)
        ds_os = ds.DataSourceOpenStack(settings.CFG_BUILTIN,
                                       None,
                                       helpers.Paths({}))
        self.assertIsNone(ds_os.version)
        found = ds_os.get_data(timeout=0.1, retries=0)
        self.assertFalse(found)
        self.assertIsNone(ds_os.version)

    @hp.activate
    def test_no_datasource(self):
        os_files = copy.deepcopy(OS_FILES)
        for k in list(os_files.keys()):
            if k.endswith('meta_data.json'):
                os_files.pop(k)
        _register_uris(self.VERSION, {}, {}, os_files)
        ds_os = ds.DataSourceOpenStack(settings.CFG_BUILTIN,
                                       None,
                                       helpers.Paths({}))
        ds_os.ds_cfg = {
            'max_wait': 0,
            'timeout': 0,
        }
        self.assertIsNone(ds_os.version)
        found = ds_os.get_data(timeout=0.1, retries=0)
        self.assertFalse(found)
        self.assertIsNone(ds_os.version)

    @hp.activate
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
                                       helpers.Paths({}))
        ds_os.ds_cfg = {
            'max_wait': 0,
            'timeout': 0,
        }
        self.assertIsNone(ds_os.version)
        found = ds_os.get_data(timeout=0.1, retries=0)
        self.assertFalse(found)
        self.assertIsNone(ds_os.version)


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
        self.assertEqual(self.cvj({'foo': 'bar'}), None)

    def test_vd_load_dict_ci_dict(self):
        self.assertRaises(ValueError, self.cvj,
                          {'foo': 'bar', 'cloud-init': {'x': 1}})

    def test_vd_load_dict_ci_string(self):
        data = {'foo': 'bar', 'cloud-init': 'VENDOR_DATA'}
        self.assertEqual(self.cvj(data), data['cloud-init'])

    def test_vd_load_dict_ci_list(self):
        data = {'foo': 'bar', 'cloud-init': ['VD_1', 'VD_2']}
        self.assertEqual(self.cvj(data), data['cloud-init'])

# vi: ts=4 expandtab
