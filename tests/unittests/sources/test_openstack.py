# Copyright (C) 2014 Yahoo! Inc.
#
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import copy
import json
import re
from io import StringIO
from unittest import mock
from urllib.parse import urlparse

import pytest
import responses

from cloudinit import settings, util
from cloudinit.sources import UNSET, BrokenMetadata
from cloudinit.sources import DataSourceOpenStack as ds
from cloudinit.sources import convert_vendordata
from cloudinit.sources.helpers import openstack
from tests.unittests import util as test_util

BASE_URL = "http://169.254.169.254"
PUBKEY = "ssh-rsa AAAAB3NzaC1....sIkJhq8wdX+4I3A4cYbYP ubuntu@server-460\n"
EC2_META = {
    "ami-id": "ami-00000001",
    "ami-launch-index": "0",
    "ami-manifest-path": "FIXME",
    "hostname": "sm-foo-test.novalocal",
    "instance-action": "none",
    "instance-id": "i-00000001",
    "instance-type": "m1.tiny",
    "local-hostname": "sm-foo-test.novalocal",
    "local-ipv4": "0.0.0.0",
    "public-hostname": "sm-foo-test.novalocal",
    "public-ipv4": "0.0.0.1",
    "reservation-id": "r-iru5qm4m",
}
USER_DATA = b"#!/bin/sh\necho This is user data\n"
VENDOR_DATA = {
    "magic": "",
}
VENDOR_DATA2: dict = {"static": {}}
OSTACK_META = {
    "availability_zone": "nova",
    "files": [
        {"content_path": "/content/0000", "path": "/etc/foo.cfg"},
        {"content_path": "/content/0001", "path": "/etc/bar/bar.cfg"},
    ],
    "hostname": "sm-foo-test.novalocal",
    "meta": {"dsmode": "local", "my-meta": "my-value"},
    "name": "sm-foo-test",
    "public_keys": {"mykey": PUBKEY},
    "uuid": "b0fa911b-69d4-4476-bbe2-1c92bff6535c",
}
CONTENT_0 = b"This is contents of /etc/foo.cfg\n"
CONTENT_1 = b"# this is /etc/bar/bar.cfg\n"
OS_FILES = {
    "openstack/content/0000": CONTENT_0,
    "openstack/content/0001": CONTENT_1,
    "openstack/latest/meta_data.json": json.dumps(OSTACK_META),
    "openstack/latest/network_data.json": json.dumps(
        {"links": [], "networks": [], "services": []}
    ),
    "openstack/latest/user_data": USER_DATA,
    "openstack/latest/vendor_data.json": json.dumps(VENDOR_DATA),
    "openstack/latest/vendor_data2.json": json.dumps(VENDOR_DATA2),
}
EC2_FILES = {
    "latest/user-data": USER_DATA,
}
EC2_VERSIONS = [
    "latest",
]

MOCK_PATH = "cloudinit.sources.DataSourceOpenStack."


@pytest.fixture(autouse=True)
def mock_is_resolvable():
    with mock.patch(f"{MOCK_PATH}util.is_resolvable"):
        yield


# TODO _register_uris should leverage test_ec2.register_mock_metaserver.
def _register_uris(version, ec2_files, ec2_meta, os_files, *, responses_mock):
    """Registers a set of url patterns into responses that will mimic the
    same data returned by the openstack metadata service (and ec2 service)."""

    def match_ec2_url(uri, headers):
        path = uri.path.strip("/")
        if not path:
            return (200, headers, "\n".join(EC2_VERSIONS))
        path = uri.path.lstrip("/")
        if path in ec2_files:
            return (200, headers, ec2_files.get(path))
        if path == "latest/meta-data/":
            buf = StringIO()
            for k, v in ec2_meta.items():
                if isinstance(v, (list, tuple)):
                    buf.write("%s/" % (k))
                else:
                    buf.write("%s" % (k))
                buf.write("\n")
            return (200, headers, buf.getvalue())
        if path.startswith("latest/meta-data/"):
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
        return (404, headers, "")

    def match_os_uri(uri, headers):
        path = uri.path.strip("/")
        if path == "openstack":
            return (200, headers, "\n".join([openstack.OS_LATEST]))
        path = uri.path.lstrip("/")
        if path in os_files:
            return (200, headers, os_files.get(path))
        return (404, headers, "")

    def get_request_callback(request):
        uri = urlparse(request.url)
        path = uri.path.lstrip("/").split("/")
        if path[0] == "openstack":
            return match_os_uri(uri, request.headers)
        return match_ec2_url(uri, request.headers)

    responses_mock.add_callback(
        responses.GET,
        re.compile(r"http://(169.254.169.254|\[fe80::a9fe:a9fe\])/.*"),
        callback=get_request_callback,
    )


