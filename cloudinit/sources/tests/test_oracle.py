# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.sources import DataSourceOracle as oracle
from cloudinit.sources import BrokenMetadata, NetworkConfigSource
from cloudinit import helpers

from cloudinit.tests import helpers as test_helpers

from textwrap import dedent
import argparse
import copy
import httpretty
import json
import os
import uuid
from unittest import mock

DS_PATH = "cloudinit.sources.DataSourceOracle"
MD_VER = "2013-10-17"

# `curl -L http://169.254.169.254/opc/v1/vnics/` on a Oracle Bare Metal Machine
# with a secondary VNIC attached (vnicId truncated for Python line length)
OPC_BM_SECONDARY_VNIC_RESPONSE = """\
[ {
  "vnicId" : "ocid1.vnic.oc1.phx.abyhqljtyvcucqkhdqmgjszebxe4hrb!!TRUNCATED||",
  "privateIp" : "10.0.0.8",
  "vlanTag" : 0,
  "macAddr" : "90:e2:ba:d4:f1:68",
  "virtualRouterIp" : "10.0.0.1",
  "subnetCidrBlock" : "10.0.0.0/24",
  "nicIndex" : 0
}, {
  "vnicId" : "ocid1.vnic.oc1.phx.abyhqljtfmkxjdy2sqidndiwrsg63zf!!TRUNCATED||",
  "privateIp" : "10.0.4.5",
  "vlanTag" : 1,
  "macAddr" : "02:00:17:05:CF:51",
  "virtualRouterIp" : "10.0.4.1",
  "subnetCidrBlock" : "10.0.4.0/24",
  "nicIndex" : 0
} ]"""

# `curl -L http://169.254.169.254/opc/v1/vnics/` on a Oracle Virtual Machine
# with a secondary VNIC attached
OPC_VM_SECONDARY_VNIC_RESPONSE = """\
[ {
  "vnicId" : "ocid1.vnic.oc1.phx.abyhqljtch72z5pd76cc2636qeqh7z_truncated",
  "privateIp" : "10.0.0.230",
  "vlanTag" : 1039,
  "macAddr" : "02:00:17:05:D1:DB",
  "virtualRouterIp" : "10.0.0.1",
  "subnetCidrBlock" : "10.0.0.0/24"
}, {
  "vnicId" : "ocid1.vnic.oc1.phx.abyhqljt4iew3gwmvrwrhhf3bp5drj_truncated",
  "privateIp" : "10.0.0.231",
  "vlanTag" : 1041,
  "macAddr" : "00:00:17:02:2B:B1",
  "virtualRouterIp" : "10.0.0.1",
  "subnetCidrBlock" : "10.0.0.0/24"
} ]"""


