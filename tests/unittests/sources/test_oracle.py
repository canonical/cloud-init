# This file is part of cloud-init. See LICENSE file for license information.

import base64
import copy
import json
from contextlib import ExitStack
from unittest import mock

import pytest

from cloudinit.sources import DataSourceOracle as oracle
from cloudinit.sources import NetworkConfigSource
from cloudinit.sources.DataSourceOracle import OpcMetadata
from cloudinit.url_helper import UrlError
from tests.unittests import helpers as test_helpers

DS_PATH = "cloudinit.sources.DataSourceOracle"

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


# Fetched with `curl http://169.254.169.254/opc/v1/instance/` (and then
# truncated for line length)
OPC_V2_METADATA = """\
{
  "availabilityDomain" : "qIZq:PHX-AD-1",
  "faultDomain" : "FAULT-DOMAIN-2",
  "compartmentId" : "ocid1.tenancy.oc1..aaaaaaaao7f7cccogqrg5emjxkxmTRUNCATED",
  "displayName" : "instance-20200320-1400",
  "hostname" : "instance-20200320-1400",
  "id" : "ocid1.instance.oc1.phx.anyhqljtniwq6syc3nex55sep5w34qbwmw6TRUNCATED",
  "image" : "ocid1.image.oc1.phx.aaaaaaaagmkn4gdhvvx24kiahh2b2qchsicTRUNCATED",
  "metadata" : {
    "ssh_authorized_keys" : "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQ truncated",
    "user_data" : "IyEvYmluL3NoCnRvdWNoIC90bXAvZm9v"
  },
  "region" : "phx",
  "canonicalRegionName" : "us-phoenix-1",
  "ociAdName" : "phx-ad-3",
  "shape" : "VM.Standard2.1",
  "state" : "Running",
  "timeCreated" : 1584727285318,
  "agentConfig" : {
    "monitoringDisabled" : true,
    "managementDisabled" : true
  }
}"""

# Just a small meaningless change to differentiate the two metadatas
OPC_V1_METADATA = OPC_V2_METADATA.replace("ocid1.instance", "ocid2.instance")


@pytest.fixture
def metadata_version():
    return 2


@pytest.fixture
def oracle_ds(request, fixture_utils, paths, metadata_version):
    """
    Return an instantiated DataSourceOracle.

    This also performs the mocking required for the default test case:
        * ``_read_system_uuid`` returns something,
        * ``_is_platform_viable`` returns True,
        * ``_is_iscsi_root`` returns True (the simpler code path),
        * ``read_opc_metadata`` returns ``OPC_V1_METADATA``

    (This uses the paths fixture for the required helpers.Paths object, and the
    fixture_utils fixture for fetching markers.)
    """
    sys_cfg = fixture_utils.closest_marker_first_arg_or(
        request, "ds_sys_cfg", mock.MagicMock()
    )
    metadata = OpcMetadata(metadata_version, json.loads(OPC_V2_METADATA), None)
    with mock.patch(DS_PATH + "._read_system_uuid", return_value="someuuid"):
        with mock.patch(DS_PATH + "._is_platform_viable", return_value=True):
            with mock.patch(DS_PATH + "._is_iscsi_root", return_value=True):
                with mock.patch(
                    DS_PATH + ".read_opc_metadata",
                    return_value=metadata,
                ):
                    yield oracle.DataSourceOracle(
                        sys_cfg=sys_cfg,
                        distro=mock.Mock(),
                        paths=paths,
                    )


