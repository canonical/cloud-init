# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.sources import DataSourceOracle as oracle
from cloudinit.sources import BrokenMetadata
from cloudinit import helpers

from cloudinit.tests import helpers as test_helpers

from textwrap import dedent
import argparse
import httpretty
import json
import mock
import os
import six
import uuid

DS_PATH = "cloudinit.sources.DataSourceOracle"
MD_VER = "2013-10-17"


class TestDataSourceOracle(test_helpers.CiTestCase):
    """Test datasource DataSourceOracle."""

    ds_class = oracle.DataSourceOracle

    my_uuid = str(uuid.uuid4())
    my_md = {"uuid": "ocid1.instance.oc1.phx.abyhqlj",
             "name": "ci-vm1", "availability_zone": "phx-ad-3",
             "hostname": "ci-vm1hostname",
             "launch_index": 0, "files": [],
             "public_keys": {"0": "ssh-rsa AAAAB3N...== user@host"},
             "meta": {}}

    def _patch_instance(self, inst, patches):
        """Patch an instance of a class 'inst'.
        for each name, kwargs in patches:
             inst.name = mock.Mock(**kwargs)
        returns a namespace object that has
             namespace.name = mock.Mock(**kwargs)
        Do not bother with cleanup as instance is assumed transient."""
        mocks = argparse.Namespace()
        for name, kwargs in patches.items():
            imock = mock.Mock(name=name, spec=getattr(inst, name), **kwargs)
            setattr(mocks, name, imock)
            setattr(inst, name, imock)
        return mocks

    def _get_ds(self, sys_cfg=None, distro=None, paths=None, ud_proc=None,
                patches=None):
        if sys_cfg is None:
            sys_cfg = {}
        if patches is None:
            patches = {}
        if paths is None:
            tmpd = self.tmp_dir()
            dirs = {'cloud_dir': self.tmp_path('cloud_dir', tmpd),
                    'run_dir': self.tmp_path('run_dir')}
            for d in dirs.values():
                os.mkdir(d)
            paths = helpers.Paths(dirs)

        ds = self.ds_class(sys_cfg=sys_cfg, distro=distro,
                           paths=paths, ud_proc=ud_proc)

        return ds, self._patch_instance(ds, patches)

    def test_platform_not_viable_returns_false(self):
        ds, mocks = self._get_ds(
            patches={'_is_platform_viable': {'return_value': False}})
        self.assertFalse(ds._get_data())
        mocks._is_platform_viable.assert_called_once_with()

    @mock.patch(DS_PATH + "._is_iscsi_root", return_value=True)
    def test_without_userdata(self, m_is_iscsi_root):
        """If no user-data is provided, it should not be in return dict."""
        ds, mocks = self._get_ds(patches={
            '_is_platform_viable': {'return_value': True},
            'crawl_metadata': {
                'return_value': {
                    MD_VER: {'system_uuid': self.my_uuid,
                             'meta_data': self.my_md}}}})
        self.assertTrue(ds._get_data())
        mocks._is_platform_viable.assert_called_once_with()
        mocks.crawl_metadata.assert_called_once_with()
        self.assertEqual(self.my_uuid, ds.system_uuid)
        self.assertEqual(self.my_md['availability_zone'], ds.availability_zone)
        self.assertIn(self.my_md["public_keys"]["0"], ds.get_public_ssh_keys())
        self.assertEqual(self.my_md['uuid'], ds.get_instance_id())
        self.assertIsNone(ds.userdata_raw)

    @mock.patch(DS_PATH + "._is_iscsi_root", return_value=True)
    def test_with_vendordata(self, m_is_iscsi_root):
        """Test with vendor data."""
        vd = {'cloud-init': '#cloud-config\nkey: value'}
        ds, mocks = self._get_ds(patches={
            '_is_platform_viable': {'return_value': True},
            'crawl_metadata': {
                'return_value': {
                    MD_VER: {'system_uuid': self.my_uuid,
                             'meta_data': self.my_md,
                             'vendor_data': vd}}}})
        self.assertTrue(ds._get_data())
        mocks._is_platform_viable.assert_called_once_with()
        mocks.crawl_metadata.assert_called_once_with()
        self.assertEqual(vd, ds.vendordata_pure)
        self.assertEqual(vd['cloud-init'], ds.vendordata_raw)

    @mock.patch(DS_PATH + "._is_iscsi_root", return_value=True)
    def test_with_userdata(self, m_is_iscsi_root):
        """Ensure user-data is populated if present and is binary."""
        my_userdata = b'abcdefg'
        ds, mocks = self._get_ds(patches={
            '_is_platform_viable': {'return_value': True},
            'crawl_metadata': {
                'return_value': {
                    MD_VER: {'system_uuid': self.my_uuid,
                             'meta_data': self.my_md,
                             'user_data': my_userdata}}}})
        self.assertTrue(ds._get_data())
        mocks._is_platform_viable.assert_called_once_with()
        mocks.crawl_metadata.assert_called_once_with()
        self.assertEqual(self.my_uuid, ds.system_uuid)
        self.assertIn(self.my_md["public_keys"]["0"], ds.get_public_ssh_keys())
        self.assertEqual(self.my_md['uuid'], ds.get_instance_id())
        self.assertEqual(my_userdata, ds.userdata_raw)

    @mock.patch(DS_PATH + ".cmdline.read_kernel_cmdline_config")
    @mock.patch(DS_PATH + "._is_iscsi_root", return_value=True)
    def test_network_cmdline(self, m_is_iscsi_root, m_cmdline_config):
        """network_config should read kernel cmdline."""
        distro = mock.MagicMock()
        ds, _ = self._get_ds(distro=distro, patches={
            '_is_platform_viable': {'return_value': True},
            'crawl_metadata': {
                'return_value': {
                    MD_VER: {'system_uuid': self.my_uuid,
                             'meta_data': self.my_md}}}})
        ncfg = {'version': 1, 'config': [{'a': 'b'}]}
        m_cmdline_config.return_value = ncfg
        self.assertTrue(ds._get_data())
        self.assertEqual(ncfg, ds.network_config)
        m_cmdline_config.assert_called_once_with()
        self.assertFalse(distro.generate_fallback_config.called)

    @mock.patch(DS_PATH + ".cmdline.read_kernel_cmdline_config")
    @mock.patch(DS_PATH + "._is_iscsi_root", return_value=True)
    def test_network_fallback(self, m_is_iscsi_root, m_cmdline_config):
        """test that fallback network is generated if no kernel cmdline."""
        distro = mock.MagicMock()
        ds, _ = self._get_ds(distro=distro, patches={
            '_is_platform_viable': {'return_value': True},
            'crawl_metadata': {
                'return_value': {
                    MD_VER: {'system_uuid': self.my_uuid,
                             'meta_data': self.my_md}}}})
        ncfg = {'version': 1, 'config': [{'a': 'b'}]}
        m_cmdline_config.return_value = None
        self.assertTrue(ds._get_data())
        ncfg = {'version': 1, 'config': [{'distro1': 'value'}]}
        distro.generate_fallback_config.return_value = ncfg
        self.assertEqual(ncfg, ds.network_config)
        m_cmdline_config.assert_called_once_with()
        distro.generate_fallback_config.assert_called_once_with()
        self.assertEqual(1, m_cmdline_config.call_count)

        # test that the result got cached, and the methods not re-called.
        self.assertEqual(ncfg, ds.network_config)
        self.assertEqual(1, m_cmdline_config.call_count)