class TestDataSourceOracle(test_helpers.CiTestCase):
    """Test datasource DataSourceOracle."""

    with_logs = True

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

    def test_platform_info(self):
        """Return platform-related information for Oracle Datasource."""
        ds, _mocks = self._get_ds()
        self.assertEqual('oracle', ds.cloud_name)
        self.assertEqual('oracle', ds.platform_type)
        self.assertEqual(
            'metadata (http://169.254.169.254/openstack/)', ds.subplatform)

    def test_sys_cfg_can_enable_configure_secondary_nics(self):
        # Confirm that behaviour is toggled by sys_cfg
        ds, _mocks = self._get_ds()
        self.assertFalse(ds.ds_cfg['configure_secondary_nics'])

        sys_cfg = {
            'datasource': {'Oracle': {'configure_secondary_nics': True}}}
        ds, _mocks = self._get_ds(sys_cfg=sys_cfg)
        self.assertTrue(ds.ds_cfg['configure_secondary_nics'])

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

    @mock.patch(DS_PATH + "._add_network_config_from_opc_imds",
                side_effect=lambda network_config: network_config)
    @mock.patch(DS_PATH + ".cmdline.read_initramfs_config")
    @mock.patch(DS_PATH + "._is_iscsi_root", return_value=True)
    def test_network_cmdline(self, m_is_iscsi_root, m_initramfs_config,
                             _m_add_network_config_from_opc_imds):
        """network_config should read kernel cmdline."""
        distro = mock.MagicMock()
        ds, _ = self._get_ds(distro=distro, patches={
            '_is_platform_viable': {'return_value': True},
            'crawl_metadata': {
                'return_value': {
                    MD_VER: {'system_uuid': self.my_uuid,
                             'meta_data': self.my_md}}}})
        ncfg = {'version': 1, 'config': [{'a': 'b'}]}
        m_initramfs_config.return_value = ncfg
        self.assertTrue(ds._get_data())
        self.assertEqual(ncfg, ds.network_config)
        self.assertEqual([mock.call()], m_initramfs_config.call_args_list)
        self.assertFalse(distro.generate_fallback_config.called)

    @mock.patch(DS_PATH + "._add_network_config_from_opc_imds",
                side_effect=lambda network_config: network_config)
    @mock.patch(DS_PATH + ".cmdline.read_initramfs_config")
    @mock.patch(DS_PATH + "._is_iscsi_root", return_value=True)
    def test_network_fallback(self, m_is_iscsi_root, m_initramfs_config,
                              _m_add_network_config_from_opc_imds):
        """test that fallback network is generated if no kernel cmdline."""
        distro = mock.MagicMock()
        ds, _ = self._get_ds(distro=distro, patches={
            '_is_platform_viable': {'return_value': True},
            'crawl_metadata': {
                'return_value': {
                    MD_VER: {'system_uuid': self.my_uuid,
                             'meta_data': self.my_md}}}})
        ncfg = {'version': 1, 'config': [{'a': 'b'}]}
        m_initramfs_config.return_value = None
        self.assertTrue(ds._get_data())
        ncfg = {'version': 1, 'config': [{'distro1': 'value'}]}
        distro.generate_fallback_config.return_value = ncfg
        self.assertEqual(ncfg, ds.network_config)
        self.assertEqual([mock.call()], m_initramfs_config.call_args_list)
        distro.generate_fallback_config.assert_called_once_with()

        # test that the result got cached, and the methods not re-called.
        self.assertEqual(ncfg, ds.network_config)
        self.assertEqual(1, m_initramfs_config.call_count)

    @mock.patch(DS_PATH + "._add_network_config_from_opc_imds")
    @mock.patch(DS_PATH + ".cmdline.read_initramfs_config",
                return_value={'some': 'config'})
    @mock.patch(DS_PATH + "._is_iscsi_root", return_value=True)
    def test_secondary_nics_added_to_network_config_if_enabled(
            self, _m_is_iscsi_root, _m_initramfs_config,
            m_add_network_config_from_opc_imds):

        needle = object()

        def network_config_side_effect(network_config):
            network_config['secondary_added'] = needle

        m_add_network_config_from_opc_imds.side_effect = (
            network_config_side_effect)

        distro = mock.MagicMock()
        ds, _ = self._get_ds(distro=distro, patches={
            '_is_platform_viable': {'return_value': True},
            'crawl_metadata': {
                'return_value': {
                    MD_VER: {'system_uuid': self.my_uuid,
                             'meta_data': self.my_md}}}})
        ds.ds_cfg['configure_secondary_nics'] = True
        self.assertEqual(needle, ds.network_config['secondary_added'])

    @mock.patch(DS_PATH + "._add_network_config_from_opc_imds")
    @mock.patch(DS_PATH + ".cmdline.read_initramfs_config",
                return_value={'some': 'config'})
    @mock.patch(DS_PATH + "._is_iscsi_root", return_value=True)
    def test_secondary_nics_not_added_to_network_config_by_default(
            self, _m_is_iscsi_root, _m_initramfs_config,
            m_add_network_config_from_opc_imds):

        def network_config_side_effect(network_config):
            network_config['secondary_added'] = True

        m_add_network_config_from_opc_imds.side_effect = (
            network_config_side_effect)

        distro = mock.MagicMock()
        ds, _ = self._get_ds(distro=distro, patches={
            '_is_platform_viable': {'return_value': True},
            'crawl_metadata': {
                'return_value': {
                    MD_VER: {'system_uuid': self.my_uuid,
                             'meta_data': self.my_md}}}})
        self.assertNotIn('secondary_added', ds.network_config)

    @mock.patch(DS_PATH + "._add_network_config_from_opc_imds")
    @mock.patch(DS_PATH + ".cmdline.read_initramfs_config")
    @mock.patch(DS_PATH + "._is_iscsi_root", return_value=True)
    def test_secondary_nic_failure_isnt_blocking(
            self, _m_is_iscsi_root, m_initramfs_config,
            m_add_network_config_from_opc_imds):

        m_add_network_config_from_opc_imds.side_effect = Exception()

        distro = mock.MagicMock()
        ds, _ = self._get_ds(distro=distro, patches={
            '_is_platform_viable': {'return_value': True},
            'crawl_metadata': {
                'return_value': {
                    MD_VER: {'system_uuid': self.my_uuid,
                             'meta_data': self.my_md}}}})
        ds.ds_cfg['configure_secondary_nics'] = True
        self.assertEqual(ds.network_config, m_initramfs_config.return_value)
        self.assertIn('Failed to fetch secondary network configuration',
                      self.logs.getvalue())

    def test_ds_network_cfg_preferred_over_initramfs(self):
        """Ensure that DS net config is preferred over initramfs config"""
        network_config_sources = oracle.DataSourceOracle.network_config_sources
        self.assertLess(
            network_config_sources.index(NetworkConfigSource.ds),
            network_config_sources.index(NetworkConfigSource.initramfs)
        )


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
                v if not isinstance(v, str) else v.encode('utf-8'))

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