class TestDataSourceOracle:
    def test_platform_info(self, oracle_ds):
        assert "oracle" == oracle_ds.cloud_name
        assert "oracle" == oracle_ds.platform_type

    def test_subplatform_before_fetch(self, oracle_ds):
        assert "unknown" == oracle_ds.subplatform

    def test_platform_info_after_fetch(self, oracle_ds):
        oracle_ds._get_data()
        assert (
            "metadata (http://169.254.169.254/opc/v2/)"
            == oracle_ds.subplatform
        )

    @pytest.mark.parametrize("metadata_version", [1])
    def test_v1_platform_info_after_fetch(self, oracle_ds):
        oracle_ds._get_data()
        assert (
            "metadata (http://169.254.169.254/opc/v1/)"
            == oracle_ds.subplatform
        )

    def test_secondary_nics_disabled_by_default(self, oracle_ds):
        assert not oracle_ds.ds_cfg["configure_secondary_nics"]

    @pytest.mark.ds_sys_cfg(
        {"datasource": {"Oracle": {"configure_secondary_nics": True}}}
    )
    def test_sys_cfg_can_enable_configure_secondary_nics(self, oracle_ds):
        assert oracle_ds.ds_cfg["configure_secondary_nics"]


class TestIsPlatformViable(test_helpers.CiTestCase):
    @mock.patch(
        DS_PATH + ".dmi.read_dmi_data", return_value=oracle.CHASSIS_ASSET_TAG
    )
    def test_expected_viable(self, m_read_dmi_data):
        """System with known chassis tag is viable."""
        self.assertTrue(oracle._is_platform_viable())
        m_read_dmi_data.assert_has_calls([mock.call("chassis-asset-tag")])

    @mock.patch(DS_PATH + ".dmi.read_dmi_data", return_value=None)
    def test_expected_not_viable_dmi_data_none(self, m_read_dmi_data):
        """System without known chassis tag is not viable."""
        self.assertFalse(oracle._is_platform_viable())
        m_read_dmi_data.assert_has_calls([mock.call("chassis-asset-tag")])

    @mock.patch(DS_PATH + ".dmi.read_dmi_data", return_value="LetsGoCubs")
    def test_expected_not_viable_other(self, m_read_dmi_data):
        """System with unnown chassis tag is not viable."""
        self.assertFalse(oracle._is_platform_viable())
        m_read_dmi_data.assert_has_calls([mock.call("chassis-asset-tag")])