@mock.patch(DS_PATH + "._read_system_uuid", return_value=str(uuid.uuid4()))
class TestReadMetaData(test_helpers.HttprettyTestCase):
    """Test the read_metadata which interacts with http metadata service."""

    mdurl = oracle.METADATA_ENDPOINT
    my_md = {"uuid": "ocid1.instance.oc1.phx.abyhqlj",
             "name": "ci-vm1", "availability_zone": "phx-ad-3",
             "hostname": "ci-vm1hostname",
             "launch_index": 0, "files": [],
             "public_keys": {"0": "ssh-rsa AAAAB3N...== user@host"},
             "meta": {}}

    def populate_md(self, data):
        """call httppretty.register_url for each item dict 'data',
           including valid indexes. Text values converted to bytes."""
        httpretty.register_uri(
            httpretty.GET, self.mdurl + MD_VER + "/",
            '\n'.join(data.keys()).encode('utf-8'))
        for k, v in data.items():
            httpretty.register_uri(
                httpretty.GET, self.mdurl + MD_VER + "/" + k,
                v if not isinstance(v, six.text_type) else v.encode('utf-8'))

    def test_broken_no_sys_uuid(self, m_read_system_uuid):
        """Datasource requires ability to read system_uuid and true return."""
        m_read_system_uuid.return_value = None
        self.assertRaises(BrokenMetadata, oracle.read_metadata)

    def test_broken_no_metadata_json(self, m_read_system_uuid):
        """Datasource requires meta_data.json."""
        httpretty.register_uri(
            httpretty.GET, self.mdurl + MD_VER + "/",
            '\n'.join(['user_data']).encode('utf-8'))
        with self.assertRaises(BrokenMetadata) as cm:
            oracle.read_metadata()
        self.assertIn("Required field 'meta_data.json' missing",
                      str(cm.exception))

    def test_with_userdata(self, m_read_system_uuid):
        data = {'user_data': b'#!/bin/sh\necho hi world\n',
                'meta_data.json': json.dumps(self.my_md)}
        self.populate_md(data)
        result = oracle.read_metadata()[MD_VER]
        self.assertEqual(data['user_data'], result['user_data'])
        self.assertEqual(self.my_md, result['meta_data'])

    def test_without_userdata(self, m_read_system_uuid):
        data = {'meta_data.json': json.dumps(self.my_md)}
        self.populate_md(data)
        result = oracle.read_metadata()[MD_VER]
        self.assertNotIn('user_data', result)
        self.assertEqual(self.my_md, result['meta_data'])

    def test_unknown_fields_included(self, m_read_system_uuid):
        """Unknown fields listed in index should be included.
        And those ending in .json should be decoded."""
        some_data = {'key1': 'data1', 'subk1': {'subd1': 'subv'}}
        some_vendor_data = {'cloud-init': 'foo'}
        data = {'meta_data.json': json.dumps(self.my_md),
                'some_data.json': json.dumps(some_data),
                'vendor_data.json': json.dumps(some_vendor_data),
                'other_blob': b'this is blob'}
        self.populate_md(data)
        result = oracle.read_metadata()[MD_VER]
        self.assertNotIn('user_data', result)
        self.assertEqual(self.my_md, result['meta_data'])
        self.assertEqual(some_data, result['some_data'])
        self.assertEqual(some_vendor_data, result['vendor_data'])
        self.assertEqual(data['other_blob'], result['other_blob'])