class TestNetworkConfigFromOpcImds(test_helpers.CiTestCase):

    with_logs = True

    def setUp(self):
        super(TestNetworkConfigFromOpcImds, self).setUp()
        self.add_patch(DS_PATH + '.readurl', 'm_readurl')
        self.add_patch(DS_PATH + '.get_interfaces_by_mac',
                       'm_get_interfaces_by_mac')

    def test_failure_to_readurl(self):
        # readurl failures should just bubble out to the caller
        self.m_readurl.side_effect = Exception('oh no')
        with self.assertRaises(Exception) as excinfo:
            oracle._add_network_config_from_opc_imds({})
        self.assertEqual(str(excinfo.exception), 'oh no')

    def test_empty_response(self):
        # empty response error should just bubble out to the caller
        self.m_readurl.return_value = ''
        with self.assertRaises(Exception):
            oracle._add_network_config_from_opc_imds([])

    def test_invalid_json(self):
        # invalid JSON error should just bubble out to the caller
        self.m_readurl.return_value = '{'
        with self.assertRaises(Exception):
            oracle._add_network_config_from_opc_imds([])

    def test_no_secondary_nics_does_not_mutate_input(self):
        self.m_readurl.return_value = json.dumps([{}])
        # We test this by passing in a non-dict to ensure that no dict
        # operations are used; failure would be seen as exceptions
        oracle._add_network_config_from_opc_imds(object())

    def test_bare_metal_machine_skipped(self):
        # nicIndex in the first entry indicates a bare metal machine
        self.m_readurl.return_value = OPC_BM_SECONDARY_VNIC_RESPONSE
        # We test this by passing in a non-dict to ensure that no dict
        # operations are used
        self.assertFalse(oracle._add_network_config_from_opc_imds(object()))
        self.assertIn('bare metal machine', self.logs.getvalue())

    def test_missing_mac_skipped(self):
        self.m_readurl.return_value = OPC_VM_SECONDARY_VNIC_RESPONSE
        self.m_get_interfaces_by_mac.return_value = {}

        network_config = {'version': 1, 'config': [{'primary': 'nic'}]}
        oracle._add_network_config_from_opc_imds(network_config)

        self.assertEqual(1, len(network_config['config']))
        self.assertIn(
            'Interface with MAC 00:00:17:02:2b:b1 not found; skipping',
            self.logs.getvalue())

    def test_missing_mac_skipped_v2(self):
        self.m_readurl.return_value = OPC_VM_SECONDARY_VNIC_RESPONSE
        self.m_get_interfaces_by_mac.return_value = {}

        network_config = {'version': 2, 'ethernets': {'primary': {'nic': {}}}}
        oracle._add_network_config_from_opc_imds(network_config)

        self.assertEqual(1, len(network_config['ethernets']))
        self.assertIn(
            'Interface with MAC 00:00:17:02:2b:b1 not found; skipping',
            self.logs.getvalue())

    def test_secondary_nic(self):
        self.m_readurl.return_value = OPC_VM_SECONDARY_VNIC_RESPONSE
        mac_addr, nic_name = '00:00:17:02:2b:b1', 'ens3'
        self.m_get_interfaces_by_mac.return_value = {
            mac_addr: nic_name,
        }

        network_config = {'version': 1, 'config': [{'primary': 'nic'}]}
        oracle._add_network_config_from_opc_imds(network_config)

        # The input is mutated
        self.assertEqual(2, len(network_config['config']))

        secondary_nic_cfg = network_config['config'][1]
        self.assertEqual(nic_name, secondary_nic_cfg['name'])
        self.assertEqual('physical', secondary_nic_cfg['type'])
        self.assertEqual(mac_addr, secondary_nic_cfg['mac_address'])
        self.assertEqual(9000, secondary_nic_cfg['mtu'])

        self.assertEqual(1, len(secondary_nic_cfg['subnets']))
        subnet_cfg = secondary_nic_cfg['subnets'][0]
        # These values are hard-coded in OPC_VM_SECONDARY_VNIC_RESPONSE
        self.assertEqual('10.0.0.231', subnet_cfg['address'])

    def test_secondary_nic_v2(self):
        self.m_readurl.return_value = OPC_VM_SECONDARY_VNIC_RESPONSE
        mac_addr, nic_name = '00:00:17:02:2b:b1', 'ens3'
        self.m_get_interfaces_by_mac.return_value = {
            mac_addr: nic_name,
        }

        network_config = {'version': 2, 'ethernets': {'primary': {'nic': {}}}}
        oracle._add_network_config_from_opc_imds(network_config)

        # The input is mutated
        self.assertEqual(2, len(network_config['ethernets']))

        secondary_nic_cfg = network_config['ethernets']['ens3']
        self.assertFalse(secondary_nic_cfg['dhcp4'])
        self.assertFalse(secondary_nic_cfg['dhcp6'])
        self.assertEqual(mac_addr, secondary_nic_cfg['match']['macaddress'])
        self.assertEqual(9000, secondary_nic_cfg['mtu'])

        self.assertEqual(1, len(secondary_nic_cfg['addresses']))
        # These values are hard-coded in OPC_VM_SECONDARY_VNIC_RESPONSE
        self.assertEqual('10.0.0.231', secondary_nic_cfg['addresses'][0])


