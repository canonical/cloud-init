# This file is part of cloud-init. See LICENSE file for license information.

import base64
import copy
import json
import logging
from itertools import count
from typing import Optional
from unittest import mock

import pytest
import responses

from cloudinit.sources import DataSourceOracle as oracle
from cloudinit.sources import NetworkConfigSource
from cloudinit.sources.DataSourceOracle import ReadOpcMetadataResponse
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
###############################################################################
OPC_VM_DUAL_STACK_SECONDARY_VNIC_RESPONSE = """\
[
  {
    "ipv6Addresses": [
      "2603:c020:400d:5dbb:e94a:a85d:26e3:e0d4"
    ],
    "ipv6SubnetCidrBlock": "2603:c020:400d:5dbb::/64",
    "ipv6VirtualRouterIp": "fe80::200:17ff:fe40:8972",
    "macAddr": "02:00:17:0D:6B:BE",
    "privateIp": "10.0.0.183",
    "subnetCidrBlock": "10.0.0.0/24",
    "virtualRouterIp": "10.0.0.1",
    "vlanTag": 929,
    "vnicId": "ocid1.vnic.oc1.iad.abuwcljtr2b6363afca55nzerlvwmfhxp_truncated"
  },
  {
    "ipv6Addresses": [
      "2603:c020:400d:5d7e:aacc:8e5f:3b1b:3a4a"
    ],
    "ipv6SubnetCidrBlock": "2603:c020:400d:5d7e::/64",
    "ipv6VirtualRouterIp": "fe80::200:17ff:fe40:8972",
    "macAddr": "02:00:17:18:F6:FF",
    "subnetCidrBlock": "\u003cnull\u003e",
    "vlanTag": 2659,
    "vnicId": "ocid1.vnic.oc1.iad.abuwcljtpfktyl2e3xm2ez4spj7wiliyc_truncated"
  }
]"""
OPC_VM_IPV6_ONLY_SECONDARY_VNIC_RESPONSE = """\
[
  {
    "ipv6Addresses": [
      "2603:c020:400d:5dbb:e94a:a85d:26e3:e0d4"
    ],
    "ipv6SubnetCidrBlock": "2603:c020:400d:5dbb::/64",
    "ipv6VirtualRouterIp": "fe80::200:17ff:fe40:8972",
    "macAddr": "02:00:17:0D:6B:BE",
    "vlanTag": 929,
    "vnicId": "ocid1.vnic.oc1.iad.abuwcljtr2b6363afca55nzerlvwmfhxp_truncated"
  },
  {
    "ipv6Addresses": [
      "2603:c020:400d:5d7e:aacc:8e5f:3b1b:3a4a"
    ],
    "ipv6SubnetCidrBlock": "2603:c020:400d:5d7e::/64",
    "ipv6VirtualRouterIp": "fe80::200:17ff:fe40:8972",
    "macAddr": "02:00:17:18:F6:FF",
    "vlanTag": 2659,
    "vnicId": "ocid1.vnic.oc1.iad.abuwcljtpfktyl2e3xm2ez4spj7wiliyc_truncated"
  }
]"""
###############################################################################

OPC_DUAL_STACK_VM_VNIC_RESPONSE = """\
[
  {
    "ipv6Addresses": [
      "2603:c020:400d:5dbb:e94a:a85d:26e3:e0d4"
    ],
    "ipv6SubnetCidrBlock": "2603:c020:400d:5dbb::/64",
    "ipv6VirtualRouterIp": "fe80::200:17ff:fe40:8972",
    "macAddr": "02:00:17:0D:6B:BE",
    "privateIp": "10.0.0.183",
    "subnetCidrBlock": "10.0.0.0/24",
    "virtualRouterIp": "10.0.0.1",
    "vlanTag": 929,
    "vnicId": "ocid1.vnic.oc1.iad.abuwcljtr2b6363afca55nzerlvwmfhxp_truncated"
  }
]"""

OPC_DUAL_STACK_WITHI_IPV6_ONLY_SECONDARY_VNIC_RESPONSE = """\
[
  {
    "ipv6Addresses": [
      "2603:c020:400d:5dbb:e94a:a85d:26e3:e0d4"
    ],
    "ipv6SubnetCidrBlock": "2603:c020:400d:5dbb::/64",
    "ipv6VirtualRouterIp": "fe80::200:17ff:fe40:8972",
    "macAddr": "02:00:17:0D:6B:BE",
    "privateIp": "10.0.0.183",
    "subnetCidrBlock": "10.0.0.0/24",
    "virtualRouterIp": "10.0.0.1",
    "vlanTag": 929,
    "vnicId": "ocid1.vnic.oc1.iad.abuwcljtr2b6363afca55nzerlvwmfhx4_truncated"
  },
  {
    "ipv6Addresses": [
      "2603:c020:400d:5d7e:aacc:8e5f:3b1b:3a4a"
    ],
    "ipv6SubnetCidrBlock": "2603:c020:400d:5d7e::/64",
    "ipv6VirtualRouterIp": "fe80::200:17ff:fe40:8972",
    "macAddr": "02:00:17:18:F6:FF",
    "subnetCidrBlock": "\u003cnull\u003e",
    "vlanTag": 2659,
    "vnicId": "ocid1.vnic.oc1.iad.abuwcljtpfktyl2e3xm2ez4spj7wiliy_truncated"
  }
]"""

OPC_IPV6_VM_VNIC_RESPONSE = """\
[
  {
    "ipv6Addresses": [
      "2603:c020:400d:5d7e:c2af:e153:ebe2:2478"
    ],
    "ipv6SubnetCidrBlock": "2603:c020:400d:5d7e::/64",
    "ipv6VirtualRouterIp": "fe80::200:17ff:fe40:8972",
    "macAddr": "02:00:17:15:92:4E",
    "vlanTag": 1970,
    "vnicId": "ocid1.vnic.oc1.iad.abuwcljtpfktyl2e3xm2ez4spj7wiliy_truncated"
  }
]"""

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

MAC_ADDR = "00:00:17:02:2b:b1"
IPV6_MAC_ADDR1 = "02:00:17:0d:6b:be"
IPV6_MAC_ADDR2 = "02:00:17:18:f6:ff"

DHCP = {
    "name": "eth0",
    "type": "physical",
    "subnets": [
        {
            "broadcast": "192.168.122.255",
            "control": "manual",
            "gateway": "192.168.122.1",
            "dns_search": ["foo.com"],
            "type": "dhcp",
            "netmask": "255.255.255.0",
            "dns_nameservers": ["192.168.122.1"],
        }
    ],
}
KLIBC_NET_CFG = {"version": 1, "config": [DHCP]}