def _read_metadata_service():
    return ds.read_metadata_service(BASE_URL, retries=0, timeout=0.1)


class TestOpenStackDataSource:

    VERSION = "latest"

    @pytest.fixture
    def ds_os(self, paths):
        return ds.DataSourceOpenStack(
            settings.CFG_BUILTIN,
            test_util.MockDistro(),
            paths,
        )

    @responses.activate
    def test_successful(self):
        _register_uris(
            self.VERSION,
            EC2_FILES,
            EC2_META,
            OS_FILES,
            responses_mock=responses,
        )
        f = _read_metadata_service()
        assert VENDOR_DATA == f.get("vendordata")
        assert VENDOR_DATA2 == f.get("vendordata2")
        assert CONTENT_0 == f["files"]["/etc/foo.cfg"]
        assert CONTENT_1 == f["files"]["/etc/bar/bar.cfg"]
        assert 2 == len(f["files"])
        assert USER_DATA == f.get("userdata")
        assert EC2_META == f.get("ec2-metadata")
        assert 2 == f.get("version")
        metadata = f["metadata"]
        assert "nova" == metadata.get("availability_zone")
        assert "sm-foo-test.novalocal" == metadata.get("hostname")
        assert "sm-foo-test.novalocal" == metadata.get("local-hostname")
        assert "sm-foo-test" == metadata.get("name")
        assert "b0fa911b-69d4-4476-bbe2-1c92bff6535c" == metadata.get("uuid")
        assert "b0fa911b-69d4-4476-bbe2-1c92bff6535c" == metadata.get(
            "instance-id"
        )

    @responses.activate
    def test_no_ec2(self):
        _register_uris(
            self.VERSION, {}, {}, OS_FILES, responses_mock=responses
        )
        f = _read_metadata_service()
        assert VENDOR_DATA == f.get("vendordata")
        assert VENDOR_DATA2 == f.get("vendordata2")
        assert CONTENT_0 == f["files"]["/etc/foo.cfg"]
        assert CONTENT_1 == f["files"]["/etc/bar/bar.cfg"]
        assert USER_DATA == f.get("userdata")
        assert {} == f.get("ec2-metadata")
        assert 2 == f.get("version")

    @responses.activate
    def test_bad_metadata(self):
        os_files = copy.deepcopy(OS_FILES)
        for k in list(os_files.keys()):
            if k.endswith("meta_data.json"):
                os_files.pop(k, None)
        _register_uris(
            self.VERSION, {}, {}, os_files, responses_mock=responses
        )
        with pytest.raises(openstack.NonReadable):
            _read_metadata_service()

    @responses.activate
    def test_bad_uuid(self):
        os_files = copy.deepcopy(OS_FILES)
        os_meta = copy.deepcopy(OSTACK_META)
        os_meta.pop("uuid")
        for k in list(os_files.keys()):
            if k.endswith("meta_data.json"):
                os_files[k] = json.dumps(os_meta)
        _register_uris(
            self.VERSION, {}, {}, os_files, responses_mock=responses
        )
        with pytest.raises(BrokenMetadata):
            _read_metadata_service()

    @responses.activate
    def test_userdata_empty(self):
        os_files = copy.deepcopy(OS_FILES)
        for k in list(os_files.keys()):
            if k.endswith("user_data"):
                os_files.pop(k, None)
        _register_uris(
            self.VERSION, {}, {}, os_files, responses_mock=responses
        )
        f = _read_metadata_service()
        assert VENDOR_DATA == f.get("vendordata")
        assert VENDOR_DATA2 == f.get("vendordata2")
        assert CONTENT_0 == f["files"]["/etc/foo.cfg"]
        assert CONTENT_1 == f["files"]["/etc/bar/bar.cfg"]
        assert not f.get("userdata")

    @responses.activate
    def test_vendordata_empty(self):
        os_files = copy.deepcopy(OS_FILES)
        for k in list(os_files.keys()):
            if k.endswith("vendor_data.json"):
                os_files.pop(k, None)
        _register_uris(
            self.VERSION, {}, {}, os_files, responses_mock=responses
        )
        f = _read_metadata_service()
        assert CONTENT_0 == f["files"]["/etc/foo.cfg"]
        assert CONTENT_1 == f["files"]["/etc/bar/bar.cfg"]
        assert not f.get("vendordata")

    @responses.activate
    def test_vendordata2_empty(self):
        os_files = copy.deepcopy(OS_FILES)
        for k in list(os_files.keys()):
            if k.endswith("vendor_data2.json"):
                os_files.pop(k, None)
        _register_uris(
            self.VERSION, {}, {}, os_files, responses_mock=responses
        )
        f = _read_metadata_service()
        assert CONTENT_0 == f["files"]["/etc/foo.cfg"]
        assert CONTENT_1 == f["files"]["/etc/bar/bar.cfg"]
        assert not f.get("vendordata2")

    @responses.activate
    def test_vendordata_invalid(self):
        os_files = copy.deepcopy(OS_FILES)
        for k in list(os_files.keys()):
            if k.endswith("vendor_data.json"):
                os_files[k] = "{"  # some invalid json
        _register_uris(
            self.VERSION, {}, {}, os_files, responses_mock=responses
        )
        with pytest.raises(BrokenMetadata):
            _read_metadata_service()

    @responses.activate
    def test_vendordata2_invalid(self):
        os_files = copy.deepcopy(OS_FILES)
        for k in list(os_files.keys()):
            if k.endswith("vendor_data2.json"):
                os_files[k] = "{"  # some invalid json
        _register_uris(
            self.VERSION, {}, {}, os_files, responses_mock=responses
        )
        with pytest.raises(BrokenMetadata):
            _read_metadata_service()

    @responses.activate
    def test_metadata_invalid(self):
        os_files = copy.deepcopy(OS_FILES)
        for k in list(os_files.keys()):
            if k.endswith("meta_data.json"):
                os_files[k] = "{"  # some invalid json
        _register_uris(
            self.VERSION, {}, {}, os_files, responses_mock=responses
        )
        with pytest.raises(BrokenMetadata):
            _read_metadata_service()

    @responses.activate
    @mock.patch("cloudinit.net.dhcp.maybe_perform_dhcp_discovery")
    def test_datasource(self, m_dhcp, ds_os):
        _register_uris(
            self.VERSION,
            EC2_FILES,
            EC2_META,
            OS_FILES,
            responses_mock=responses,
        )
        assert ds_os.version is None
        with mock.patch.object(ds_os, "override_ds_detect", return_value=True):
            assert ds_os.get_data()
        assert 2 == ds_os.version
        md = dict(ds_os.metadata)
        md.pop("instance-id", None)
        md.pop("local-hostname", None)
        assert OSTACK_META == md
        assert EC2_META == ds_os.ec2_metadata
        assert USER_DATA == ds_os.userdata_raw
        assert 2 == len(ds_os.files)
        assert ds_os.vendordata_raw is None
        m_dhcp.assert_not_called()

    @responses.activate
    @mock.patch("cloudinit.net.ephemeral.EphemeralIPv4Network")
    @mock.patch("cloudinit.net.ephemeral.maybe_perform_dhcp_discovery")
    @pytest.mark.usefixtures("disable_netdev_info")
    def test_local_datasource(self, m_dhcp, m_net, paths, tmp_path):
        """OpenStackLocal calls EphemeralDHCPNetwork and gets instance data."""
        _register_uris(
            self.VERSION,
            EC2_FILES,
            EC2_META,
            OS_FILES,
            responses_mock=responses,
        )
        distro = mock.MagicMock()
        distro.get_tmp_exec_path = str(tmp_path)
        ds_os_local = ds.DataSourceOpenStackLocal(
            settings.CFG_BUILTIN, distro, paths
        )
        distro.fallback_interface = "eth9"  # Monkey patch for dhcp
        m_dhcp.return_value = {
            "interface": "eth9",
            "fixed-address": "192.168.2.9",
            "routers": "192.168.2.1",
            "subnet-mask": "255.255.255.0",
            "broadcast-address": "192.168.2.255",
        }

        assert ds_os_local.version is None
        with mock.patch.object(
            ds_os_local, "override_ds_detect"
        ) as m_detect_os:
            m_detect_os.return_value = True
            assert ds_os_local.get_data() is True
        assert 2 == ds_os_local.version
        md = dict(ds_os_local.metadata)
        md.pop("instance-id", None)
        md.pop("local-hostname", None)
        assert OSTACK_META == md
        assert EC2_META == ds_os_local.ec2_metadata
        assert USER_DATA == ds_os_local.userdata_raw
        assert 2 == len(ds_os_local.files)
        assert ds_os_local.vendordata_raw is None
        m_dhcp.assert_called_with(distro, "eth9", None)

    @responses.activate
    def test_bad_datasource_meta(self, caplog, ds_os):
        os_files = copy.deepcopy(OS_FILES)
        for k in list(os_files.keys()):
            if k.endswith("meta_data.json"):
                os_files[k] = "{"  # some invalid json
        _register_uris(
            self.VERSION, {}, {}, os_files, responses_mock=responses
        )
        assert ds_os.version is None
        with mock.patch.object(ds_os, "override_ds_detect") as m_detect_os:
            m_detect_os.return_value = True
            found = ds_os.get_data()
        assert not found
        assert ds_os.version is None
        assert re.search(
            r"InvalidMetaDataException: Broken metadata address"
            r" http://(169.254.169.254|\[fe80::a9fe:a9fe\])",
            caplog.text,
        )

    @responses.activate
    def test_no_datasource(self, ds_os):
        os_files = copy.deepcopy(OS_FILES)
        for k in list(os_files.keys()):
            if k.endswith("meta_data.json"):
                os_files.pop(k)
        _register_uris(
            self.VERSION, {}, {}, os_files, responses_mock=responses
        )
        ds_os.ds_cfg = {
            "max_wait": 0,
            "timeout": 0,
        }
        assert ds_os.version is None
        with mock.patch.object(ds_os, "override_ds_detect", return_value=True):
            assert not ds_os.get_data()
        assert ds_os.version is None

    def test_network_config_disabled_by_datasource_config(self, ds_os):
        """The network_config can be disabled from datasource config."""
        mock_path = MOCK_PATH + "openstack.convert_net_json"
        ds_os.ds_cfg = {"apply_network_config": False}
        sample_json = {
            "links": [{"ethernet_mac_address": "mymac"}],
            "networks": [],
            "services": [],
        }
        ds_os.network_json = sample_json  # Ignore this content from metadata
        with mock.patch(mock_path) as m_convert_json:
            assert ds_os.network_config is None
        m_convert_json.assert_not_called()

    def test_network_config_from_network_json(self, caplog, ds_os):
        """The datasource gets network_config from network_data.json."""
        mock_path = MOCK_PATH + "openstack.convert_net_json"
        example_cfg = {"version": 1, "config": []}
        sample_json = {
            "links": [{"ethernet_mac_address": "mymac"}],
            "networks": [],
            "services": [],
        }
        ds_os.network_json = sample_json
        with mock.patch(mock_path) as m_convert_json:
            m_convert_json.return_value = example_cfg
            assert example_cfg == ds_os.network_config
        assert "network config provided via network_json" in caplog.text
        m_convert_json.assert_called_with(sample_json, known_macs=None)

    def test_network_config_cached(self, ds_os):
        """The datasource caches the network_config property."""
        mock_path = MOCK_PATH + "openstack.convert_net_json"
        example_cfg = {"version": 1, "config": []}
        ds_os._network_config = example_cfg
        with mock.patch(mock_path) as m_convert_json:
            assert example_cfg == ds_os.network_config
        m_convert_json.assert_not_called()

    @responses.activate
    def test_disabled_datasource(self, ds_os):
        os_files = copy.deepcopy(OS_FILES)
        os_meta = copy.deepcopy(OSTACK_META)
        os_meta["meta"] = {
            "dsmode": "disabled",
        }
        for k in list(os_files.keys()):
            if k.endswith("meta_data.json"):
                os_files[k] = json.dumps(os_meta)
        _register_uris(
            self.VERSION, {}, {}, os_files, responses_mock=responses
        )
        ds_os.ds_cfg = {
            "max_wait": 0,
            "timeout": 0,
        }
        assert ds_os.version is None
        with mock.patch.object(ds_os, "override_ds_detect") as m_detect_os:
            m_detect_os.return_value = True
            found = ds_os.get_data()
        assert not found
        assert ds_os.version is None

    @responses.activate
    def test_wb__crawl_metadata_does_not_persist(self, ds_os):
        """_crawl_metadata returns current metadata and does not cache."""
        _register_uris(
            self.VERSION,
            EC2_FILES,
            EC2_META,
            OS_FILES,
            responses_mock=responses,
        )
        crawled_data = ds_os._crawl_metadata()
        assert UNSET == ds_os.ec2_metadata
        assert ds_os.userdata_raw is None
        assert 0 == len(ds_os.files)
        assert ds_os.vendordata_raw is None
        assert [
            "dsmode",
            "ec2-metadata",
            "files",
            "metadata",
            "networkdata",
            "userdata",
            "vendordata",
            "vendordata2",
            "version",
        ] == sorted(crawled_data.keys())
        assert "local" == crawled_data["dsmode"]
        assert EC2_META == crawled_data["ec2-metadata"]
        assert 2 == len(crawled_data["files"])
        md = copy.deepcopy(crawled_data["metadata"])
        md.pop("instance-id")
        md.pop("local-hostname")
        assert OSTACK_META == md
        assert (
            json.loads(OS_FILES["openstack/latest/network_data.json"])
            == crawled_data["networkdata"]
        )
        assert USER_DATA == crawled_data["userdata"]
        assert VENDOR_DATA == crawled_data["vendordata"]
        assert VENDOR_DATA2 == crawled_data["vendordata2"]
        assert 2 == crawled_data["version"]


