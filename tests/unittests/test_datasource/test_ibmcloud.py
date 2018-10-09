# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.helpers import Paths
from cloudinit.sources import DataSourceIBMCloud as ibm
from cloudinit.tests import helpers as test_helpers
from cloudinit import util

import base64
import copy
import json
from textwrap import dedent

mock = test_helpers.mock

D_PATH = "cloudinit.sources.DataSourceIBMCloud."


class TestIBMCloud(test_helpers.CiTestCase):
    """Test the datasource."""
    def setUp(self):
        super(TestIBMCloud, self).setUp()
        pass


@mock.patch(D_PATH + "_is_xen", return_value=True)
@mock.patch(D_PATH + "_is_ibm_provisioning")
@mock.patch(D_PATH + "util.blkid")
class TestGetIBMPlatform(test_helpers.CiTestCase):
    """Test the get_ibm_platform helper."""

    blkid_base = {
        "/dev/xvda1": {
            "DEVNAME": "/dev/xvda1", "LABEL": "cloudimg-bootfs",
            "TYPE": "ext3"},
        "/dev/xvda2": {
            "DEVNAME": "/dev/xvda2", "LABEL": "cloudimg-rootfs",
            "TYPE": "ext4"},
    }

    blkid_metadata_disk = {
        "/dev/xvdh1": {
            "DEVNAME": "/dev/xvdh1", "LABEL": "METADATA", "TYPE": "vfat",
            "SEC_TYPE": "msdos", "UUID": "681B-8C5D",
            "PARTUUID": "3d631e09-01"},
    }

    blkid_oscode_disk = {
        "/dev/xvdh": {
            "DEVNAME": "/dev/xvdh", "LABEL": "config-2", "TYPE": "vfat",
            "SEC_TYPE": "msdos", "UUID": ibm.IBM_CONFIG_UUID}
    }

    def setUp(self):
        self.blkid_metadata = copy.deepcopy(self.blkid_base)
        self.blkid_metadata.update(copy.deepcopy(self.blkid_metadata_disk))

        self.blkid_oscode = copy.deepcopy(self.blkid_base)
        self.blkid_oscode.update(copy.deepcopy(self.blkid_oscode_disk))

    def test_id_template_live_metadata(self, m_blkid, m_is_prov, _m_xen):
        """identify TEMPLATE_LIVE_METADATA."""
        m_blkid.return_value = self.blkid_metadata
        m_is_prov.return_value = False
        self.assertEqual(
            (ibm.Platforms.TEMPLATE_LIVE_METADATA, "/dev/xvdh1"),
            ibm.get_ibm_platform())

    def test_id_template_prov_metadata(self, m_blkid, m_is_prov, _m_xen):
        """identify TEMPLATE_PROVISIONING_METADATA."""
        m_blkid.return_value = self.blkid_metadata
        m_is_prov.return_value = True
        self.assertEqual(
            (ibm.Platforms.TEMPLATE_PROVISIONING_METADATA, "/dev/xvdh1"),
            ibm.get_ibm_platform())

    def test_id_template_prov_nodata(self, m_blkid, m_is_prov, _m_xen):
        """identify TEMPLATE_PROVISIONING_NODATA."""
        m_blkid.return_value = self.blkid_base
        m_is_prov.return_value = True
        self.assertEqual(
            (ibm.Platforms.TEMPLATE_PROVISIONING_NODATA, None),
            ibm.get_ibm_platform())

    def test_id_os_code(self, m_blkid, m_is_prov, _m_xen):
        """Identify OS_CODE."""
        m_blkid.return_value = self.blkid_oscode
        m_is_prov.return_value = False
        self.assertEqual((ibm.Platforms.OS_CODE, "/dev/xvdh"),
                         ibm.get_ibm_platform())

    def test_id_os_code_must_match_uuid(self, m_blkid, m_is_prov, _m_xen):
        """Test against false positive on openstack with non-ibm UUID."""
        blkid = self.blkid_oscode
        blkid["/dev/xvdh"]["UUID"] = "9999-9999"
        m_blkid.return_value = blkid
        m_is_prov.return_value = False
        self.assertEqual((None, None), ibm.get_ibm_platform())