ipv6_v1_instance_url = oracle.IPV6_METADATA_PATTERN.format(
    path="instance",
    version=1,
)
ipv4_v1_instance_url = oracle.IPV4_METADATA_PATTERN.format(
    path="instance",
    version=1,
)
ipv4_v2_instance_url = oracle.IPV4_METADATA_PATTERN.format(
    path="instance",
    version=2,
)
connectivity_urls_data = (
    {
        "url": oracle.IPV4_METADATA_PATTERN.format(version=2, path="instance"),
        "headers": oracle.V2_HEADERS,
    },
    {
        "url": oracle.IPV4_METADATA_PATTERN.format(version=1, path="instance"),
    },
    {
        "url": oracle.IPV6_METADATA_PATTERN.format(version=2, path="instance"),
        "headers": oracle.V2_HEADERS,
    },
    {
        "url": oracle.IPV6_METADATA_PATTERN.format(version=1, path="instance"),
    },
)


@pytest.fixture
def metadata_version():
    return 2


@pytest.fixture
def oracle_ds(request, fixture_utils, paths, metadata_version, mocker):
    """
    Return an instantiated DataSourceOracle.

    This also performs the mocking required:
        * ``_read_system_uuid`` returns something,
        * ``ds_detect`` returns True,
        * ``DataSourceOracle._is_iscsi_root`` returns True by default or what
          pytest.mark.is_iscsi gives as first param,
        * ``DataSourceOracle._get_iscsi_config`` returns a network cfg if
          is_iscsi else an empty network config,
        * ``read_opc_metadata`` returns ``OPC_V1_METADATA``,
        * ``ephemeral.EphemeralDHCPv4`` and ``net.find_fallback_nic`` mocked to
          avoid subp calls

    (This uses the paths fixture for the required helpers.Paths object, and the
    fixture_utils fixture for fetching markers.)
    """
    sys_cfg = fixture_utils.closest_marker_first_arg_or(
        request, "ds_sys_cfg", mock.MagicMock()
    )
    is_iscsi = fixture_utils.closest_marker_first_arg_or(
        request, "is_iscsi", True
    )

    metadata = ReadOpcMetadataResponse(
        metadata_version,
        json.loads(OPC_V2_METADATA),
        None,
        (
            ipv4_v2_instance_url
            if metadata_version == 2
            else ipv4_v1_instance_url
        ),
    )

    mocker.patch(DS_PATH + ".net.find_fallback_nic", return_value="fake_eth0")
    mocker.patch(DS_PATH + ".ephemeral.EphemeralDHCPv4")
    mocker.patch(DS_PATH + ".ephemeral.EphemeralIPNetwork")
    mocker.patch(DS_PATH + "._read_system_uuid", return_value="someuuid")
    mocker.patch(DS_PATH + ".DataSourceOracle.ds_detect", return_value=True)
    mocker.patch(DS_PATH + ".read_opc_metadata", return_value=metadata)
    mocker.patch(DS_PATH + ".KlibcOracleNetworkConfigSource")
    ds = oracle.DataSourceOracle(
        sys_cfg=sys_cfg,
        distro=mock.Mock(),
        paths=paths,
    )
    mocker.patch.object(ds, "_is_iscsi_root", return_value=is_iscsi)
    if is_iscsi:
        iscsi_config = copy.deepcopy(KLIBC_NET_CFG)
    else:
        iscsi_config = {"version": 1, "config": []}
    mocker.patch.object(ds, "_get_iscsi_config", return_value=iscsi_config)
    yield ds


class TestDataSourceOracle:

    def test_check_instance_id(self, oracle_ds):
        oracle_ds.system_uuid = "someuuid"
        with mock.patch(
            DS_PATH + ".sources.instance_id_matches_system_uuid"
        ) as m:
            oracle_ds.check_instance_id("sys_cfg")
        m.assert_called_once_with("someuuid")

    def test_get_public_ssh_keys(self, oracle_ds):
        oracle_ds.metadata = {"public_keys": "key"}
        assert ["key"] == oracle_ds.get_public_ssh_keys()

    def test_platform_info(self, oracle_ds):
        assert "oracle" == oracle_ds.cloud_name
        assert "oracle" == oracle_ds.platform_type

    def test_subplatform_before_fetch(self, oracle_ds):
        assert "unknown" == oracle_ds.subplatform

    @pytest.mark.parametrize("metadata_version", [1, 2])
    def test_platform_info_after_fetch(self, oracle_ds, metadata_version):
        oracle_ds._check_and_get_data()
        assert (
            f"metadata (http://169.254.169.254/opc/v{metadata_version}/)"
            == oracle_ds.subplatform
        )

    # @pytest.mark.parametrize("metadata_version", [1])
    # def test_v1_platform_info_after_fetch(self, oracle_ds):
    #     oracle_ds._check_and_get_data()
    #     assert (
    #         "metadata (http://169.254.169.254/opc/v1/)"
    #         == oracle_ds.subplatform
    #     )

    def test_secondary_nics_disabled_by_default(self, oracle_ds):
        assert not oracle_ds.ds_cfg["configure_secondary_nics"]

    @pytest.mark.ds_sys_cfg(
        {"datasource": {"Oracle": {"configure_secondary_nics": True}}}
    )
    def test_sys_cfg_can_enable_configure_secondary_nics(self, oracle_ds):
        assert oracle_ds.ds_cfg["configure_secondary_nics"]


class TestIsPlatformViable:
    @pytest.mark.parametrize(
        "dmi_data, platform_viable",
        [
            # System with known chassis tag is viable.
            (oracle.CHASSIS_ASSET_TAG, True),
            # System without known chassis tag is not viable.
            (None, False),
            # System with unknown chassis tag is not viable.
            ("LetsGoCubs", False),
        ],
    )
    def test_ds_detect(self, dmi_data, platform_viable):
        with mock.patch(
            DS_PATH + ".dmi.read_dmi_data", return_value=dmi_data
        ) as m_read_dmi_data:
            assert platform_viable == oracle.DataSourceOracle.ds_detect()
        m_read_dmi_data.assert_has_calls([mock.call("chassis-asset-tag")])