class TestVendorDataLoading:
    def cvj(self, data):
        return convert_vendordata(data)

    def test_vd_load_none(self):
        # non-existant vendor-data should return none
        assert self.cvj(None) is None

    def test_vd_load_string(self):
        assert self.cvj("foobar") == "foobar"

    def test_vd_load_list(self):
        data = [{"foo": "bar"}, "mystring", list(["another", "list"])]
        assert self.cvj(data) == data

    def test_vd_load_dict_no_ci(self):
        assert self.cvj({"foo": "bar"}) is None

    def test_vd_load_dict_ci_dict(self):
        with pytest.raises(ValueError):
            self.cvj({"foo": "bar", "cloud-init": {"x": 1}})

    def test_vd_load_dict_ci_string(self):
        data = {"foo": "bar", "cloud-init": "VENDOR_DATA"}
        assert self.cvj(data) == data["cloud-init"]

    def test_vd_load_dict_ci_list(self):
        data = {"foo": "bar", "cloud-init": ["VD_1", "VD_2"]}
        assert self.cvj(data) == data["cloud-init"]


@mock.patch(MOCK_PATH + "util.is_x86")
class TestDetectOpenStack:

    @pytest.fixture
    def fake_ds(self, paths) -> ds.DataSourceOpenStack:
        return ds.DataSourceOpenStack(
            settings.CFG_BUILTIN,
            test_util.MockDistro(),
            paths,
        )

    def test_ds_detect_non_intel_x86(self, m_is_x86, fake_ds):
        """Return True on non-intel platforms because dmi isn't conclusive."""
        m_is_x86.return_value = False
        assert fake_ds.ds_detect(), "Expected ds_detect == True"

    @mock.patch(MOCK_PATH + "util.get_proc_env")
    @mock.patch(MOCK_PATH + "dmi.read_dmi_data")
    def test_not_ds_detect_intel_x86_ec2(
        self, m_dmi, m_proc_env, m_is_x86, fake_ds
    ):
        """Return False on EC2 platforms."""
        m_is_x86.return_value = True
        # No product_name in proc/1/environ
        m_proc_env.return_value = {"HOME": "/"}

        def fake_dmi_read(dmi_key):
            if dmi_key == "system-product-name":
                return "HVM domU"  # Nothing 'openstackish' on EC2
            if dmi_key == "chassis-asset-tag":
                return ""  # Empty string on EC2
            assert False, "Unexpected dmi read of %s" % dmi_key

        m_dmi.side_effect = fake_dmi_read
        assert not fake_ds.ds_detect(), "Expected ds_detect == False on EC2"
        m_proc_env.assert_called_with(1)

    @mock.patch(MOCK_PATH + "dmi.read_dmi_data")
    def test_ds_detect_intel_product_name_compute(
        self, m_dmi, m_is_x86, fake_ds
    ):
        """Return True on OpenStack compute and nova instances."""
        m_is_x86.return_value = True
        openstack_product_names = ["OpenStack Nova", "OpenStack Compute"]

        for product_name in openstack_product_names:
            m_dmi.return_value = product_name
            assert fake_ds.ds_detect(), "Failed to ds_detect"

    @mock.patch(MOCK_PATH + "dmi.read_dmi_data")
    def test_ds_detect_opentelekomcloud_chassis_asset_tag(
        self, m_dmi, m_is_x86, fake_ds
    ):
        """Return True on OpenStack reporting OpenTelekomCloud asset-tag."""
        m_is_x86.return_value = True

        def fake_dmi_read(dmi_key):
            if dmi_key == "system-product-name":
                return "HVM domU"  # Nothing 'openstackish' on OpenTelekomCloud
            if dmi_key == "chassis-asset-tag":
                return "OpenTelekomCloud"
            assert False, "Unexpected dmi read of %s" % dmi_key

        m_dmi.side_effect = fake_dmi_read
        assert (
            fake_ds.ds_detect()
        ), "Expected ds_detect == True on OpenTelekomCloud"

    @mock.patch(MOCK_PATH + "dmi.read_dmi_data")
    def test_ds_detect_sapccloud_chassis_asset_tag(
        self, m_dmi, m_is_x86, fake_ds
    ):
        """Return True on OpenStack reporting SAP CCloud VM asset-tag."""
        m_is_x86.return_value = True

        def fake_dmi_read(dmi_key):
            if dmi_key == "system-product-name":
                return "VMware Virtual Platform"  # SAP CCloud uses VMware
            if dmi_key == "chassis-asset-tag":
                return "SAP CCloud VM"
            assert False, "Unexpected dmi read of %s" % dmi_key

        m_dmi.side_effect = fake_dmi_read
        assert (
            fake_ds.ds_detect()
        ), "Expected ds_detect == True on SAP CCloud VM"

    @mock.patch(MOCK_PATH + "dmi.read_dmi_data")
    def test_ds_detect_huaweicloud_chassis_asset_tag(
        self, m_dmi, m_is_x86, fake_ds
    ):
        """Return True on OpenStack reporting Huawei Cloud VM asset-tag."""
        m_is_x86.return_value = True

        def fake_asset_tag_dmi_read(dmi_key):
            if dmi_key == "system-product-name":
                return "c7.large.2"  # No match
            if dmi_key == "chassis-asset-tag":
                return "HUAWEICLOUD"
            assert False, "Unexpected dmi read of %s" % dmi_key

        m_dmi.side_effect = fake_asset_tag_dmi_read
        assert (
            fake_ds.ds_detect()
        ), "Expected ds_detect == True on Huawei Cloud VM"

    @mock.patch(MOCK_PATH + "dmi.read_dmi_data")
    def test_ds_detect_samsung_cloud_platform_chassis_asset_tag(
        self, m_dmi, m_is_x86, fake_ds
    ):
        """Return True on OpenStack reporting
        Samsung Cloud Platform VM asset-tag."""
        m_is_x86.return_value = True

        def fake_asset_tag_dmi_read(dmi_key):
            if dmi_key == "system-product-name":
                return "c7.large.2"  # No match
            if dmi_key == "chassis-asset-tag":
                return "Samsung Cloud Platform"
            assert False, "Unexpected dmi read of %s" % dmi_key

        m_dmi.side_effect = fake_asset_tag_dmi_read
        assert (
            fake_ds.ds_detect()
        ), "Expected ds_detect == True on Samsung Cloud Platform VM"

    @mock.patch(MOCK_PATH + "dmi.read_dmi_data")
    def test_ds_detect_oraclecloud_chassis_asset_tag(
        self, m_dmi, m_is_x86, fake_ds
    ):
        """Return True on OpenStack reporting Oracle cloud asset-tag."""
        m_is_x86.return_value = True

        def fake_dmi_read(dmi_key):
            if dmi_key == "system-product-name":
                return "Standard PC (i440FX + PIIX, 1996)"  # No match
            if dmi_key == "chassis-asset-tag":
                return "OracleCloud.com"
            assert False, "Unexpected dmi read of %s" % dmi_key

        m_dmi.side_effect = fake_dmi_read
        ds = fake_ds
        ds.sys_cfg = {"datasource_list": ["Oracle"]}
        assert ds.ds_detect(), "Expected ds_detect == True on OracleCloud.com"
        ds.sys_cfg = {"datasource_list": []}
        assert not ds.ds_detect(), "Expected ds_detect == False."

    @pytest.mark.parametrize(
        ["chassis_tag"], [("OpenStack Nova",), ("OpenStack Compute",)]
    )
    @mock.patch(MOCK_PATH + "dmi.read_dmi_data")
    def test_ds_detect_chassis_asset_tag(
        self, m_dmi, m_is_x86, chassis_tag, fake_ds
    ):
        """Return True on OpenStack reporting generic asset-tag."""
        m_is_x86.return_value = True

        def fake_dmi_read(dmi_key):
            if dmi_key == "system-product-name":
                return "Generic OpenStack Platform"
            if dmi_key == "chassis-asset-tag":
                return chassis_tag
            assert False, "Unexpected dmi read of %s" % dmi_key

        m_dmi.side_effect = fake_dmi_read
        assert (
            fake_ds.ds_detect()
        ), "Expected ds_detect == True on Generic OpenStack Platform"

    @mock.patch(MOCK_PATH + "util.get_proc_env")
    @mock.patch(MOCK_PATH + "dmi.read_dmi_data")
    def test_ds_detect_by_proc_1_environ(
        self, m_dmi, m_proc_env, m_is_x86, fake_ds
    ):
        """Return True when nova product_name specified in /proc/1/environ."""
        m_is_x86.return_value = True
        # Nova product_name in proc/1/environ
        m_proc_env.return_value = {
            "HOME": "/",
            "product_name": "OpenStack Nova",
        }

        def fake_dmi_read(dmi_key):
            if dmi_key == "system-product-name":
                return "HVM domU"  # Nothing 'openstackish'
            if dmi_key == "chassis-asset-tag":
                return ""  # Nothin 'openstackish'
            assert False, "Unexpected dmi read of %s" % dmi_key

        m_dmi.side_effect = fake_dmi_read
        assert (
            fake_ds.ds_detect()
        ), "Expected ds_detect == True on OpenTelekomCloud"
        m_proc_env.assert_called_with(1)