@mock.patch(
    "cloudinit.net.is_openvswitch_internal_interface",
    mock.Mock(return_value=False),
)
class TestNetworkConfigFromOpcImds:
    def test_no_secondary_nics_does_not_mutate_input(self, oracle_ds):
        oracle_ds._vnics_data = [{}]
        # We test this by using in a non-dict to ensure that no dict
        # operations are used; failure would be seen as exceptions
        oracle_ds._network_config = object()
        oracle_ds._add_network_config_from_opc_imds()

    def test_bare_metal_machine_skipped(self, oracle_ds, caplog):
        # nicIndex in the first entry indicates a bare metal machine
        oracle_ds._vnics_data = json.loads(OPC_BM_SECONDARY_VNIC_RESPONSE)
        # We test this by using a non-dict to ensure that no dict
        # operations are used
        oracle_ds._network_config = object()
        oracle_ds._add_network_config_from_opc_imds()
        assert "bare metal machine" in caplog.text

    def test_missing_mac_skipped(self, oracle_ds, caplog):
        oracle_ds._vnics_data = json.loads(OPC_VM_SECONDARY_VNIC_RESPONSE)

        oracle_ds._network_config = {
            "version": 1,
            "config": [{"primary": "nic"}],
        }
        with mock.patch(DS_PATH + ".get_interfaces_by_mac", return_value={}):
            oracle_ds._add_network_config_from_opc_imds()

        assert 1 == len(oracle_ds.network_config["config"])
        assert (
            "Interface with MAC 00:00:17:02:2b:b1 not found; skipping"
            in caplog.text
        )

    def test_missing_mac_skipped_v2(self, oracle_ds, caplog):
        oracle_ds._vnics_data = json.loads(OPC_VM_SECONDARY_VNIC_RESPONSE)

        oracle_ds._network_config = {
            "version": 2,
            "ethernets": {"primary": {"nic": {}}},
        }
        with mock.patch(DS_PATH + ".get_interfaces_by_mac", return_value={}):
            oracle_ds._add_network_config_from_opc_imds()

        assert 1 == len(oracle_ds.network_config["ethernets"])
        assert (
            "Interface with MAC 00:00:17:02:2b:b1 not found; skipping"
            in caplog.text
        )

    def test_secondary_nic(self, oracle_ds):
        oracle_ds._vnics_data = json.loads(OPC_VM_SECONDARY_VNIC_RESPONSE)
        oracle_ds._network_config = {
            "version": 1,
            "config": [{"primary": "nic"}],
        }
        mac_addr, nic_name = "00:00:17:02:2b:b1", "ens3"
        with mock.patch(
            DS_PATH + ".get_interfaces_by_mac",
            return_value={mac_addr: nic_name},
        ):
            oracle_ds._add_network_config_from_opc_imds()

        # The input is mutated
        assert 2 == len(oracle_ds.network_config["config"])

        secondary_nic_cfg = oracle_ds.network_config["config"][1]
        assert nic_name == secondary_nic_cfg["name"]
        assert "physical" == secondary_nic_cfg["type"]
        assert mac_addr == secondary_nic_cfg["mac_address"]
        assert 9000 == secondary_nic_cfg["mtu"]

        assert 1 == len(secondary_nic_cfg["subnets"])
        subnet_cfg = secondary_nic_cfg["subnets"][0]
        # These values are hard-coded in OPC_VM_SECONDARY_VNIC_RESPONSE
        assert "10.0.0.231" == subnet_cfg["address"]

    def test_secondary_nic_v2(self, oracle_ds):
        oracle_ds._vnics_data = json.loads(OPC_VM_SECONDARY_VNIC_RESPONSE)
        oracle_ds._network_config = {
            "version": 2,
            "ethernets": {"primary": {"nic": {}}},
        }
        mac_addr, nic_name = "00:00:17:02:2b:b1", "ens3"
        with mock.patch(
            DS_PATH + ".get_interfaces_by_mac",
            return_value={mac_addr: nic_name},
        ):
            oracle_ds._add_network_config_from_opc_imds()

        # The input is mutated
        assert 2 == len(oracle_ds.network_config["ethernets"])

        secondary_nic_cfg = oracle_ds.network_config["ethernets"]["ens3"]
        assert secondary_nic_cfg["dhcp4"] is False
        assert secondary_nic_cfg["dhcp6"] is False
        assert mac_addr == secondary_nic_cfg["match"]["macaddress"]
        assert 9000 == secondary_nic_cfg["mtu"]

        assert 1 == len(secondary_nic_cfg["addresses"])
        # These values are hard-coded in OPC_VM_SECONDARY_VNIC_RESPONSE
        assert "10.0.0.231" == secondary_nic_cfg["addresses"][0]