@mock.patch(D_PATH + "_read_system_uuid", return_value=None)
@mock.patch(D_PATH + "get_ibm_platform")
class TestReadMD(test_helpers.CiTestCase):
    """Test the read_datasource helper."""

    template_md = {
        "files": [],
        "network_config": {"content_path": "/content/interfaces"},
        "hostname": "ci-fond-ram",
        "name": "ci-fond-ram",
        "domain": "testing.ci.cloud-init.org",
        "meta": {"dsmode": "net"},
        "uuid": "8e636730-9f5d-c4a5-327c-d7123c46e82f",
        "public_keys": {"1091307": "ssh-rsa AAAAB3NzaC1...Hw== ci-pubkey"},
    }

    oscode_md = {
        "hostname": "ci-grand-gannet.testing.ci.cloud-init.org",
        "name": "ci-grand-gannet",
        "uuid": "2f266908-8e6c-4818-9b5c-42e9cc66a785",
        "random_seed": "bm90LXJhbmRvbQo=",
        "crypt_key": "ssh-rsa AAAAB3NzaC1yc2..n6z/",
        "configuration_token": "eyJhbGciOi..M3ZA",
        "public_keys": {"1091307": "ssh-rsa AAAAB3N..Hw== ci-pubkey"},
    }

    content_interfaces = dedent("""\
        auto lo
        iface lo inet loopback

        auto eth0
        allow-hotplug eth0
        iface eth0 inet static
        address 10.82.43.5
        netmask 255.255.255.192
        """)

    userdata = b"#!/bin/sh\necho hi mom\n"
    # meta.js file gets json encoded userdata as a list.
    meta_js = '["#!/bin/sh\necho hi mom\n"]'
    vendor_data = {
        "cloud-init": "#!/bin/bash\necho 'root:$6$5ab01p1m1' | chpasswd -e"}

    network_data = {
        "links": [
            {"id": "interface_29402281", "name": "eth0", "mtu": None,
             "type": "phy", "ethernet_mac_address": "06:00:f1:bd:da:25"},
            {"id": "interface_29402279", "name": "eth1", "mtu": None,
             "type": "phy", "ethernet_mac_address": "06:98:5e:d0:7f:86"}
        ],
        "networks": [
            {"id": "network_109887563", "link": "interface_29402281",
             "type": "ipv4", "ip_address": "10.82.43.2",
             "netmask": "255.255.255.192",
             "routes": [
                 {"network": "10.0.0.0", "netmask": "255.0.0.0",
                  "gateway": "10.82.43.1"},
                 {"network": "161.26.0.0", "netmask": "255.255.0.0",
                  "gateway": "10.82.43.1"}]},
            {"id": "network_109887551", "link": "interface_29402279",
             "type": "ipv4", "ip_address": "108.168.194.252",
             "netmask": "255.255.255.248",
             "routes": [
                 {"network": "0.0.0.0", "netmask": "0.0.0.0",
                  "gateway": "108.168.194.249"}]}
        ],
        "services": [
            {"type": "dns", "address": "10.0.80.11"},
            {"type": "dns", "address": "10.0.80.12"}
        ],
    }

    sysuuid = '7f79ebf5-d791-43c3-a723-854e8389d59f'

    def _get_expected_metadata(self, os_md):
        """return expected 'metadata' for data loaded from meta_data.json."""
        os_md = copy.deepcopy(os_md)
        renames = (
            ('hostname', 'local-hostname'),
            ('uuid', 'instance-id'),
            ('public_keys', 'public-keys'))
        ret = {}
        for osname, mdname in renames:
            if osname in os_md:
                ret[mdname] = os_md[osname]
        if 'random_seed' in os_md:
            ret['random_seed'] = base64.b64decode(os_md['random_seed'])

        return ret

    def test_provisioning_md(self, m_platform, m_sysuuid):
        """Provisioning env with a metadata disk should return None."""
        m_platform.return_value = (
            ibm.Platforms.TEMPLATE_PROVISIONING_METADATA, "/dev/xvdh")
        self.assertIsNone(ibm.read_md())

    def test_provisioning_no_metadata(self, m_platform, m_sysuuid):
        """Provisioning env with no metadata disk should return None."""
        m_platform.return_value = (
            ibm.Platforms.TEMPLATE_PROVISIONING_NODATA, None)
        self.assertIsNone(ibm.read_md())

    def test_provisioning_not_ibm(self, m_platform, m_sysuuid):
        """Provisioning env but not identified as IBM should return None."""
        m_platform.return_value = (None, None)
        self.assertIsNone(ibm.read_md())

    def test_template_live(self, m_platform, m_sysuuid):
        """Template live environment should be identified."""
        tmpdir = self.tmp_dir()
        m_platform.return_value = (
            ibm.Platforms.TEMPLATE_LIVE_METADATA, tmpdir)
        m_sysuuid.return_value = self.sysuuid

        test_helpers.populate_dir(tmpdir, {
            'openstack/latest/meta_data.json': json.dumps(self.template_md),
            'openstack/latest/user_data': self.userdata,
            'openstack/content/interfaces': self.content_interfaces,
            'meta.js': self.meta_js})

        ret = ibm.read_md()
        self.assertEqual(ibm.Platforms.TEMPLATE_LIVE_METADATA,
                         ret['platform'])
        self.assertEqual(tmpdir, ret['source'])
        self.assertEqual(self.userdata, ret['userdata'])
        self.assertEqual(self._get_expected_metadata(self.template_md),
                         ret['metadata'])
        self.assertEqual(self.sysuuid, ret['system-uuid'])

    def test_os_code_live(self, m_platform, m_sysuuid):
        """Verify an os_code metadata path."""
        tmpdir = self.tmp_dir()
        m_platform.return_value = (ibm.Platforms.OS_CODE, tmpdir)
        netdata = json.dumps(self.network_data)
        test_helpers.populate_dir(tmpdir, {
            'openstack/latest/meta_data.json': json.dumps(self.oscode_md),
            'openstack/latest/user_data': self.userdata,
            'openstack/latest/vendor_data.json': json.dumps(self.vendor_data),
            'openstack/latest/network_data.json': netdata,
        })

        ret = ibm.read_md()
        self.assertEqual(ibm.Platforms.OS_CODE, ret['platform'])
        self.assertEqual(tmpdir, ret['source'])
        self.assertEqual(self.userdata, ret['userdata'])
        self.assertEqual(self._get_expected_metadata(self.oscode_md),
                         ret['metadata'])

    def test_os_code_live_no_userdata(self, m_platform, m_sysuuid):
        """Verify os_code without user-data."""
        tmpdir = self.tmp_dir()
        m_platform.return_value = (ibm.Platforms.OS_CODE, tmpdir)
        test_helpers.populate_dir(tmpdir, {
            'openstack/latest/meta_data.json': json.dumps(self.oscode_md),
            'openstack/latest/vendor_data.json': json.dumps(self.vendor_data),
        })

        ret = ibm.read_md()
        self.assertEqual(ibm.Platforms.OS_CODE, ret['platform'])
        self.assertEqual(tmpdir, ret['source'])
        self.assertIsNone(ret['userdata'])
        self.assertEqual(self._get_expected_metadata(self.oscode_md),
                         ret['metadata'])