@pytest.mark.is_iscsi(False)
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
        oracle_ds._add_network_config_from_opc_imds(set_primary=False)

    def test_bare_metal_machine_skipped(self, oracle_ds, caplog):
        # nicIndex in the first entry indicates a bare metal machine
        oracle_ds._vnics_data = json.loads(OPC_BM_SECONDARY_VNIC_RESPONSE)
        # We test this by using a non-dict to ensure that no dict
        # operations are used
        oracle_ds._network_config = object()
        oracle_ds._add_network_config_from_opc_imds(set_primary=False)
        assert "bare metal machine" in caplog.text

    @pytest.mark.parametrize(
        "network_config, network_config_key",
        [
            pytest.param(
                {
                    "version": 1,
                    "config": [{"primary": "nic"}],
                },
                "config",
                id="v1",
            ),
            pytest.param(
                {
                    "version": 2,
                    "ethernets": {"primary": {"nic": {}}},
                },
                "ethernets",
                id="v2",
            ),
        ],
    )
    def test_missing_mac_skipped(
        self,
        oracle_ds,
        network_config,
        network_config_key,
        caplog,
    ):
        oracle_ds._vnics_data = json.loads(OPC_VM_SECONDARY_VNIC_RESPONSE)
        oracle_ds._network_config = network_config
        with mock.patch(DS_PATH + ".get_interfaces_by_mac", return_value={}):
            oracle_ds._add_network_config_from_opc_imds(set_primary=False)

        assert 1 == len(oracle_ds._network_config[network_config_key])
        assert (
            f"Interface with MAC {MAC_ADDR} not found; skipping" in caplog.text
        )
        assert 1 == caplog.text.count(" not found; skipping")

    @pytest.mark.parametrize(
        "set_primary",
        [True, False],
    )
    def test_imds_nic_setup_v1(self, set_primary, oracle_ds):
        oracle_ds._vnics_data = json.loads(OPC_VM_SECONDARY_VNIC_RESPONSE)
        oracle_ds._network_config = {
            "version": 1,
            "config": [{"primary": "nic"}],
        }
        with mock.patch(
            f"{DS_PATH}.get_interfaces_by_mac",
            return_value={
                "02:00:17:05:d1:db": "ens3",
                "00:00:17:02:2b:b1": "ens4",
            },
        ):
            oracle_ds._add_network_config_from_opc_imds(
                set_primary=set_primary
            )

        secondary_nic_index = 1
        nic_cfg = oracle_ds.network_config["config"]
        if set_primary:
            primary_cfg = nic_cfg[1]
            secondary_nic_index += 1

            assert "ens3" == primary_cfg["name"]
            assert "physical" == primary_cfg["type"]
            assert "02:00:17:05:d1:db" == primary_cfg["mac_address"]
            assert 9000 == primary_cfg["mtu"]
            assert 1 == len(primary_cfg["subnets"])
            assert "address" not in primary_cfg["subnets"][0]
            assert "dhcp" == primary_cfg["subnets"][0]["type"]
        secondary_cfg = nic_cfg[secondary_nic_index]
        assert "ens4" == secondary_cfg["name"]
        assert "physical" == secondary_cfg["type"]
        assert "00:00:17:02:2b:b1" == secondary_cfg["mac_address"]
        assert 9000 == secondary_cfg["mtu"]
        assert 1 == len(secondary_cfg["subnets"])
        assert "10.0.0.231/24" == secondary_cfg["subnets"][0]["address"]
        assert "static" == secondary_cfg["subnets"][0]["type"]

    @pytest.mark.parametrize(
        "set_primary",
        [True, False],
    )
    def test_secondary_nic_v2(self, set_primary, oracle_ds):
        oracle_ds._vnics_data = json.loads(OPC_VM_SECONDARY_VNIC_RESPONSE)
        oracle_ds._network_config = {
            "version": 2,
            "ethernets": {"primary": {"nic": {}}},
        }
        with mock.patch(
            f"{DS_PATH}.get_interfaces_by_mac",
            return_value={
                "02:00:17:05:d1:db": "ens3",
                "00:00:17:02:2b:b1": "ens4",
            },
        ):
            oracle_ds._add_network_config_from_opc_imds(
                set_primary=set_primary
            )

        nic_cfg = oracle_ds.network_config["ethernets"]
        if set_primary:
            assert "ens3" in nic_cfg
            primary_cfg = nic_cfg["ens3"]

            assert primary_cfg["dhcp4"] is True
            assert primary_cfg["dhcp6"] is False
            assert "02:00:17:05:d1:db" == primary_cfg["match"]["macaddress"]
            assert 9000 == primary_cfg["mtu"]
            assert "addresses" not in primary_cfg

        assert "ens4" in nic_cfg
        secondary_cfg = nic_cfg["ens4"]
        assert secondary_cfg["dhcp4"] is False
        assert secondary_cfg["dhcp6"] is False
        assert "00:00:17:02:2b:b1" == secondary_cfg["match"]["macaddress"]
        assert 9000 == secondary_cfg["mtu"]

        assert 1 == len(secondary_cfg["addresses"])
        assert "10.0.0.231/24" == secondary_cfg["addresses"][0]

    @pytest.mark.parametrize(
        "set_primary",
        [
            pytest.param(True, id="set_primary"),
            pytest.param(False, id="dont_set_primary"),
        ],
    )
    def test_imds_nic_setup_v1_ipv6_only(self, set_primary, oracle_ds):
        oracle_ds._vnics_data = json.loads(
            OPC_VM_IPV6_ONLY_SECONDARY_VNIC_RESPONSE
        )
        oracle_ds._network_config = {
            "version": 1,
            "config": [{"primary": "nic"}],
        }
        with mock.patch(
            f"{DS_PATH}.get_interfaces_by_mac",
            return_value={
                "02:00:17:0d:6b:be": "ens3",
                "02:00:17:18:f6:ff": "ens4",
            },
        ):
            oracle_ds._add_network_config_from_opc_imds(
                set_primary=set_primary
            )

        secondary_nic_index = 1
        nic_cfg = oracle_ds.network_config["config"]
        if set_primary:
            primary_cfg = nic_cfg[1]
            secondary_nic_index += 1

            assert "ens3" == primary_cfg["name"]
            assert "physical" == primary_cfg["type"]
            assert "02:00:17:0d:6b:be" == primary_cfg["mac_address"]
            assert 9000 == primary_cfg["mtu"]
            assert 1 == len(primary_cfg["subnets"])
            assert "address" not in primary_cfg["subnets"][0]
            assert "dhcp6" == primary_cfg["subnets"][0]["type"]
        secondary_cfg = nic_cfg[secondary_nic_index]
        assert "ens4" == secondary_cfg["name"]
        assert "physical" == secondary_cfg["type"]
        assert "02:00:17:18:f6:ff" == secondary_cfg["mac_address"]
        assert 9000 == secondary_cfg["mtu"]
        assert 1 == len(secondary_cfg["subnets"])
        assert (
            "2603:c020:400d:5d7e:aacc:8e5f:3b1b:3a4a/128"
            == secondary_cfg["subnets"][0]["address"]
        )
        assert "static" == secondary_cfg["subnets"][0]["type"]

    @pytest.mark.parametrize(
        "set_primary",
        [True, False],
    )
    def test_secondary_nic_v2_ipv6_only(self, set_primary, oracle_ds):
        oracle_ds._vnics_data = json.loads(
            OPC_VM_IPV6_ONLY_SECONDARY_VNIC_RESPONSE
        )
        oracle_ds._network_config = {
            "version": 2,
            "ethernets": {"primary": {"nic": {}}},
        }
        with mock.patch(
            f"{DS_PATH}.get_interfaces_by_mac",
            return_value={
                "02:00:17:0d:6b:be": "ens3",
                "02:00:17:18:f6:ff": "ens4",
            },
        ):
            oracle_ds._add_network_config_from_opc_imds(
                set_primary=set_primary
            )

        nic_cfg = oracle_ds.network_config["ethernets"]
        if set_primary:
            assert "ens3" in nic_cfg
            primary_cfg = nic_cfg["ens3"]

            assert primary_cfg["dhcp4"] is False
            assert primary_cfg["dhcp6"] is True
            assert "02:00:17:0d:6b:be" == primary_cfg["match"]["macaddress"]
            assert 9000 == primary_cfg["mtu"]
            assert "addresses" not in primary_cfg

        assert "ens4" in nic_cfg
        secondary_cfg = nic_cfg["ens4"]
        assert secondary_cfg["dhcp4"] is False
        assert secondary_cfg["dhcp6"] is False
        assert "02:00:17:18:f6:ff" == secondary_cfg["match"]["macaddress"]
        assert 9000 == secondary_cfg["mtu"]

        assert 1 == len(secondary_cfg["addresses"])
        assert (
            "2603:c020:400d:5d7e:aacc:8e5f:3b1b:3a4a/128"
            == secondary_cfg["addresses"][0]
        )

    @pytest.mark.parametrize("error_add_network", [None, Exception])
    @pytest.mark.parametrize(
        "configure_secondary_nics",
        [False, True],
    )
    @mock.patch(DS_PATH + "._ensure_netfailover_safe")
    def test_network_config_log_errors(
        self,
        m_ensure_netfailover_safe,
        configure_secondary_nics,
        error_add_network,
        oracle_ds,
        caplog,
        capsys,
    ):
        assert not oracle_ds._has_network_config()
        oracle_ds.ds_cfg["configure_secondary_nics"] = configure_secondary_nics
        with mock.patch.object(
            oracle.DataSourceOracle,
            "_add_network_config_from_opc_imds",
        ) as m_add_network_config_from_opc_imds:
            if error_add_network:
                m_add_network_config_from_opc_imds.side_effect = (
                    error_add_network
                )
            oracle_ds.network_config  # pylint: disable=pointless-statement  # noqa: E501
        assert [
            mock.call(True, False)
            == m_add_network_config_from_opc_imds.call_args_list
        ]
        assert 1 == oracle_ds._is_iscsi_root.call_count
        assert 1 == m_ensure_netfailover_safe.call_count

        assert ("", "") == capsys.readouterr()
        if not error_add_network:
            log_initramfs_index = -1
        else:
            log_initramfs_index = -3
            # Primary
            assert (
                logging.WARNING,
                "Failed to parse IMDS network configuration!",
            ) == caplog.record_tuples[-2][1:]
            # Secondary
            assert (
                logging.DEBUG,
                "Failed to parse IMDS network configuration!",
            ) == caplog.record_tuples[-1][1:]

        assert (
            logging.WARNING,
            "Could not obtain network configuration from initramfs."
            " Falling back to IMDS.",
        ) == caplog.record_tuples[log_initramfs_index][1:]