class TestNetworkConfigFiltersNetFailover(test_helpers.CiTestCase):
    def setUp(self):
        super(TestNetworkConfigFiltersNetFailover, self).setUp()
        self.add_patch(
            DS_PATH + ".get_interfaces_by_mac", "m_get_interfaces_by_mac"
        )
        self.add_patch(DS_PATH + ".is_netfail_master", "m_netfail_master")

    def test_ignore_bogus_network_config(self):
        netcfg = {"something": "here"}
        passed_netcfg = copy.copy(netcfg)
        oracle._ensure_netfailover_safe(passed_netcfg)
        self.assertEqual(netcfg, passed_netcfg)

    def test_ignore_network_config_unknown_versions(self):
        netcfg = {"something": "here", "version": 3}
        passed_netcfg = copy.copy(netcfg)
        oracle._ensure_netfailover_safe(passed_netcfg)
        self.assertEqual(netcfg, passed_netcfg)

    def test_checks_v1_type_physical_interfaces(self):
        mac_addr, nic_name = "00:00:17:02:2b:b1", "ens3"
        self.m_get_interfaces_by_mac.return_value = {
            mac_addr: nic_name,
        }
        netcfg = {
            "version": 1,
            "config": [
                {
                    "type": "physical",
                    "name": nic_name,
                    "mac_address": mac_addr,
                    "subnets": [{"type": "dhcp4"}],
                }
            ],
        }
        passed_netcfg = copy.copy(netcfg)
        self.m_netfail_master.return_value = False
        oracle._ensure_netfailover_safe(passed_netcfg)
        self.assertEqual(netcfg, passed_netcfg)
        self.assertEqual(
            [mock.call(nic_name)], self.m_netfail_master.call_args_list
        )

    def test_checks_v1_skips_non_phys_interfaces(self):
        mac_addr, nic_name = "00:00:17:02:2b:b1", "bond0"
        self.m_get_interfaces_by_mac.return_value = {
            mac_addr: nic_name,
        }
        netcfg = {
            "version": 1,
            "config": [
                {
                    "type": "bond",
                    "name": nic_name,
                    "mac_address": mac_addr,
                    "subnets": [{"type": "dhcp4"}],
                }
            ],
        }
        passed_netcfg = copy.copy(netcfg)
        oracle._ensure_netfailover_safe(passed_netcfg)
        self.assertEqual(netcfg, passed_netcfg)
        self.assertEqual(0, self.m_netfail_master.call_count)

    def test_removes_master_mac_property_v1(self):
        nic_master, mac_master = "ens3", self.random_string()
        nic_other, mac_other = "ens7", self.random_string()
        nic_extra, mac_extra = "enp0s1f2", self.random_string()
        self.m_get_interfaces_by_mac.return_value = {
            mac_master: nic_master,
            mac_other: nic_other,
            mac_extra: nic_extra,
        }
        netcfg = {
            "version": 1,
            "config": [
                {
                    "type": "physical",
                    "name": nic_master,
                    "mac_address": mac_master,
                },
                {
                    "type": "physical",
                    "name": nic_other,
                    "mac_address": mac_other,
                },
                {
                    "type": "physical",
                    "name": nic_extra,
                    "mac_address": mac_extra,
                },
            ],
        }

        def _is_netfail_master(iface):
            if iface == "ens3":
                return True
            return False

        self.m_netfail_master.side_effect = _is_netfail_master
        expected_cfg = {
            "version": 1,
            "config": [
                {"type": "physical", "name": nic_master},
                {
                    "type": "physical",
                    "name": nic_other,
                    "mac_address": mac_other,
                },
                {
                    "type": "physical",
                    "name": nic_extra,
                    "mac_address": mac_extra,
                },
            ],
        }
        oracle._ensure_netfailover_safe(netcfg)
        self.assertEqual(expected_cfg, netcfg)

    def test_checks_v2_type_ethernet_interfaces(self):
        mac_addr, nic_name = "00:00:17:02:2b:b1", "ens3"
        self.m_get_interfaces_by_mac.return_value = {
            mac_addr: nic_name,
        }
        netcfg = {
            "version": 2,
            "ethernets": {
                nic_name: {
                    "dhcp4": True,
                    "critical": True,
                    "set-name": nic_name,
                    "match": {"macaddress": mac_addr},
                }
            },
        }
        passed_netcfg = copy.copy(netcfg)
        self.m_netfail_master.return_value = False
        oracle._ensure_netfailover_safe(passed_netcfg)
        self.assertEqual(netcfg, passed_netcfg)
        self.assertEqual(
            [mock.call(nic_name)], self.m_netfail_master.call_args_list
        )

    def test_skips_v2_non_ethernet_interfaces(self):
        mac_addr, nic_name = "00:00:17:02:2b:b1", "wlps0"
        self.m_get_interfaces_by_mac.return_value = {
            mac_addr: nic_name,
        }
        netcfg = {
            "version": 2,
            "wifis": {
                nic_name: {
                    "dhcp4": True,
                    "critical": True,
                    "set-name": nic_name,
                    "match": {"macaddress": mac_addr},
                }
            },
        }
        passed_netcfg = copy.copy(netcfg)
        oracle._ensure_netfailover_safe(passed_netcfg)
        self.assertEqual(netcfg, passed_netcfg)
        self.assertEqual(0, self.m_netfail_master.call_count)

    def test_removes_master_mac_property_v2(self):
        nic_master, mac_master = "ens3", self.random_string()
        nic_other, mac_other = "ens7", self.random_string()
        nic_extra, mac_extra = "enp0s1f2", self.random_string()
        self.m_get_interfaces_by_mac.return_value = {
            mac_master: nic_master,
            mac_other: nic_other,
            mac_extra: nic_extra,
        }
        netcfg = {
            "version": 2,
            "ethernets": {
                nic_extra: {
                    "dhcp4": True,
                    "set-name": nic_extra,
                    "match": {"macaddress": mac_extra},
                },
                nic_other: {
                    "dhcp4": True,
                    "set-name": nic_other,
                    "match": {"macaddress": mac_other},
                },
                nic_master: {
                    "dhcp4": True,
                    "set-name": nic_master,
                    "match": {"macaddress": mac_master},
                },
            },
        }

        def _is_netfail_master(iface):
            if iface == "ens3":
                return True
            return False

        self.m_netfail_master.side_effect = _is_netfail_master

        expected_cfg = {
            "version": 2,
            "ethernets": {
                nic_master: {"dhcp4": True, "match": {"name": nic_master}},
                nic_extra: {
                    "dhcp4": True,
                    "set-name": nic_extra,
                    "match": {"macaddress": mac_extra},
                },
                nic_other: {
                    "dhcp4": True,
                    "set-name": nic_other,
                    "match": {"macaddress": mac_other},
                },
            },
        }
        oracle._ensure_netfailover_safe(netcfg)
        import pprint

        pprint.pprint(netcfg)
        print("---- ^^ modified ^^ ---- vv original vv ----")
        pprint.pprint(expected_cfg)
        self.assertEqual(expected_cfg, netcfg)