class TestIsIBMProvisioning(test_helpers.FilesystemMockingTestCase):
    """Test the _is_ibm_provisioning method."""
    inst_log = "/root/swinstall.log"
    prov_cfg = "/root/provisioningConfiguration.cfg"
    boot_ref = "/proc/1/environ"
    with_logs = True

    def _call_with_root(self, rootd):
        self.reRoot(rootd)
        return ibm._is_ibm_provisioning()

    def test_no_config(self):
        """No provisioning config means not provisioning."""
        self.assertFalse(self._call_with_root(self.tmp_dir()))

    def test_config_only(self):
        """A provisioning config without a log means provisioning."""
        rootd = self.tmp_dir()
        test_helpers.populate_dir(rootd, {self.prov_cfg: "key=value"})
        self.assertTrue(self._call_with_root(rootd))

    def test_config_with_old_log(self):
        """A config with a log from previous boot is not provisioning."""
        rootd = self.tmp_dir()
        data = {self.prov_cfg: ("key=value\nkey2=val2\n", -10),
                self.inst_log: ("log data\n", -30),
                self.boot_ref: ("PWD=/", 0)}
        test_helpers.populate_dir_with_ts(rootd, data)
        self.assertFalse(self._call_with_root(rootd=rootd))
        self.assertIn("from previous boot", self.logs.getvalue())

    def test_config_with_new_log(self):
        """A config with a log from this boot is provisioning."""
        rootd = self.tmp_dir()
        data = {self.prov_cfg: ("key=value\nkey2=val2\n", -10),
                self.inst_log: ("log data\n", 30),
                self.boot_ref: ("PWD=/", 0)}
        test_helpers.populate_dir_with_ts(rootd, data)
        self.assertTrue(self._call_with_root(rootd=rootd))
        self.assertIn("from current boot", self.logs.getvalue())

    def test_config_and_log_no_reference(self):
        """If the config and log existed, but no reference, assume not."""
        rootd = self.tmp_dir()
        test_helpers.populate_dir(
            rootd, {self.prov_cfg: "key=value", self.inst_log: "log data\n"})
        self.assertFalse(self._call_with_root(rootd=rootd))
        self.assertIn("no reference file", self.logs.getvalue())