@mock.patch(DS_PATH + ".get_interfaces_by_mac")
@mock.patch(DS_PATH + ".is_netfail_master")
class TestNetworkConfigFiltersNetFailover:
    @pytest.mark.parametrize(
        "netcfg",
        [
            pytest.param({"something": "here"}, id="bogus"),
            pytest.param(
                {"something": "here", "version": 3}, id="unknown_version"
            ),
        ],
    )
    def test_ignore_network_config(
        self, m_netfail_master, m_get_interfaces_by_mac, netcfg
    ):
        passed_netcfg = copy.copy(netcfg)
        oracle._ensure_netfailover_safe(passed_netcfg)
        assert netcfg == passed_netcfg

    @pytest.mark.parametrize(
        "nic_name, netcfg, netfail_master_return, call_args_list",
        [
            pytest.param(
                "ens3",
                {
                    "version": 1,
                    "config": [
                        {
                            "type": "physical",
                            "name": "ens3",
                            "mac_address": MAC_ADDR,
                            "subnets": [{"type": "dhcp4"}],
                        }
                    ],
                },
                False,
                [mock.call("ens3")],
                id="checks_v1_type_physical_interfaces",
            ),
            pytest.param(
                "bond0",
                {
                    "version": 1,
                    "config": [
                        {
                            "type": "bond",
                            "name": "bond0",
                            "mac_address": MAC_ADDR,
                            "subnets": [{"type": "dhcp4"}],
                        }
                    ],
                },
                None,
                [],
                id="skips_v1_non_phys_interfaces",
            ),
            pytest.param(
                "ens3",
                {
                    "version": 2,
                    "ethernets": {
                        "ens3": {
                            "dhcp4": True,
                            "critical": True,
                            "set-name": "ens3",
                            "match": {"macaddress": MAC_ADDR},
                        }
                    },
                },
                False,
                [mock.call("ens3")],
                id="checks_v2_type_ethernet_interfaces",
            ),
            pytest.param(
                "wlps0",
                {
                    "version": 2,
                    "ethernets": {
                        "wlps0": {
                            "dhcp4": True,
                            "critical": True,
                            "set-name": "wlps0",
                            "match": {"macaddress": MAC_ADDR},
                        }
                    },
                },
                None,
                [mock.call("wlps0")],
                id="skips_v2_non_ethernet_interfaces",
            ),
        ],
    )
    def test__ensure_netfailover_safe(
        self,
        m_netfail_master,
        m_get_interfaces_by_mac,
        nic_name,
        netcfg,
        netfail_master_return,
        call_args_list,
    ):
        m_get_interfaces_by_mac.return_value = {
            MAC_ADDR: nic_name,
        }
        passed_netcfg = copy.copy(netcfg)
        if netfail_master_return is not None:
            m_netfail_master.return_value = netfail_master_return
        oracle._ensure_netfailover_safe(passed_netcfg)
        assert netcfg == passed_netcfg
        assert call_args_list == m_netfail_master.call_args_list

    def test_removes_master_mac_property_v1(
        self, m_netfail_master, m_get_interfaces_by_mac
    ):
        nic_master, mac_master = "ens3", test_helpers.random_string()
        nic_other, mac_other = "ens7", test_helpers.random_string()
        nic_extra, mac_extra = "enp0s1f2", test_helpers.random_string()
        m_get_interfaces_by_mac.return_value = {
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

        m_netfail_master.side_effect = _is_netfail_master
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
        assert expected_cfg == netcfg

    def test_removes_master_mac_property_v2(
        self, m_netfail_master, m_get_interfaces_by_mac
    ):
        nic_master, mac_master = "ens3", test_helpers.random_string()
        nic_other, mac_other = "ens7", test_helpers.random_string()
        nic_extra, mac_extra = "enp0s1f2", test_helpers.random_string()
        m_get_interfaces_by_mac.return_value = {
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

        m_netfail_master.side_effect = _is_netfail_master

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
        assert expected_cfg == netcfg


def _mock_v2_urls(mocked_responses):
    def instance_callback(response):
        print(response.url)
        assert response.headers.get("Authorization") == "Bearer Oracle"
        return [200, response.headers, OPC_V2_METADATA]

    def vnics_callback(response):
        assert response.headers.get("Authorization") == "Bearer Oracle"
        return [200, response.headers, OPC_BM_SECONDARY_VNIC_RESPONSE]

    mocked_responses.add_callback(
        responses.GET,
        "http://169.254.169.254/opc/v2/instance/",
        callback=instance_callback,
    )
    mocked_responses.add_callback(
        responses.GET,
        "http://169.254.169.254/opc/v2/vnics/",
        callback=vnics_callback,
    )


def _mock_no_v2_urls(mocked_responses):
    mocked_responses.add(
        responses.GET,
        "http://169.254.169.254/opc/v2/instance/",
        status=404,
    )
    mocked_responses.add(
        responses.GET,
        "http://169.254.169.254/opc/v1/instance/",
        body=OPC_V1_METADATA,
    )
    mocked_responses.add(
        responses.GET,
        "http://169.254.169.254/opc/v1/vnics/",
        body=OPC_BM_SECONDARY_VNIC_RESPONSE,
    )


class TestReadOpcMetadata:
    # See https://docs.pytest.org/en/stable/example
    # /parametrize.html#parametrizing-conditional-raising

    @mock.patch("cloudinit.url_helper.time.sleep", lambda _: None)
    @pytest.mark.parametrize(
        "version,setup_urls,instance_data,fetch_vnics,vnics_data",
        [
            pytest.param(
                2,
                _mock_v2_urls,
                json.loads(OPC_V2_METADATA),
                True,
                json.loads(OPC_BM_SECONDARY_VNIC_RESPONSE),
                id="v2_with_vnic_data",
            ),
            pytest.param(
                2,
                _mock_v2_urls,
                json.loads(OPC_V2_METADATA),
                False,
                None,
                id="v2_no_vnic_data",
            ),
            pytest.param(
                1,
                _mock_no_v2_urls,
                json.loads(OPC_V1_METADATA),
                True,
                json.loads(OPC_BM_SECONDARY_VNIC_RESPONSE),
                id="v1_with_vnic_data",
            ),
            pytest.param(
                1,
                _mock_no_v2_urls,
                json.loads(OPC_V1_METADATA),
                False,
                None,
                id="v1_no_vnic_data",
            ),
        ],
    )
    def test_metadata_returned(
        self,
        version,
        setup_urls,
        instance_data,
        fetch_vnics,
        vnics_data,
        mocked_responses,
    ):
        """
        Test the read_opc_metadata function in all happy path scenarios.
        """
        setup_urls(mocked_responses)
        metadata = oracle.read_opc_metadata(fetch_vnics_data=fetch_vnics)
        print(metadata)
        assert version == metadata.version
        assert instance_data == metadata.instance_data
        assert vnics_data == metadata.vnics_data
        if version == 2:
            assert ipv4_v2_instance_url == metadata.imds_url_used
        else:
            assert ipv4_v1_instance_url == metadata.imds_url_used

    @mock.patch("cloudinit.url_helper.time.sleep", lambda _: None)
    @mock.patch("cloudinit.url_helper.time.monotonic", side_effect=count(0, 1))
    @mock.patch("cloudinit.url_helper.readurl", side_effect=UrlError)
    def test_retry(self, m_readurl, m_time):
        # Since wait_for_url has its own retry tests, just verify that we
        # attempted to contact both endpoints multiple times
        oracle.read_opc_metadata()
        assert len(m_readurl.call_args_list) > 3
        assert (
            m_readurl.call_args_list[0][0][0]
            == "http://169.254.169.254/opc/v2/instance/"
        )
        assert (
            m_readurl.call_args_list[1][0][0]
            == "http://169.254.169.254/opc/v1/instance/"
        )
        assert (
            m_readurl.call_args_list[2][0][0]
            == "http://169.254.169.254/opc/v2/instance/"
        )
        assert (
            m_readurl.call_args_list[3][0][0]
            == "http://169.254.169.254/opc/v1/instance/"
        )

    @mock.patch("cloudinit.url_helper.time.sleep", lambda _: None)
    @mock.patch("cloudinit.url_helper.time.monotonic", side_effect=[0, 11])
    @mock.patch(
        "cloudinit.sources.DataSourceOracle.wait_for_url",
        return_value=("http://hi", b'{"some": "value"}'),
    )
    def test_fetch_vnics_max_wait(self, m_wait_for_url, m_time):
        oracle.read_opc_metadata(fetch_vnics_data=True)
        assert m_wait_for_url.call_count == 2
        # 19 because start time was 0, next time was 11 and max wait is 30
        assert m_wait_for_url.call_args_list[-1][1]["max_wait"] == 19

    @mock.patch("cloudinit.url_helper.time.sleep", lambda _: None)
    @mock.patch("cloudinit.url_helper.time.monotonic", side_effect=[0, 1000])
    @mock.patch(
        "cloudinit.sources.DataSourceOracle.wait_for_url",
        return_value=("http://hi", b'{"some": "value"}'),
    )
    def test_attempt_vnics_after_max_wait_expire(self, m_wait_for_url, m_time):
        oracle.read_opc_metadata(fetch_vnics_data=True)
        assert m_wait_for_url.call_count == 2
        assert m_wait_for_url.call_args_list[-1][1]["max_wait"] < 0

    # No need to actually wait between retries in the tests
    @mock.patch("cloudinit.url_helper.time.sleep", lambda _: None)
    @pytest.mark.parametrize(
        [
            "instance_md_succeeds",
            "vnics_md_succeeds",
        ],
        [
            pytest.param(
                True,
                True,
                id="fetching both instance and vnics metadata succeeds",
            ),
            pytest.param(
                False,
                None,
                id="fetching instance metadata fails, vnics not fetched",
            ),
            pytest.param(
                True,
                False,
                id="fetching instance metadata succeeds, vnics metadata fails",
            ),
        ],
    )
    def test_fetchin_instance_and_vnic_successes_and_failures(
        self,
        caplog,
        instance_md_succeeds: bool,
        vnics_md_succeeds: Optional[bool],
    ):
        instance_md_requsted = False
        vnics_md_requsted = False

        def m_wait(*args, **kwargs):
            nonlocal instance_md_requsted, vnics_md_requsted
            if "urls" in kwargs:
                url_arg = kwargs["urls"]
            else:
                url_arg = args[0]
            print(url_arg)
            for url in url_arg:
                if "vnics" in url:
                    vnics_md_requsted = True
                    if vnics_md_succeeds:
                        return url, b"{}"
                    return False, None
                if "instance" in url:
                    instance_md_requsted = True
                    if instance_md_succeeds:
                        return url, b"{}"
                    return False, None
            return ("http://localhost", b"{}")

        with mock.patch(DS_PATH + ".wait_for_url", side_effect=m_wait):
            opc_metadata = oracle.read_opc_metadata(fetch_vnics_data=True)
            if instance_md_succeeds:
                assert opc_metadata
                assert opc_metadata.imds_url_used == ipv4_v2_instance_url
            else:
                assert not opc_metadata
            assert instance_md_requsted
            assert vnics_md_requsted == instance_md_succeeds

        if instance_md_succeeds:
            assert (
                "Successfully fetched instance metadata from IMDS at:"
                in caplog.text
            )
            if vnics_md_succeeds:
                assert (
                    "Successfully fetched vnics metadata from IMDS at:"
                    in caplog.text
                )
            else:
                assert (
                    "Failed to fetch IMDS network configuration!"
                    in caplog.text
                )
        else:
            log_level = caplog.record_tuples[-1][1]
            assert logging.WARNING == log_level
            log_message = caplog.record_tuples[-1][2]
            assert "Failed to fetch IMDS metadata from any of:" in log_message


@pytest.mark.parametrize(
    "",
    [
        pytest.param(marks=pytest.mark.is_iscsi(True), id="iscsi"),
        pytest.param(marks=pytest.mark.is_iscsi(False), id="non-iscsi"),
    ],
)
class TestCommon_GetDataBehaviour:
    """This test class tests behaviour common to iSCSI and non-iSCSI root.

    It defines a fixture, parameterized_oracle_ds, which is used in all the
    tests herein to test that the commonly expected behaviour is the same with
    iSCSI root and without.

    (As non-iSCSI root behaviour is a superset of iSCSI root behaviour this
    class is implicitly also testing all iSCSI root behaviour so there is no
    separate class for that case.)
    """

    @mock.patch(
        DS_PATH + ".DataSourceOracle.ds_detect", mock.Mock(return_value=False)
    )
    def test_false_if_platform_not_viable(
        self,
        oracle_ds,
    ):
        assert not oracle_ds._check_and_get_data()

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
        oracle_ds,
    ):
        assert oracle_ds._check_and_get_data()
        assert expected_value == oracle_ds.metadata[keyname]

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
        oracle_ds,
    ):
        assert oracle_ds._check_and_get_data()
        assert expected_value == getattr(oracle_ds, attribute_name)

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
        self, ssh_keys, expected_value, oracle_ds
    ):
        instance_data = json.loads(OPC_V1_METADATA)
        if ssh_keys is None:
            del instance_data["metadata"]["ssh_authorized_keys"]
        else:
            instance_data["metadata"]["ssh_authorized_keys"] = ssh_keys
        metadata = ReadOpcMetadataResponse(
            None,
            instance_data,
            None,
            ipv4_v1_instance_url,
        )
        with mock.patch(
            DS_PATH + ".read_opc_metadata",
            mock.Mock(return_value=metadata),
        ):
            assert oracle_ds._check_and_get_data()
            assert expected_value == oracle_ds.get_public_ssh_keys()

    @pytest.mark.parametrize(
        "use_ipv6",
        [
            pytest.param(True, id="ipv6"),
            pytest.param(False, id="ipv4"),
        ],
    )
    def test_missing_user_data_handled_gracefully(self, oracle_ds, use_ipv6):
        instance_data = json.loads(OPC_V1_METADATA)
        del instance_data["metadata"]["user_data"]
        md_url_pattern = (
            ipv6_v1_instance_url if use_ipv6 else ipv4_v1_instance_url
        )
        metadata = ReadOpcMetadataResponse(
            None,
            instance_data,
            None,
            md_url_pattern,
        )

        with mock.patch(
            DS_PATH + ".read_opc_metadata",
            mock.Mock(return_value=metadata),
        ):
            assert oracle_ds._check_and_get_data()

        assert oracle_ds.userdata_raw is None

    @pytest.mark.parametrize(
        "use_ipv6",
        [
            pytest.param(True, id="ipv6"),
            pytest.param(False, id="ipv4"),
        ],
    )
    def test_missing_metadata_handled_gracefully(self, oracle_ds, use_ipv6):
        instance_data = json.loads(OPC_V1_METADATA)
        del instance_data["metadata"]
        md_url_pattern = (
            ipv6_v1_instance_url if use_ipv6 else ipv4_v1_instance_url
        )
        metadata = ReadOpcMetadataResponse(
            None,
            instance_data,
            None,
            md_url_pattern,
        )
        with mock.patch(
            DS_PATH + ".read_opc_metadata",
            mock.Mock(return_value=metadata),
        ):
            assert oracle_ds._check_and_get_data()

        assert oracle_ds.userdata_raw is None
        assert [] == oracle_ds.get_public_ssh_keys()