def _mock_v2_urls(httpretty):
    def instance_callback(request, uri, response_headers):
        print(response_headers)
        assert request.headers.get("Authorization") == "Bearer Oracle"
        return [200, response_headers, OPC_V2_METADATA]

    def vnics_callback(request, uri, response_headers):
        assert request.headers.get("Authorization") == "Bearer Oracle"
        return [200, response_headers, OPC_BM_SECONDARY_VNIC_RESPONSE]

    httpretty.register_uri(
        httpretty.GET,
        "http://169.254.169.254/opc/v2/instance/",
        body=instance_callback,
    )
    httpretty.register_uri(
        httpretty.GET,
        "http://169.254.169.254/opc/v2/vnics/",
        body=vnics_callback,
    )


def _mock_no_v2_urls(httpretty):
    httpretty.register_uri(
        httpretty.GET,
        "http://169.254.169.254/opc/v2/instance/",
        status=404,
    )
    httpretty.register_uri(
        httpretty.GET,
        "http://169.254.169.254/opc/v1/instance/",
        body=OPC_V1_METADATA,
    )
    httpretty.register_uri(
        httpretty.GET,
        "http://169.254.169.254/opc/v1/vnics/",
        body=OPC_BM_SECONDARY_VNIC_RESPONSE,
    )