class TestMetadataReader:
    """Test the MetadataReader."""

    burl = "http://169.254.169.254/"
    md_base = {
        "availability_zone": "myaz1",
        "hostname": "sm-foo-test.novalocal",
        "keys": [{"data": PUBKEY, "name": "brickies", "type": "ssh"}],
        "launch_index": 0,
        "name": "sm-foo-test",
        "public_keys": {"mykey": PUBKEY},
        "project_id": "6a103f813b774b9fb15a4fcd36e1c056",
        "uuid": "b0fa911b-69d4-4476-bbe2-1c92bff6535c",
    }

    def register(self, path, body=None, status=200):
        content = body if not isinstance(body, str) else body.encode("utf-8")
        responses.add(
            responses.GET,
            self.burl + "openstack" + path,
            status=status,
            body=content,
        )

    def register_versions(self, versions):
        self.register("", "\n".join(versions))
        self.register("/", "\n".join(versions))

    def register_version(self, version, data):
        content = "\n".join(sorted(data.keys()))
        self.register(version, content)
        self.register(version + "/", content)
        for path, content in data.items():
            self.register("/%s/%s" % (version, path), content)
            self.register("/%s/%s" % (version, path), content)
        if "user_data" not in data:
            self.register("/%s/user_data" % version, "nodata", status=404)

    @responses.activate
    def test__find_working_version(self):
        """Test a working version ignores unsupported."""
        unsup = "2016-11-09"
        self.register_versions(
            [
                openstack.OS_FOLSOM,
                openstack.OS_LIBERTY,
                unsup,
                openstack.OS_LATEST,
            ]
        )
        assert (
            openstack.OS_LIBERTY
            == openstack.MetadataReader(self.burl)._find_working_version()
        )

    @responses.activate
    def test__find_working_version_uses_latest(self):
        """'latest' should be used if no supported versions."""
        unsup1, unsup2 = ("2016-11-09", "2017-06-06")
        self.register_versions([unsup1, unsup2, openstack.OS_LATEST])
        assert (
            openstack.OS_LATEST
            == openstack.MetadataReader(self.burl)._find_working_version()
        )

    @responses.activate
    def test_read_v2_os_ocata(self):
        """Validate return value of read_v2 for os_ocata data."""
        md = copy.deepcopy(self.md_base)
        md["devices"] = []
        network_data = {"links": [], "networks": [], "services": []}
        vendor_data = {}
        vendor_data2 = {"static": {}}

        data = {
            "meta_data.json": json.dumps(md),
            "network_data.json": json.dumps(network_data),
            "vendor_data.json": json.dumps(vendor_data),
            "vendor_data2.json": json.dumps(vendor_data2),
        }

        self.register_versions([openstack.OS_OCATA, openstack.OS_LATEST])
        self.register_version(openstack.OS_OCATA, data)

        mock_read_ec2 = mock.MagicMock(
            return_value={"instance-id": "unused-ec2"}
        )
        expected_md = copy.deepcopy(md)
        expected_md.update(
            {"instance-id": md["uuid"], "local-hostname": md["hostname"]}
        )
        expected = {
            "userdata": "",  # Annoying, no user-data results in empty string.
            "version": 2,
            "metadata": expected_md,
            "vendordata": vendor_data,
            "vendordata2": vendor_data2,
            "networkdata": network_data,
            "ec2-metadata": mock_read_ec2.return_value,
            "files": {},
        }
        reader = openstack.MetadataReader(self.burl)
        reader._read_ec2_metadata = mock_read_ec2
        assert expected == reader.read_v2()
        assert 1 == mock_read_ec2.call_count