@pytest.mark.is_iscsi(False)
class TestNonIscsiRoot_GetDataBehaviour:
    @mock.patch(DS_PATH + ".ephemeral.EphemeralIPNetwork")
    @mock.patch(DS_PATH + ".net.find_fallback_nic", return_value="fake_eth0")
    def test_read_opc_metadata_called_with_ephemeral_dhcp(
        self, m_find_fallback_nic, m_ephemeral_network, oracle_ds
    ):

        in_context_manager = False

        def enter_context_manager():
            nonlocal in_context_manager
            in_context_manager = True

        def exit_context_manager(*args):
            nonlocal in_context_manager
            in_context_manager = False

        m_ephemeral_network.return_value.__enter__.side_effect = (
            enter_context_manager
        )
        m_ephemeral_network.return_value.__exit__.side_effect = (
            exit_context_manager
        )

        def assert_in_context_manager(**kwargs):
            assert in_context_manager
            m_fetched_metadata = mock.MagicMock()
            m_fetched_metadata.imds_url_used = ipv4_v1_instance_url
            return m_fetched_metadata

        with mock.patch(
            DS_PATH + ".read_opc_metadata",
            mock.Mock(
                side_effect=assert_in_context_manager,
            ),
        ):
            assert oracle_ds._check_and_get_data()

        assert [
            mock.call(
                distro=oracle_ds.distro,
                interface=m_find_fallback_nic.return_value,
                ipv6=True,
                ipv4=True,
                connectivity_urls_data=connectivity_urls_data,
            )
        ] == m_ephemeral_network.call_args_list