class TestReadOpcMetadata:
    # See https://docs.pytest.org/en/stable/example
    # /parametrize.html#parametrizing-conditional-raising
    does_not_raise = ExitStack

    @mock.patch("cloudinit.url_helper.time.sleep", lambda _: None)
    @pytest.mark.parametrize(
        "version,setup_urls,instance_data,fetch_vnics,vnics_data",
        [
            (
                2,
                _mock_v2_urls,
                json.loads(OPC_V2_METADATA),
                True,
                json.loads(OPC_BM_SECONDARY_VNIC_RESPONSE),
            ),
            (2, _mock_v2_urls, json.loads(OPC_V2_METADATA), False, None),
            (
                1,
                _mock_no_v2_urls,
                json.loads(OPC_V1_METADATA),
                True,
                json.loads(OPC_BM_SECONDARY_VNIC_RESPONSE),
            ),
            (1, _mock_no_v2_urls, json.loads(OPC_V1_METADATA), False, None),
        ],
    )
    def test_metadata_returned(
        self,
        version,
        setup_urls,
        instance_data,
        fetch_vnics,
        vnics_data,
        httpretty,
    ):
        setup_urls(httpretty)
        metadata = oracle.read_opc_metadata(fetch_vnics_data=fetch_vnics)

        assert version == metadata.version
        assert instance_data == metadata.instance_data
        assert vnics_data == metadata.vnics_data

    # No need to actually wait between retries in the tests
    @mock.patch("cloudinit.url_helper.time.sleep", lambda _: None)
    @pytest.mark.parametrize(
        "v2_failure_count,v1_failure_count,expected_body,expectation",
        [
            (1, 0, json.loads(OPC_V2_METADATA), does_not_raise()),
            (2, 0, json.loads(OPC_V2_METADATA), does_not_raise()),
            (3, 0, json.loads(OPC_V1_METADATA), does_not_raise()),
            (3, 1, json.loads(OPC_V1_METADATA), does_not_raise()),
            (3, 2, json.loads(OPC_V1_METADATA), does_not_raise()),
            (3, 3, None, pytest.raises(UrlError)),
        ],
    )
    def test_retries(
        self,
        v2_failure_count,
        v1_failure_count,
        expected_body,
        expectation,
        httpretty,
    ):
        v2_responses = [httpretty.Response("", status=404)] * v2_failure_count
        v2_responses.append(httpretty.Response(OPC_V2_METADATA))
        v1_responses = [httpretty.Response("", status=404)] * v1_failure_count
        v1_responses.append(httpretty.Response(OPC_V1_METADATA))

        httpretty.register_uri(
            httpretty.GET,
            "http://169.254.169.254/opc/v1/instance/",
            responses=v1_responses,
        )
        httpretty.register_uri(
            httpretty.GET,
            "http://169.254.169.254/opc/v2/instance/",
            responses=v2_responses,
        )
        with expectation:
            assert expected_body == oracle.read_opc_metadata().instance_data