class TestIsPlatformViable(test_helpers.CiTestCase):
    @mock.patch(DS_PATH + ".util.read_dmi_data",
                return_value=oracle.CHASSIS_ASSET_TAG)
    def test_expected_viable(self, m_read_dmi_data):
        """System with known chassis tag is viable."""
        self.assertTrue(oracle._is_platform_viable())
        m_read_dmi_data.assert_has_calls([mock.call('chassis-asset-tag')])

    @mock.patch(DS_PATH + ".util.read_dmi_data", return_value=None)
    def test_expected_not_viable_dmi_data_none(self, m_read_dmi_data):
        """System without known chassis tag is not viable."""
        self.assertFalse(oracle._is_platform_viable())
        m_read_dmi_data.assert_has_calls([mock.call('chassis-asset-tag')])

    @mock.patch(DS_PATH + ".util.read_dmi_data", return_value="LetsGoCubs")
    def test_expected_not_viable_other(self, m_read_dmi_data):
        """System with unnown chassis tag is not viable."""
        self.assertFalse(oracle._is_platform_viable())
        m_read_dmi_data.assert_has_calls([mock.call('chassis-asset-tag')])


class TestLoadIndex(test_helpers.CiTestCase):
    """_load_index handles parsing of an index into a proper list.
    The tests here guarantee correct parsing of html version or
    a fixed version.  See the function docstring for more doc."""

    _known_html_api_versions = dedent("""\
        <html>
        <head><title>Index of /openstack/</title></head>
        <body bgcolor="white">
        <h1>Index of /openstack/</h1><hr><pre><a href="../">../</a>
        <a href="2013-10-17/">2013-10-17/</a>   27-Jun-2018 12:22  -
        <a href="latest/">latest/</a>           27-Jun-2018 12:22  -
        </pre><hr></body>
        </html>""")

    _known_html_contents = dedent("""\
        <html>
        <head><title>Index of /openstack/2013-10-17/</title></head>
        <body bgcolor="white">
        <h1>Index of /openstack/2013-10-17/</h1><hr><pre><a href="../">../</a>
        <a href="meta_data.json">meta_data.json</a>  27-Jun-2018 12:22  679
        <a href="user_data">user_data</a>            27-Jun-2018 12:22  146
        </pre><hr></body>
        </html>""")

    def test_parse_html(self):
        """Test parsing of lower case html."""
        self.assertEqual(
            ['2013-10-17/', 'latest/'],
            oracle._load_index(self._known_html_api_versions))
        self.assertEqual(
            ['meta_data.json', 'user_data'],
            oracle._load_index(self._known_html_contents))

    def test_parse_html_upper(self):
        """Test parsing of upper case html, although known content is lower."""
        def _toupper(data):
            return data.replace("<a", "<A").replace("html>", "HTML>")

        self.assertEqual(
            ['2013-10-17/', 'latest/'],
            oracle._load_index(_toupper(self._known_html_api_versions)))
        self.assertEqual(
            ['meta_data.json', 'user_data'],
            oracle._load_index(_toupper(self._known_html_contents)))

    def test_parse_newline_list_with_endl(self):
        """Test parsing of newline separated list with ending newline."""
        self.assertEqual(
            ['2013-10-17/', 'latest/'],
            oracle._load_index("\n".join(["2013-10-17/", "latest/", ""])))
        self.assertEqual(
            ['meta_data.json', 'user_data'],
            oracle._load_index("\n".join(["meta_data.json", "user_data", ""])))

    def test_parse_newline_list_without_endl(self):
        """Test parsing of newline separated list with no ending newline.

        Actual openstack implementation does not include trailing newline."""
        self.assertEqual(
            ['2013-10-17/', 'latest/'],
            oracle._load_index("\n".join(["2013-10-17/", "latest/"])))
        self.assertEqual(
            ['meta_data.json', 'user_data'],
            oracle._load_index("\n".join(["meta_data.json", "user_data"])))


# vi: ts=4 expandtab