class TestNetworkConfigFiltersNetFailover(test_helpers.CiTestCase):

    with_logs = True

    def setUp(self):
        super(TestNetworkConfigFiltersNetFailover, self).setUp()
        self.add_patch(DS_PATH + '.get_interfaces_by_mac',
                       'm_get_interfaces_by_mac')
        self.add_patch(DS_PATH + '.is_netfail_master', 'm_netfail_master')

    def test_ignore_bogus_network_config(self):
        netcfg = {'something': 'here'}
        passed_netcfg = copy.copy(netcfg)
        oracle._ensure_netfailover_safe(passed_netcfg)
        self.assertEqual(netcfg, passed_netcfg)

    def test_ignore_network_config_unknown_versions(self):
        netcfg = {'something': 'here', 'version': 3}
        passed_netcfg = copy.copy(netcfg)
        oracle._ensure_netfailover_safe(passed_netcfg)
        self.assertEqual(netcfg, passed_netcfg)

    def test_checks_v1_type_physical_interfaces(self):
        mac_addr, nic_name = '00:00:17:02:2b:b1', 'ens3'
        self.m_get_interfaces_by_mac.return_value = {
            mac_addr: nic_name,
        }
        netcfg = {'version': 1, 'config': [
            {'type': 'physical', 'name': nic_name, 'mac_address': mac_addr,
             'subnets': [{'type': 'dhcp4'}]}]}
        passed_netcfg = copy.copy(netcfg)
        self.m_netfail_master.return_value = False
        oracle._ensure_netfailover_safe(passed_netcfg)
        self.assertEqual(netcfg, passed_netcfg)
        self.assertEqual([mock.call(nic_name)],
                         self.m_netfail_master.call_args_list)

    def test_checks_v1_skips_non_phys_interfaces(self):
        mac_addr, nic_name = '00:00:17:02:2b:b1', 'bond0'
        self.m_get_interfaces_by_mac.return_value = {
            mac_addr: nic_name,
        }
        netcfg = {'version': 1, 'config': [
            {'type': 'bond', 'name': nic_name, 'mac_address': mac_addr,
             'subnets': [{'type': 'dhcp4'}]}]}
        passed_netcfg = copy.copy(netcfg)
        oracle._ensure_netfailover_safe(passed_netcfg)
        self.assertEqual(netcfg, passed_netcfg)
        self.assertEqual(0, self.m_netfail_master.call_count)

    def test_removes_master_mac_property_v1(self):
        nic_master, mac_master = 'ens3', self.random_string()
        nic_other, mac_other = 'ens7', self.random_string()
        nic_extra, mac_extra = 'enp0s1f2', self.random_string()
        self.m_get_interfaces_by_mac.return_value = {
            mac_master: nic_master,
            mac_other: nic_other,
            mac_extra: nic_extra,
        }
        netcfg = {'version': 1, 'config': [
            {'type': 'physical', 'name': nic_master,
             'mac_address': mac_master},
            {'type': 'physical', 'name': nic_other, 'mac_address': mac_other},
            {'type': 'physical', 'name': nic_extra, 'mac_address': mac_extra},
        ]}

        def _is_netfail_master(iface):
            if iface == 'ens3':
                return True
            return False
        self.m_netfail_master.side_effect = _is_netfail_master
        expected_cfg = {'version': 1, 'config': [
            {'type': 'physical', 'name': nic_master},
            {'type': 'physical', 'name': nic_other, 'mac_address': mac_other},
            {'type': 'physical', 'name': nic_extra, 'mac_address': mac_extra},
        ]}
        oracle._ensure_netfailover_safe(netcfg)
        self.assertEqual(expected_cfg, netcfg)

    def test_checks_v2_type_ethernet_interfaces(self):
        mac_addr, nic_name = '00:00:17:02:2b:b1', 'ens3'
        self.m_get_interfaces_by_mac.return_value = {
            mac_addr: nic_name,
        }
        netcfg = {'version': 2, 'ethernets': {
            nic_name: {'dhcp4': True, 'critical': True, 'set-name': nic_name,
                       'match': {'macaddress': mac_addr}}}}
        passed_netcfg = copy.copy(netcfg)
        self.m_netfail_master.return_value = False
        oracle._ensure_netfailover_safe(passed_netcfg)
        self.assertEqual(netcfg, passed_netcfg)
        self.assertEqual([mock.call(nic_name)],
                         self.m_netfail_master.call_args_list)

    def test_skips_v2_non_ethernet_interfaces(self):
        mac_addr, nic_name = '00:00:17:02:2b:b1', 'wlps0'
        self.m_get_interfaces_by_mac.return_value = {
            mac_addr: nic_name,
        }
        netcfg = {'version': 2, 'wifis': {
            nic_name: {'dhcp4': True, 'critical': True, 'set-name': nic_name,
                       'match': {'macaddress': mac_addr}}}}
        passed_netcfg = copy.copy(netcfg)
        oracle._ensure_netfailover_safe(passed_netcfg)
        self.assertEqual(netcfg, passed_netcfg)
        self.assertEqual(0, self.m_netfail_master.call_count)

    def test_removes_master_mac_property_v2(self):
        nic_master, mac_master = 'ens3', self.random_string()
        nic_other, mac_other = 'ens7', self.random_string()
        nic_extra, mac_extra = 'enp0s1f2', self.random_string()
        self.m_get_interfaces_by_mac.return_value = {
            mac_master: nic_master,
            mac_other: nic_other,
            mac_extra: nic_extra,
        }
        netcfg = {'version': 2, 'ethernets': {
            nic_extra: {'dhcp4': True, 'set-name': nic_extra,
                        'match': {'macaddress': mac_extra}},
            nic_other: {'dhcp4': True, 'set-name': nic_other,
                        'match': {'macaddress': mac_other}},
            nic_master: {'dhcp4': True, 'set-name': nic_master,
                         'match': {'macaddress': mac_master}},
        }}

        def _is_netfail_master(iface):
            if iface == 'ens3':
                return True
            return False
        self.m_netfail_master.side_effect = _is_netfail_master

        expected_cfg = {'version': 2, 'ethernets': {
            nic_master: {'dhcp4': True, 'match': {'name': nic_master}},
            nic_extra: {'dhcp4': True, 'set-name': nic_extra,
                        'match': {'macaddress': mac_extra}},
            nic_other: {'dhcp4': True, 'set-name': nic_other,
                        'match': {'macaddress': mac_other}},
        }}
        oracle._ensure_netfailover_safe(netcfg)
        import pprint
        pprint.pprint(netcfg)
        print('---- ^^ modified ^^ ---- vv original vv ----')
        pprint.pprint(expected_cfg)
        self.assertEqual(expected_cfg, netcfg)


# vi: ts=4 expandtab