class TestCommon_GetDataBehaviour:
    """This test class tests behaviour common to iSCSI and non-iSCSI root.

    It defines a fixture, parameterized_oracle_ds, which is used in all the
    tests herein to test that the commonly expected behaviour is the same with
    iSCSI root and without.

    (As non-iSCSI root behaviour is a superset of iSCSI root behaviour this
    class is implicitly also testing all iSCSI root behaviour so there is no
    separate class for that case.)
    """

    @pytest.fixture(params=[True, False])
    def parameterized_oracle_ds(self, request, oracle_ds):
        """oracle_ds parameterized for iSCSI and non-iSCSI root respectively"""
        is_iscsi_root = request.param
        with ExitStack() as stack:
            stack.enter_context(
                mock.patch(
                    DS_PATH + "._is_iscsi_root", return_value=is_iscsi_root
                )
            )
            if not is_iscsi_root:
                stack.enter_context(
                    mock.patch(DS_PATH + ".net.find_fallback_nic")
                )
                stack.enter_context(
                    mock.patch(DS_PATH + ".dhcp.EphemeralDHCPv4")
                )
            yield oracle_ds

    @mock.patch(
        DS_PATH + "._is_platform_viable", mock.Mock(return_value=False)
    )
    def test_false_if_platform_not_viable(
        self,
        parameterized_oracle_ds,
    ):
        assert not parameterized_oracle_ds._get_data()

    @pytest.mark.parametrize(
        "keyname,expected_value",
        (
            ("availability-zone", "phx-ad-3"),
            ("launch-index", 0),
            ("local-hostname", "instance-20200320-1400"),
            (
                "instance-id",
                "ocid1.instance.oc1.phx"
                ".anyhqljtniwq6syc3nex55sep5w34qbwmw6TRUNCATED",
            ),
            ("name", "instance-20200320-1400"),
            (
                "public_keys",
                "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQ truncated",
            ),
        ),
    )
    def test_metadata_keys_set_correctly(
        self,
        keyname,
        expected_value,
        parameterized_oracle_ds,
    ):
        assert parameterized_oracle_ds._get_data()
        assert expected_value == parameterized_oracle_ds.metadata[keyname]

    @pytest.mark.parametrize(
        "attribute_name,expected_value",
        [
            ("_crawled_metadata", json.loads(OPC_V2_METADATA)),
            (
                "userdata_raw",
                base64.b64decode(b"IyEvYmluL3NoCnRvdWNoIC90bXAvZm9v"),
            ),
            ("system_uuid", "my-test-uuid"),
        ],
    )
    @mock.patch(
        DS_PATH + "._read_system_uuid", mock.Mock(return_value="my-test-uuid")
    )
    def test_attributes_set_correctly(
        self,
        attribute_name,
        expected_value,
        parameterized_oracle_ds,
    ):
        assert parameterized_oracle_ds._get_data()
        assert expected_value == getattr(
            parameterized_oracle_ds, attribute_name
        )

    @pytest.mark.parametrize(
        "ssh_keys,expected_value",
        [
            # No SSH keys in metadata => no keys detected
            (None, []),
            # Empty SSH keys in metadata => no keys detected
            ("", []),
            # Single SSH key in metadata => single key detected
            ("ssh-rsa ... test@test", ["ssh-rsa ... test@test"]),
            # Multiple SSH keys in metadata => multiple keys detected
            (
                "ssh-rsa ... test@test\nssh-rsa ... test2@test2",
                ["ssh-rsa ... test@test", "ssh-rsa ... test2@test2"],
            ),
        ],
    )
    def test_public_keys_handled_correctly(
        self, ssh_keys, expected_value, parameterized_oracle_ds
    ):
        instance_data = json.loads(OPC_V1_METADATA)
        if ssh_keys is None:
            del instance_data["metadata"]["ssh_authorized_keys"]
        else:
            instance_data["metadata"]["ssh_authorized_keys"] = ssh_keys
        metadata = OpcMetadata(None, instance_data, None)
        with mock.patch(
            DS_PATH + ".read_opc_metadata",
            mock.Mock(return_value=metadata),
        ):
            assert parameterized_oracle_ds._get_data()
            assert (
                expected_value == parameterized_oracle_ds.get_public_ssh_keys()
            )

    def test_missing_user_data_handled_gracefully(
        self, parameterized_oracle_ds
    ):
        instance_data = json.loads(OPC_V1_METADATA)
        del instance_data["metadata"]["user_data"]
        metadata = OpcMetadata(None, instance_data, None)
        with mock.patch(
            DS_PATH + ".read_opc_metadata",
            mock.Mock(return_value=metadata),
        ):
            assert parameterized_oracle_ds._get_data()

        assert parameterized_oracle_ds.userdata_raw is None

    def test_missing_metadata_handled_gracefully(
        self, parameterized_oracle_ds
    ):
        instance_data = json.loads(OPC_V1_METADATA)
        del instance_data["metadata"]
        metadata = OpcMetadata(None, instance_data, None)
        with mock.patch(
            DS_PATH + ".read_opc_metadata",
            mock.Mock(return_value=metadata),
        ):
            assert parameterized_oracle_ds._get_data()

        assert parameterized_oracle_ds.userdata_raw is None
        assert [] == parameterized_oracle_ds.get_public_ssh_keys()


@mock.patch(DS_PATH + "._is_iscsi_root", lambda: False)
class TestNonIscsiRoot_GetDataBehaviour:
    @mock.patch(DS_PATH + ".dhcp.EphemeralDHCPv4")
    @mock.patch(DS_PATH + ".net.find_fallback_nic")
    def test_read_opc_metadata_called_with_ephemeral_dhcp(
        self, m_find_fallback_nic, m_EphemeralDHCPv4, oracle_ds
    ):
        in_context_manager = False

        def enter_context_manager():
            nonlocal in_context_manager
            in_context_manager = True

        def exit_context_manager(*args):
            nonlocal in_context_manager
            in_context_manager = False

        m_EphemeralDHCPv4.return_value.__enter__.side_effect = (
            enter_context_manager
        )
        m_EphemeralDHCPv4.return_value.__exit__.side_effect = (
            exit_context_manager
        )

        def assert_in_context_manager(**kwargs):
            assert in_context_manager
            return mock.MagicMock()

        with mock.patch(
            DS_PATH + ".read_opc_metadata",
            mock.Mock(side_effect=assert_in_context_manager),
        ):
            assert oracle_ds._get_data()

        assert [
            mock.call(
                iface=m_find_fallback_nic.return_value,
                connectivity_url_data={
                    "headers": {"Authorization": "Bearer Oracle"},
                    "url": "http://169.254.169.254/opc/v2/instance/",
                },
            )
        ] == m_EphemeralDHCPv4.call_args_list