class TestDataSourceIBMCloud(test_helpers.CiTestCase):

    def setUp(self):
        super(TestDataSourceIBMCloud, self).setUp()
        self.tmp = self.tmp_dir()
        self.cloud_dir = self.tmp_path('cloud', dir=self.tmp)
        util.ensure_dir(self.cloud_dir)
        paths = Paths({'run_dir': self.tmp, 'cloud_dir': self.cloud_dir})
        self.ds = ibm.DataSourceIBMCloud(
            sys_cfg={}, distro=None, paths=paths)

    def test_get_data_false(self):
        """When read_md returns None, get_data returns False."""
        with mock.patch(D_PATH + 'read_md', return_value=None):
            self.assertFalse(self.ds.get_data())

    def test_get_data_processes_read_md(self):
        """get_data processes and caches content returned by read_md."""
        md = {
            'metadata': {}, 'networkdata': 'net', 'platform': 'plat',
            'source': 'src', 'system-uuid': 'uuid', 'userdata': 'ud',
            'vendordata': 'vd'}
        with mock.patch(D_PATH + 'read_md', return_value=md):
            self.assertTrue(self.ds.get_data())
        self.assertEqual('src', self.ds.source)
        self.assertEqual('plat', self.ds.platform)
        self.assertEqual({}, self.ds.metadata)
        self.assertEqual('ud', self.ds.userdata_raw)
        self.assertEqual('net', self.ds.network_json)
        self.assertEqual('vd', self.ds.vendordata_pure)
        self.assertEqual('uuid', self.ds.system_uuid)
        self.assertEqual('ibmcloud', self.ds.cloud_name)
        self.assertEqual('ibmcloud', self.ds.platform_type)
        self.assertEqual('plat (src)', self.ds.subplatform)

# vi: ts=4 expandtab