class TestPerformDHCPSetup:
    @pytest.mark.parametrize(
        [
            "perform_dhcp_setup",
            "ephemeral_dhcp_setup_raises_exception",
        ],
        [
            pytest.param(
                False,
                None,
                id="dont_perform_dhcp_setup",
            ),
            pytest.param(
                True,
                False,
                id="successfully_perform_dhcp_setup",
            ),
            pytest.param(
                True,
                True,
                id="fail_to_perform_dhcp_setup",
            ),
        ],
    )
    @mock.patch(DS_PATH + ".ephemeral.EphemeralIPNetwork")
    @mock.patch(DS_PATH + ".net.find_fallback_nic", return_value="fake_eth0")
    def test_read_opc_metadata_called_with_ephemeral_dhcp(
        self,
        m_find_fallback_nic,
        m_ephemeral_network,
        perform_dhcp_setup,
        ephemeral_dhcp_setup_raises_exception,
        oracle_ds,
    ):
        # actually modify the oracle_ds to use `perform_dhcp_setup` value
        oracle_ds.perform_dhcp_setup = perform_dhcp_setup

        assert oracle_ds.perform_dhcp_setup == perform_dhcp_setup

        in_context_manager = False
        ephemeral_dhcp_context_entered = False

        def enter_context_manager():
            nonlocal in_context_manager, ephemeral_dhcp_context_entered
            ephemeral_dhcp_context_entered = True
            in_context_manager = True

        def exit_context_manager(*args):
            nonlocal in_context_manager, ephemeral_dhcp_context_entered
            in_context_manager = False

        # have ephemeral network riase exception when parameterized to do so
        if ephemeral_dhcp_setup_raises_exception:

            def raise_exception(**kwargs):
                raise Exception("Failed to setup ephemeral network")

            m_ephemeral_network.side_effect = raise_exception
        else:
            m_ephemeral_network.return_value.__enter__.side_effect = (
                enter_context_manager
            )
            m_ephemeral_network.return_value.__exit__.side_effect = (
                exit_context_manager
            )

        def assert_in_context_manager(**kwargs):
            if (
                perform_dhcp_setup
                and not ephemeral_dhcp_setup_raises_exception
            ):
                assert in_context_manager
            else:
                assert not in_context_manager

            m_fetched_metadata = mock.MagicMock()
            m_fetched_metadata.imds_url_used = ipv4_v1_instance_url
            return m_fetched_metadata

        with mock.patch(
            DS_PATH + ".read_opc_metadata",
            mock.Mock(
                side_effect=assert_in_context_manager,
            ),
        ):
            # datasource fails/exits if ephemeral dhcp setup fails
            with (
                pytest.raises(Exception)
                if ephemeral_dhcp_setup_raises_exception
                else test_helpers.does_not_raise()
            ):
                assert oracle_ds._check_and_get_data()

        if perform_dhcp_setup:
            assert [
                mock.call(
                    distro=oracle_ds.distro,
                    interface=m_find_fallback_nic.return_value,
                    ipv6=True,
                    ipv4=True,
                    connectivity_urls_data=connectivity_urls_data,
                )
            ] == m_ephemeral_network.call_args_list
        else:
            # otherwise, assert that we dont try to bring up networking
            assert m_ephemeral_network.call_count == 0

        # ephemeral dhcp context should only be entered if we are expecting
        # to perform ephemeral network setup AND doing so does not fail
        if perform_dhcp_setup and not ephemeral_dhcp_setup_raises_exception:
            assert ephemeral_dhcp_context_entered
        else:
            assert not ephemeral_dhcp_context_entered