@mock.patch(DS_PATH + ".get_interfaces_by_mac", lambda: {})
@mock.patch(DS_PATH + ".cmdline.read_initramfs_config")
class TestNetworkConfig:
    def test_network_config_cached(self, m_read_initramfs_config, oracle_ds):
        """.network_config should be cached"""
        assert 0 == m_read_initramfs_config.call_count
        oracle_ds.network_config  # pylint: disable=pointless-statement
        assert 1 == m_read_initramfs_config.call_count
        oracle_ds.network_config  # pylint: disable=pointless-statement
        assert 1 == m_read_initramfs_config.call_count

    def test_network_cmdline(self, m_read_initramfs_config, oracle_ds):
        """network_config should prefer initramfs config over fallback"""
        ncfg = {"version": 1, "config": [{"a": "b"}]}
        m_read_initramfs_config.return_value = copy.deepcopy(ncfg)

        assert ncfg == oracle_ds.network_config
        assert 0 == oracle_ds.distro.generate_fallback_config.call_count

    def test_network_fallback(self, m_read_initramfs_config, oracle_ds):
        """network_config should prefer initramfs config over fallback"""
        ncfg = {"version": 1, "config": [{"a": "b"}]}

        m_read_initramfs_config.return_value = None
        oracle_ds.distro.generate_fallback_config.return_value = copy.deepcopy(
            ncfg
        )

        assert ncfg == oracle_ds.network_config

    @pytest.mark.parametrize(
        "configure_secondary_nics,expect_secondary_nics",
        [(True, True), (False, False), (None, False)],
    )
    def test_secondary_nic_addition(
        self,
        m_read_initramfs_config,
        configure_secondary_nics,
        expect_secondary_nics,
        oracle_ds,
    ):
        """Test that _add_network_config_from_opc_imds is called as expected

        (configure_secondary_nics=None is used to test the default behaviour.)
        """
        m_read_initramfs_config.return_value = {"version": 1, "config": []}

        if configure_secondary_nics is not None:
            oracle_ds.ds_cfg[
                "configure_secondary_nics"
            ] = configure_secondary_nics

        def side_effect(self):
            self._network_config["secondary_added"] = mock.sentinel.needle

        oracle_ds._vnics_data = "DummyData"
        with mock.patch.object(
            oracle.DataSourceOracle,
            "_add_network_config_from_opc_imds",
            new=side_effect,
        ):
            was_secondary_added = "secondary_added" in oracle_ds.network_config
        assert expect_secondary_nics == was_secondary_added

    def test_secondary_nic_failure_isnt_blocking(
        self,
        m_read_initramfs_config,
        caplog,
        oracle_ds,
    ):
        oracle_ds.ds_cfg["configure_secondary_nics"] = True
        oracle_ds._vnics_data = "DummyData"

        with mock.patch.object(
            oracle.DataSourceOracle,
            "_add_network_config_from_opc_imds",
            side_effect=Exception(),
        ):
            network_config = oracle_ds.network_config
        assert network_config == m_read_initramfs_config.return_value
        assert "Failed to parse secondary network configuration" in caplog.text

    def test_ds_network_cfg_order(self, _m):
        """Ensure that DS net config is preferred over initramfs config
        but less than system config."""
        config_sources = oracle.DataSourceOracle.network_config_sources
        system_idx = config_sources.index(NetworkConfigSource.system_cfg)
        ds_idx = config_sources.index(NetworkConfigSource.ds)
        initramfs_idx = config_sources.index(NetworkConfigSource.initramfs)
        assert system_idx < ds_idx < initramfs_idx


# vi: ts=4 expandtab