@mock.patch(DS_PATH + ".get_interfaces_by_mac", return_value={})
class TestNetworkConfig:
    def test_network_config_cached(self, m_get_interfaces_by_mac, oracle_ds):
        """.network_config should be cached"""
        assert 0 == oracle_ds._get_iscsi_config.call_count
        oracle_ds.network_config  # pylint: disable=pointless-statement
        assert 1 == oracle_ds._get_iscsi_config.call_count
        oracle_ds.network_config  # pylint: disable=pointless-statement
        assert 1 == oracle_ds._get_iscsi_config.call_count

    @pytest.mark.parametrize(
        "configure_secondary_nics,is_iscsi,expected_set_primary",
        [
            pytest.param(
                True,
                True,
                [mock.call(False)],
                marks=pytest.mark.is_iscsi(True),
            ),
            pytest.param(
                True,
                False,
                [mock.call(True)],
                marks=pytest.mark.is_iscsi(False),
            ),
            pytest.param(False, True, [], marks=pytest.mark.is_iscsi(True)),
            pytest.param(
                False,
                False,
                [mock.call(True)],
                marks=pytest.mark.is_iscsi(False),
            ),
            pytest.param(None, True, [], marks=pytest.mark.is_iscsi(True)),
            pytest.param(
                None,
                False,
                [mock.call(True)],
                marks=pytest.mark.is_iscsi(False),
            ),
        ],
    )
    def test_secondary_nic_addition(
        self,
        m_get_interfaces_by_mac,
        configure_secondary_nics,
        is_iscsi,
        expected_set_primary,
        oracle_ds,
    ):
        """Test that _add_network_config_from_opc_imds is called as expected

        (configure_secondary_nics=None is used to test the default behaviour.)
        """

        if configure_secondary_nics is not None:
            oracle_ds.ds_cfg["configure_secondary_nics"] = (
                configure_secondary_nics
            )

        oracle_ds._vnics_data = "DummyData"
        with mock.patch.object(
            oracle_ds,
            "_add_network_config_from_opc_imds",
        ) as m_add_network_config_from_opc_imds:
            oracle_ds.network_config  # pylint: disable=pointless-statement
        assert (
            expected_set_primary
            == m_add_network_config_from_opc_imds.call_args_list
        )

    def test_secondary_nic_failure_isnt_blocking(
        self,
        m_get_interfaces_by_mac,
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
        assert network_config == oracle_ds._get_iscsi_config.return_value
        assert 2 == caplog.text.count(
            "Failed to parse IMDS network configuration"
        )

    def test_ds_network_cfg_preferred_over_initramfs(
        self, m_get_interfaces_by_mac
    ):
        """Ensure that DS net config is preferred over initramfs config"""
        config_sources = oracle.DataSourceOracle.network_config_sources
        ds_idx = config_sources.index(NetworkConfigSource.DS)
        initramfs_idx = config_sources.index(NetworkConfigSource.INITRAMFS)
        assert ds_idx < initramfs_idx

    def test_system_network_cfg_preferred_over_ds(
        self, m_get_interfaces_by_mac
    ):
        """Ensure that system net config is preferred over DS config"""
        config_sources = oracle.DataSourceOracle.network_config_sources
        ds_idx = config_sources.index(NetworkConfigSource.DS)
        system_idx = config_sources.index(NetworkConfigSource.SYSTEM_CFG)
        assert system_idx < ds_idx

    @pytest.mark.parametrize("set_primary", [True, False])
    def test__add_network_config_from_opc_imds_no_vnics_data(
        self,
        m_get_interfaces_by_mac,
        set_primary,
        oracle_ds,
        caplog,
    ):
        assert not oracle_ds._has_network_config()
        with mock.patch.object(oracle_ds, "_vnics_data", None):
            oracle_ds._add_network_config_from_opc_imds(set_primary)
        assert not oracle_ds._has_network_config()
        assert (
            logging.WARNING,
            "NIC data is UNSET but should not be",
        ) == caplog.record_tuples[-1][1:]

    def test_missing_mac_skipped(
        self,
        m_get_interfaces_by_mac,
        oracle_ds,
        caplog,
    ):
        """If no intefaces by mac found, then _network_config not setted and
        correct logs.
        """
        vnics_data = json.loads(OPC_VM_SECONDARY_VNIC_RESPONSE)
        assert not oracle_ds._has_network_config()
        with mock.patch.object(oracle_ds, "_vnics_data", vnics_data):
            oracle_ds._add_network_config_from_opc_imds(set_primary=True)
        assert not oracle_ds._has_network_config()
        assert (
            logging.WARNING,
            "Interface with MAC 02:00:17:05:d1:db not found; skipping",
        ) == caplog.record_tuples[-2][1:]
        assert (
            logging.WARNING,
            f"Interface with MAC {MAC_ADDR} not found; skipping",
        ) == caplog.record_tuples[-1][1:]

    # @pytest.mark.parametrize("set_primary", [True, False])
    # @pytest.mark.parametrize("use_ipv6", [True, False])
    @pytest.mark.parametrize(
        [
            "set_primary",
            "use_ipv6",
            "secondary_mac_present",
        ],
        [
            # pytest.param(True, True, id="ipv6 vnics setting primary"),
            # pytest.param(False, True, id="ipv6 vnics not setting primary"),
            # pytest.param(True, False, id="ipv4 vnics setting primary"),
            # pytest.param(False, False, id="ipv4 vnics not setting primary"),
            pytest.param(
                True,
                True,
                True,
                id="ipv6 vnics setting primary with secondary mac present",
            ),
            pytest.param(
                False,
                True,
                True,
                id="ipv6 vnics not setting primary with secondary mac present",
            ),
            pytest.param(
                False,
                True,
                False,
                id="ipv6 vnics not setting primary w/o secondary mac present",
            ),
        ],
    )
    def test_nics(
        self,
        m_get_interfaces_by_mac,
        set_primary,
        use_ipv6,
        secondary_mac_present,
        oracle_ds,
        caplog,
        mocker,
    ):
        """Correct number of configs added"""
        if use_ipv6:
            vnics_data = json.loads(OPC_VM_DUAL_STACK_SECONDARY_VNIC_RESPONSE)
        else:
            vnics_data = json.loads(OPC_VM_SECONDARY_VNIC_RESPONSE)
        if set_primary:
            assert not oracle_ds._has_network_config()
        else:
            # Simulate primary config was taken from iscsi
            oracle_ds._network_config = copy.deepcopy(KLIBC_NET_CFG)
        if use_ipv6:
            interfaces = {IPV6_MAC_ADDR1: "eth_0"}
            if secondary_mac_present:
                interfaces[IPV6_MAC_ADDR2] = "eth_1"
            mocker.patch(
                DS_PATH + ".get_interfaces_by_mac",
                return_value=interfaces,
            )
        else:
            mocker.patch(
                DS_PATH + ".get_interfaces_by_mac",
                return_value={
                    "02:00:17:05:d1:db": "eth_0",
                    MAC_ADDR: "name_1",
                },
            )
        mocker.patch.object(oracle_ds, "_vnics_data", vnics_data)
        mocker.patch.object(
            oracle_ds,
            "metadata_address",
            ipv6_v1_instance_url if use_ipv6 else ipv4_v1_instance_url,
        )

        # assert that oracle_ds.metadata_address is set correctly
        assert oracle_ds.metadata_address == (
            ipv6_v1_instance_url if use_ipv6 else ipv4_v1_instance_url
        )

        oracle_ds._add_network_config_from_opc_imds(set_primary)
        num_configs_expected = 1 + int(secondary_mac_present)
        assert num_configs_expected == len(
            oracle_ds._network_config["config"]
        ), "Config not added"

        # assert that secondary vnic config is skipped if its mac is not found
        assert int(not secondary_mac_present) == caplog.text.count(
            " not found; skipping"
        )


class TestHelpers:
    @pytest.mark.parametrize(
        [
            "url",
            "expected_base_url",
            "raises_exception",
        ],
        [
            pytest.param(
                None,
                None,
                None,
                id="None",
            ),
            pytest.param(
                "",
                "",
                None,
                id="empty",
            ),
            pytest.param(
                "http://url.tld/v2/instance/",
                "http://url.tld/v2/",
                None,
                id="v2",
            ),
            pytest.param(
                "http://url.tld/v1/instance/",
                "http://url.tld/v1/",
                None,
                id="v1",
            ),
            pytest.param(
                "http://url.tld/v3/instance/",
                None,
                ValueError,
                id="v3_error",
            ),
            pytest.param(
                "http://localhost:12345/v1/instance/vnics/a/b/c",
                "http://localhost:12345/v1/",
                None,
                id="v1_many_parts_with_host_and_ports",
            ),
        ],
    )
    def test_get_versioned_metadata_base_url(
        self,
        url,
        expected_base_url,
        raises_exception,
    ):
        """
        Test that the correct base URL is returned from the given URL, or that
        the expected exception is raised if the URL is not valid.
        """
        if raises_exception:
            with pytest.raises(raises_exception):
                oracle._get_versioned_metadata_base_url(url)
        else:
            assert (
                expected_base_url
                == oracle._get_versioned_metadata_base_url(url)
            )
