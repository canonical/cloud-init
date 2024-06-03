# This file is part of cloud-init. See LICENSE file for license information.
# pylint: disable=attribute-defined-outside-init

import copy
import datetime
import json
import os
import stat
import xml.etree.ElementTree as ET
from pathlib import Path

import passlib.hash
import pytest
import requests

from cloudinit import distros, dmi, helpers, subp, url_helper
from cloudinit.atomic_helper import b64e, json_dumps
from cloudinit.net import dhcp, ephemeral
from cloudinit.sources import UNSET
from cloudinit.sources import DataSourceAzure as dsaz
from cloudinit.sources.azure import errors, identity, imds
from cloudinit.sources.helpers import netlink
from cloudinit.util import (
    MountFailedError,
    load_json,
    load_text_file,
    write_file,
)
from tests.unittests.helpers import (
    CiTestCase,
    ExitStack,
    example_netdev,
    mock,
    populate_dir,
    resourceLocation,
)

MOCKPATH = "cloudinit.sources.DataSourceAzure."


@pytest.fixture
def azure_ds(patched_data_dir_path, mock_dmi_read_dmi_data, paths):
    """Provide DataSourceAzure instance with mocks for minimal test case."""
    yield dsaz.DataSourceAzure(sys_cfg={}, distro=mock.Mock(), paths=paths)


@pytest.fixture
def mock_wrapping_setup_ephemeral_networking(azure_ds):
    with mock.patch.object(
        azure_ds,
        "_setup_ephemeral_networking",
        wraps=azure_ds._setup_ephemeral_networking,
    ) as m:
        yield m


@pytest.fixture
def mock_azure_helper_readurl():
    with mock.patch(
        "cloudinit.sources.helpers.azure.url_helper.readurl", autospec=True
    ) as m:
        yield m


@pytest.fixture
def mock_azure_get_metadata_from_fabric():
    with mock.patch(
        MOCKPATH + "get_metadata_from_fabric",
        autospec=True,
    ) as m:
        yield m


@pytest.fixture
def mock_azure_report_failure_to_fabric():
    with mock.patch(
        MOCKPATH + "report_failure_to_fabric",
        autospec=True,
    ) as m:
        yield m


@pytest.fixture
def mock_chassis_asset_tag():
    with mock.patch.object(
        identity.ChassisAssetTag,
        "query_system",
        return_value=identity.ChassisAssetTag.AZURE_CLOUD.value,
    ) as m:
        yield m


@pytest.fixture(autouse=True)
def mock_device_driver():
    with mock.patch(
        MOCKPATH + "device_driver",
        return_value="fake_driver",
    ) as m:
        yield m


@pytest.fixture(autouse=True)
def mock_netinfo(disable_netdev_info):
    pass


@pytest.fixture
def mock_generate_fallback_config():
    with mock.patch(
        MOCKPATH + "net.generate_fallback_config",
        autospec=True,
    ) as m:
        yield m


@pytest.fixture
def mock_time():
    with mock.patch(
        MOCKPATH + "time",
        autospec=True,
    ) as m:
        yield m


@pytest.fixture
def mock_monotonic():
    with mock.patch(
        MOCKPATH + "monotonic",
        autospec=True,
    ) as m:
        yield m


@pytest.fixture
def mock_dmi_read_dmi_data():
    def fake_read(key: str) -> str:
        if key == "system-uuid":
            return "50109936-ef07-47fe-ac82-890c853f60d5"
        elif key == "chassis-asset-tag":
            return "7783-7084-3265-9085-8269-3286-77"
        raise RuntimeError()

    with mock.patch.object(
        dmi,
        "read_dmi_data",
        side_effect=fake_read,
        autospec=True,
    ) as m:
        yield m


@pytest.fixture
def mock_ephemeral_dhcp_v4(mock_ephemeral_ipv4_network):
    with mock.patch(
        MOCKPATH + "EphemeralDHCPv4",
    ) as m:
        m.return_value._ephipv4 = mock_ephemeral_ipv4_network.return_value
        yield m


@pytest.fixture
def mock_ephemeral_ipv4_network():
    with mock.patch(
        "cloudinit.net.ephemeral.EphemeralIPv4Network",
        autospec=True,
    ) as m:
        m.return_value.distro = "ubuntu"
        m.return_value.interface = "eth0"
        m.return_value.ip = "10.0.0.4"
        m.return_value.prefix_or_mask = "32"
        m.return_value.broadcast = "255.255.255.255"
        m.return_value.router = "10.0.0.1"
        m.return_value.static_routes = [
            ("0.0.0.0/0", "10.0.0.1"),
            ("168.63.129.16/32", "10.0.0.1"),
            ("169.254.169.254/32", "10.0.0.1"),
        ]
        yield m


@pytest.fixture
def mock_imds_fetch_metadata_with_api_fallback():
    with mock.patch.object(
        imds,
        "fetch_metadata_with_api_fallback",
        autospec=True,
    ) as m:
        yield m


@pytest.fixture(autouse=True)
def mock_report_dmesg_to_kvp():
    with mock.patch(
        MOCKPATH + "report_dmesg_to_kvp",
        return_value=True,
        autospec=True,
    ) as m:
        yield m


@pytest.fixture
def mock_kvp_report_failure_to_host():
    with mock.patch(
        MOCKPATH + "kvp.report_failure_to_host",
        return_value=True,
        autospec=True,
    ) as m:
        yield m


@pytest.fixture
def mock_kvp_report_success_to_host():
    with mock.patch(
        MOCKPATH + "kvp.report_success_to_host",
        return_value=True,
        autospec=True,
    ) as m:
        yield m


@pytest.fixture
def mock_net_dhcp_maybe_perform_dhcp_discovery():
    with mock.patch(
        "cloudinit.net.ephemeral.maybe_perform_dhcp_discovery",
        return_value={
            "unknown-245": dhcp.IscDhclient.get_ip_from_lease_value(
                "0a:0b:0c:0d"
            ),
            "interface": "ethBoot0",
            "fixed-address": "192.168.2.9",
            "routers": "192.168.2.1",
            "subnet-mask": "255.255.255.0",
        },
        autospec=True,
    ) as m:
        yield m


@pytest.fixture(autouse=True)
def mock_get_interfaces():
    with mock.patch(
        MOCKPATH + "net.get_interfaces",
        return_value=[
            ("dummy0", "9e:65:d6:19:19:01", None, None),
            ("enP3", "00:11:22:33:44:02", "unknown_accel", "0x3"),
            ("eth0", "00:11:22:33:44:00", "hv_netvsc", "0x3"),
            ("eth2", "00:11:22:33:44:01", "unknown", "0x3"),
            ("eth3", "00:11:22:33:44:02", "unknown_with_unknown_vf", "0x3"),
            ("lo", "00:00:00:00:00:00", None, None),
        ],
    ) as m:
        yield m


@pytest.fixture
def mock_get_interface_mac():
    with mock.patch(
        MOCKPATH + "net.get_interface_mac",
        return_value="001122334455",
    ) as m:
        yield m


@pytest.fixture
def mock_netlink():
    with mock.patch(
        MOCKPATH + "netlink",
        autospec=True,
    ) as m:
        yield m


@pytest.fixture
def mock_os_path_isfile():
    with mock.patch(MOCKPATH + "os.path.isfile", autospec=True) as m:
        yield m


@pytest.fixture
def mock_readurl():
    with mock.patch(MOCKPATH + "imds.readurl", autospec=True) as m:
        yield m


@pytest.fixture
def mock_report_diagnostic_event():
    with mock.patch(MOCKPATH + "report_diagnostic_event") as m:
        yield m


@pytest.fixture
def mock_sleep():
    with mock.patch(
        MOCKPATH + "sleep",
        autospec=True,
    ) as m:
        yield m


@pytest.fixture
def mock_subp_subp():
    with mock.patch(MOCKPATH + "subp.subp", side_effect=[]) as m:
        yield m


@pytest.fixture
def mock_timestamp():
    timestamp = datetime.datetime.utcnow()
    with mock.patch.object(errors, "datetime", autospec=True) as m:
        m.utcnow.return_value = timestamp
        yield timestamp


@pytest.fixture
def mock_util_ensure_dir():
    with mock.patch(
        MOCKPATH + "util.ensure_dir",
        autospec=True,
    ) as m:
        yield m


@pytest.fixture
def mock_util_find_devs_with():
    with mock.patch(MOCKPATH + "util.find_devs_with", autospec=True) as m:
        yield m


@pytest.fixture
def mock_util_load_file():
    with mock.patch(
        MOCKPATH + "util.load_binary_file",
        autospec=True,
        return_value=b"",
    ) as m:
        yield m


@pytest.fixture
def mock_util_mount_cb():
    with mock.patch(
        MOCKPATH + "util.mount_cb",
        autospec=True,
        return_value=({}, "", {}, {}),
    ) as m:
        yield m


@pytest.fixture
def wrapped_util_write_file():
    with mock.patch.object(
        dsaz.util,
        "write_file",
        wraps=write_file,
    ) as m:
        yield m


@pytest.fixture
def patched_data_dir_path(tmpdir):
    data_dir_path = Path(tmpdir) / "data_dir"
    data_dir_path.mkdir()
    data_dir = str(data_dir_path)

    with mock.patch(MOCKPATH + "AGENT_SEED_DIR", data_dir):
        with mock.patch.dict(dsaz.BUILTIN_DS_CONFIG, {"data_dir": data_dir}):
            yield data_dir_path


@pytest.fixture
def patched_markers_dir_path(tmpdir):
    patched_markers_dir_path = Path(tmpdir) / "markers"
    patched_markers_dir_path.mkdir()

    yield patched_markers_dir_path


@pytest.fixture
def patched_reported_ready_marker_path(azure_ds, patched_markers_dir_path):
    reported_ready_marker = patched_markers_dir_path / "reported_ready"
    with mock.patch.object(
        azure_ds, "_reported_ready_marker_file", str(reported_ready_marker)
    ):
        yield reported_ready_marker


def fake_http_error_for_code(status_code: int):
    response_failure = requests.Response()
    response_failure.status_code = status_code
    return requests.exceptions.HTTPError(
        "fake error",
        response=response_failure,
    )


def construct_ovf_env(
    *,
    custom_data=None,
    hostname="test-host",
    username="test-user",
    password=None,
    public_keys=None,
    disable_ssh_password_auth=None,
    preprovisioned_vm=None,
    preprovisioned_vm_type=None,
    provision_guest_proxy_agent=None,
):
    content = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<ns0:Environment xmlns="http://schemas.dmtf.org/ovf/environment/1"',
        'xmlns:ns0="http://schemas.dmtf.org/ovf/environment/1"',
        'xmlns:ns1="http://schemas.microsoft.com/windowsazure"',
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">',
        "<ns1:ProvisioningSection>",
        "<ns1:Version>1.0</ns1:Version>",
        "<ns1:LinuxProvisioningConfigurationSet>",
        "<ns1:ConfigurationSetType>"
        "LinuxProvisioningConfiguration"
        "</ns1:ConfigurationSetType>",
    ]
    if hostname is not None:
        content.append("<ns1:HostName>%s</ns1:HostName>" % hostname)
    if username is not None:
        content.append("<ns1:UserName>%s</ns1:UserName>" % username)
    if password is not None:
        content.append("<ns1:UserPassword>%s</ns1:UserPassword>" % password)
    if custom_data is not None:
        content.append(
            "<ns1:CustomData>%s</ns1:CustomData>" % (b64e(custom_data))
        )
    if disable_ssh_password_auth is not None:
        content.append(
            "<ns1:DisableSshPasswordAuthentication>%s"
            % str(disable_ssh_password_auth).lower()
            + "</ns1:DisableSshPasswordAuthentication>"
        )
    if public_keys is not None:
        content += ["<ns1:SSH>", "<ns1:PublicKeys>"]
        for public_key in public_keys:
            content.append("<ns1:PublicKey>")
            fp = public_key.get("fingerprint")
            if fp is not None:
                content.append("<ns1:Fingerprint>%s</ns1:Fingerprint>" % fp)
            path = public_key.get("path")
            if path is not None:
                content.append("<ns1:Path>%s</ns1:Path>" % path)
            value = public_key.get("value")
            if value is not None:
                content.append("<ns1:Value>%s</ns1:Value>" % value)
            content.append("</ns1:PublicKey>")
        content += ["</ns1:PublicKeys>", "</ns1:SSH>"]
    content += [
        "</ns1:LinuxProvisioningConfigurationSet>",
        "</ns1:ProvisioningSection>",
        "<ns1:PlatformSettingsSection>",
        "<ns1:Version>1.0</ns1:Version>",
        "<ns1:PlatformSettings>",
        "<ns1:KmsServerHostname>"
        "kms.core.windows.net"
        "</ns1:KmsServerHostname>",
        "<ns1:ProvisionGuestAgent>false</ns1:ProvisionGuestAgent>",
        '<ns1:GuestAgentPackageName xsi:nil="true" />',
    ]
    if preprovisioned_vm is not None:
        content.append(
            "<ns1:PreprovisionedVm>%s</ns1:PreprovisionedVm>"
            % str(preprovisioned_vm).lower()
        )

    if preprovisioned_vm_type is None:
        content.append('<ns1:PreprovisionedVMType xsi:nil="true" />')
    else:
        content.append(
            "<ns1:PreprovisionedVMType>%s</ns1:PreprovisionedVMType>"
            % preprovisioned_vm_type
        )
    if provision_guest_proxy_agent is not None:
        content.append(
            "<ns1:ProvisionGuestProxyAgent>%s</ns1:ProvisionGuestProxyAgent>"
            % provision_guest_proxy_agent
        )
    content += [
        "</ns1:PlatformSettings>",
        "</ns1:PlatformSettingsSection>",
        "</ns0:Environment>",
    ]

    return "\n".join(content)


NETWORK_METADATA = {
    "compute": {
        "location": "eastus2",
        "name": "my-hostname",
        "offer": "UbuntuServer",
        "osType": "Linux",
        "placementGroupId": "",
        "platformFaultDomain": "0",
        "platformUpdateDomain": "0",
        "publisher": "Canonical",
        "resourceGroupName": "srugroup1",
        "sku": "19.04-DAILY",
        "subscriptionId": "12aad61c-6de4-4e53-a6c6-5aff52a83777",
        "tags": "",
        "version": "19.04.201906190",
        "vmId": "ff702a6b-cb6a-4fcd-ad68-b4ce38227642",
        "vmScaleSetName": "",
        "vmSize": "Standard_DS1_v2",
        "zone": "",
        "publicKeys": [{"keyData": "ssh-rsa key1", "path": "path1"}],
    },
    "network": {
        "interface": [
            {
                "macAddress": "000D3A047598",
                "ipv6": {"ipAddress": []},
                "ipv4": {
                    "subnet": [{"prefix": "24", "address": "10.0.0.0"}],
                    "ipAddress": [
                        {
                            "privateIpAddress": "10.0.0.4",
                            "publicIpAddress": "104.46.124.81",
                        }
                    ],
                },
            }
        ]
    },
}

SECONDARY_INTERFACE = {
    "macAddress": "220D3A047598",
    "ipv6": {"ipAddress": []},
    "ipv4": {
        "subnet": [{"prefix": "24", "address": "10.0.1.0"}],
        "ipAddress": [
            {
                "privateIpAddress": "10.0.1.5",
            }
        ],
    },
}

SECONDARY_INTERFACE_NO_IP = {
    "macAddress": "220D3A047598",
    "ipv6": {"ipAddress": []},
    "ipv4": {
        "subnet": [{"prefix": "24", "address": "10.0.1.0"}],
        "ipAddress": [],
    },
}

IMDS_NETWORK_METADATA = {
    "interface": [
        {
            "macAddress": "000D3A047598",
            "ipv6": {"ipAddress": []},
            "ipv4": {
                "subnet": [{"prefix": "24", "address": "10.0.0.0"}],
                "ipAddress": [
                    {
                        "privateIpAddress": "10.0.0.4",
                        "publicIpAddress": "104.46.124.81",
                    }
                ],
            },
        }
    ]
}

EXAMPLE_UUID = "d0df4c54-4ecb-4a4b-9954-5bdf3ed5c3b8"


class TestGenerateNetworkConfig:
    @pytest.mark.parametrize(
        "label,metadata,ip_config,expected",
        [
            (
                "simple interface",
                NETWORK_METADATA["network"],
                True,
                {
                    "ethernets": {
                        "eth0": {
                            "dhcp4": True,
                            "dhcp4-overrides": {"route-metric": 100},
                            "dhcp6": False,
                            "match": {"macaddress": "00:0d:3a:04:75:98"},
                            "set-name": "eth0",
                        }
                    },
                    "version": 2,
                },
            ),
            (
                "hv_netvsc driver",
                {
                    "interface": [
                        {
                            "macAddress": "001122334400",
                            "ipv6": {"ipAddress": []},
                            "ipv4": {
                                "subnet": [
                                    {"prefix": "24", "address": "10.0.0.0"}
                                ],
                                "ipAddress": [
                                    {
                                        "privateIpAddress": "10.0.0.4",
                                        "publicIpAddress": "104.46.124.81",
                                    }
                                ],
                            },
                        }
                    ]
                },
                True,
                {
                    "ethernets": {
                        "eth0": {
                            "dhcp4": True,
                            "dhcp4-overrides": {"route-metric": 100},
                            "dhcp6": False,
                            "match": {
                                "macaddress": "00:11:22:33:44:00",
                                "driver": "hv_netvsc",
                            },
                            "set-name": "eth0",
                        }
                    },
                    "version": 2,
                },
            ),
            (
                "unknown",
                {
                    "interface": [
                        {
                            "macAddress": "001122334401",
                            "ipv6": {"ipAddress": []},
                            "ipv4": {
                                "subnet": [
                                    {"prefix": "24", "address": "10.0.0.0"}
                                ],
                                "ipAddress": [
                                    {
                                        "privateIpAddress": "10.0.0.4",
                                        "publicIpAddress": "104.46.124.81",
                                    }
                                ],
                            },
                        }
                    ]
                },
                True,
                {
                    "ethernets": {
                        "eth0": {
                            "dhcp4": True,
                            "dhcp4-overrides": {"route-metric": 100},
                            "dhcp6": False,
                            "match": {
                                "macaddress": "00:11:22:33:44:01",
                                "driver": "unknown",
                            },
                            "set-name": "eth0",
                        }
                    },
                    "version": 2,
                },
            ),
            (
                "unknown with unknown matching VF",
                {
                    "interface": [
                        {
                            "macAddress": "001122334402",
                            "ipv6": {"ipAddress": []},
                            "ipv4": {
                                "subnet": [
                                    {"prefix": "24", "address": "10.0.0.0"}
                                ],
                                "ipAddress": [
                                    {
                                        "privateIpAddress": "10.0.0.4",
                                        "publicIpAddress": "104.46.124.81",
                                    }
                                ],
                            },
                        }
                    ]
                },
                True,
                {
                    "ethernets": {
                        "eth0": {
                            "dhcp4": True,
                            "dhcp4-overrides": {"route-metric": 100},
                            "dhcp6": False,
                            "match": {
                                "macaddress": "00:11:22:33:44:02",
                            },
                            "set-name": "eth0",
                        }
                    },
                    "version": 2,
                },
            ),
            (
                "multiple interfaces with increasing route metric",
                {
                    "interface": [
                        {
                            "macAddress": "000D3A047598",
                            "ipv6": {"ipAddress": []},
                            "ipv4": {
                                "subnet": [
                                    {"prefix": "24", "address": "10.0.0.0"}
                                ],
                                "ipAddress": [
                                    {
                                        "privateIpAddress": "10.0.0.4",
                                        "publicIpAddress": "104.46.124.81",
                                    }
                                ],
                            },
                        }
                    ]
                    * 3
                },
                True,
                {
                    "ethernets": {
                        "eth0": {
                            "dhcp4": True,
                            "dhcp4-overrides": {"route-metric": 100},
                            "dhcp6": False,
                            "match": {"macaddress": "00:0d:3a:04:75:98"},
                            "set-name": "eth0",
                        },
                        "eth1": {
                            "set-name": "eth1",
                            "match": {"macaddress": "00:0d:3a:04:75:98"},
                            "dhcp6": False,
                            "dhcp4": True,
                            "dhcp4-overrides": {
                                "route-metric": 200,
                                "use-dns": False,
                            },
                        },
                        "eth2": {
                            "set-name": "eth2",
                            "match": {"macaddress": "00:0d:3a:04:75:98"},
                            "dhcp6": False,
                            "dhcp4": True,
                            "dhcp4-overrides": {
                                "route-metric": 300,
                                "use-dns": False,
                            },
                        },
                    },
                    "version": 2,
                },
            ),
            (
                "secondary IPv4s are static",
                {
                    "interface": [
                        {
                            "macAddress": "000D3A047598",
                            "ipv6": {
                                "subnet": [
                                    {
                                        "prefix": "10",
                                        "address": "2001:dead:beef::16",
                                    }
                                ],
                                "ipAddress": [
                                    {"privateIpAddress": "2001:dead:beef::1"}
                                ],
                            },
                            "ipv4": {
                                "subnet": [
                                    {"prefix": "24", "address": "10.0.0.0"},
                                ],
                                "ipAddress": [
                                    {
                                        "privateIpAddress": "10.0.0.4",
                                        "publicIpAddress": "104.46.124.81",
                                    },
                                    {
                                        "privateIpAddress": "11.0.0.5",
                                        "publicIpAddress": "104.46.124.82",
                                    },
                                    {
                                        "privateIpAddress": "12.0.0.6",
                                        "publicIpAddress": "104.46.124.83",
                                    },
                                ],
                            },
                        }
                    ]
                },
                True,
                {
                    "ethernets": {
                        "eth0": {
                            "addresses": ["11.0.0.5/24", "12.0.0.6/24"],
                            "dhcp4": True,
                            "dhcp4-overrides": {"route-metric": 100},
                            "dhcp6": True,
                            "dhcp6-overrides": {"route-metric": 100},
                            "match": {"macaddress": "00:0d:3a:04:75:98"},
                            "set-name": "eth0",
                        }
                    },
                    "version": 2,
                },
            ),
            (
                "secondary IPv4s are not configured",
                {
                    "interface": [
                        {
                            "macAddress": "000D3A047598",
                            "ipv6": {
                                "subnet": [
                                    {
                                        "prefix": "10",
                                        "address": "2001:dead:beef::16",
                                    }
                                ],
                                "ipAddress": [
                                    {"privateIpAddress": "2001:dead:beef::1"}
                                ],
                            },
                            "ipv4": {
                                "subnet": [
                                    {"prefix": "24", "address": "10.0.0.0"},
                                ],
                                "ipAddress": [
                                    {
                                        "privateIpAddress": "10.0.0.4",
                                        "publicIpAddress": "104.46.124.81",
                                    },
                                    {
                                        "privateIpAddress": "11.0.0.5",
                                        "publicIpAddress": "104.46.124.82",
                                    },
                                    {
                                        "privateIpAddress": "12.0.0.6",
                                        "publicIpAddress": "104.46.124.83",
                                    },
                                ],
                            },
                        }
                    ]
                },
                False,
                {
                    "ethernets": {
                        "eth0": {
                            "dhcp4": True,
                            "dhcp4-overrides": {"route-metric": 100},
                            "dhcp6": True,
                            "dhcp6-overrides": {"route-metric": 100},
                            "match": {"macaddress": "00:0d:3a:04:75:98"},
                            "set-name": "eth0",
                        }
                    },
                    "version": 2,
                },
            ),
            (
                "ipv6 secondaries",
                {
                    "interface": [
                        {
                            "macAddress": "000D3A047598",
                            "ipv6": {
                                "subnet": [
                                    {
                                        "prefix": "10",
                                        "address": "2001:dead:beef::16",
                                    }
                                ],
                                "ipAddress": [
                                    {"privateIpAddress": "2001:dead:beef::1"},
                                    {"privateIpAddress": "2001:dead:beef::2"},
                                ],
                            },
                        }
                    ]
                },
                True,
                {
                    "ethernets": {
                        "eth0": {
                            "addresses": ["2001:dead:beef::2/10"],
                            "dhcp4": True,
                            "dhcp4-overrides": {"route-metric": 100},
                            "dhcp6": True,
                            "dhcp6-overrides": {"route-metric": 100},
                            "match": {"macaddress": "00:0d:3a:04:75:98"},
                            "set-name": "eth0",
                        }
                    },
                    "version": 2,
                },
            ),
            (
                "ipv6 secondaries not configured",
                {
                    "interface": [
                        {
                            "macAddress": "000D3A047598",
                            "ipv6": {
                                "subnet": [
                                    {
                                        "prefix": "10",
                                        "address": "2001:dead:beef::16",
                                    }
                                ],
                                "ipAddress": [
                                    {"privateIpAddress": "2001:dead:beef::1"},
                                    {"privateIpAddress": "2001:dead:beef::2"},
                                ],
                            },
                        }
                    ]
                },
                False,
                {
                    "ethernets": {
                        "eth0": {
                            "dhcp4": True,
                            "dhcp4-overrides": {"route-metric": 100},
                            "dhcp6": True,
                            "dhcp6-overrides": {"route-metric": 100},
                            "match": {"macaddress": "00:0d:3a:04:75:98"},
                            "set-name": "eth0",
                        }
                    },
                    "version": 2,
                },
            ),
        ],
    )
    def test_parsing_scenarios(
        self, label, mock_get_interfaces, metadata, ip_config, expected
    ):
        assert (
            dsaz.generate_network_config_from_instance_network_metadata(
                metadata, apply_network_config_for_secondary_ips=ip_config
            )
            == expected
        )


class TestNetworkConfig:
    fallback_config = {
        "version": 1,
        "config": [
            {
                "type": "physical",
                "name": "eth0",
                "mac_address": "00:11:22:33:44:55",
                "params": {"driver": "hv_netvsc"},
                "subnets": [{"type": "dhcp"}],
            }
        ],
    }

    def test_single_ipv4_nic_configuration(
        self, azure_ds, mock_get_interfaces
    ):
        """Network config emits dhcp on single nic with ipv4"""
        expected = {
            "ethernets": {
                "eth0": {
                    "dhcp4": True,
                    "dhcp4-overrides": {"route-metric": 100},
                    "dhcp6": False,
                    "match": {"macaddress": "00:0d:3a:04:75:98"},
                    "set-name": "eth0",
                },
            },
            "version": 2,
        }
        azure_ds._metadata_imds = NETWORK_METADATA

        assert azure_ds.network_config == expected

    def test_uses_fallback_cfg_when_apply_network_config_is_false(
        self, azure_ds, mock_generate_fallback_config
    ):
        azure_ds.ds_cfg["apply_network_config"] = False
        azure_ds._metadata_imds = NETWORK_METADATA
        mock_generate_fallback_config.return_value = self.fallback_config

        assert azure_ds.network_config == self.fallback_config

    def test_uses_fallback_cfg_when_imds_metadata_unset(
        self, azure_ds, mock_generate_fallback_config
    ):
        azure_ds._metadata_imds = UNSET
        mock_generate_fallback_config.return_value = self.fallback_config

        assert azure_ds.network_config == self.fallback_config

    def test_uses_fallback_cfg_when_no_network_metadata(
        self, azure_ds, mock_generate_fallback_config
    ):
        """Network config generates fallback network config when the
        IMDS instance metadata is corrupted/invalid, such as when
        network metadata is not present.
        """
        imds_metadata_missing_network_metadata = copy.deepcopy(
            NETWORK_METADATA
        )
        del imds_metadata_missing_network_metadata["network"]
        mock_generate_fallback_config.return_value = self.fallback_config
        azure_ds._metadata_imds = imds_metadata_missing_network_metadata

        assert azure_ds.network_config == self.fallback_config

    def test_uses_fallback_cfg_when_no_interface_metadata(
        self, azure_ds, mock_generate_fallback_config
    ):
        """Network config generates fallback network config when the
        IMDS instance metadata is corrupted/invalid, such as when
        network interface metadata is not present.
        """
        imds_metadata_missing_interface_metadata = copy.deepcopy(
            NETWORK_METADATA
        )
        del imds_metadata_missing_interface_metadata["network"]["interface"]
        mock_generate_fallback_config.return_value = self.fallback_config
        azure_ds._metadata_imds = imds_metadata_missing_interface_metadata

        assert azure_ds.network_config == self.fallback_config


class TestAzureDataSource(CiTestCase):
    with_logs = True

    def setUp(self):
        super(TestAzureDataSource, self).setUp()
        self.tmp = self.tmp_dir()

        # patch cloud_dir, so our 'seed_dir' is guaranteed empty
        self.paths = helpers.Paths(
            {"cloud_dir": self.tmp, "run_dir": self.tmp}
        )
        self.waagent_d = os.path.join(self.tmp, "var", "lib", "waagent")

        self.patches = ExitStack()
        self.addCleanup(self.patches.close)

        self.patches.enter_context(
            mock.patch.object(dsaz, "_get_random_seed", return_value="wild")
        )

        self.m_dhcp = self.patches.enter_context(
            mock.patch.object(
                dsaz,
                "EphemeralDHCPv4",
            )
        )
        self.m_dhcp.return_value.lease = {}
        self.m_dhcp.return_value.iface = "eth4"

        self.m_fetch = self.patches.enter_context(
            mock.patch.object(
                dsaz.imds,
                "fetch_metadata_with_api_fallback",
                mock.MagicMock(return_value=NETWORK_METADATA),
            )
        )
        self.m_fallback_nic = self.patches.enter_context(
            mock.patch(
                "cloudinit.sources.net.find_fallback_nic", return_value="eth9"
            )
        )
        self.m_remove_ubuntu_network_scripts = self.patches.enter_context(
            mock.patch.object(
                dsaz,
                "maybe_remove_ubuntu_network_config_scripts",
                mock.MagicMock(),
            )
        )

    def apply_patches(self, patches):
        for module, name, new in patches:
            self.patches.enter_context(mock.patch.object(module, name, new))

    def _get_mockds(self):
        sysctl_out = (
            "dev.storvsc.3.%pnpinfo: "
            "classid=ba6163d9-04a1-4d29-b605-72e2ffb1dc7f "
            "deviceid=f8b3781b-1e82-4818-a1c3-63d806ec15bb\n"
        )
        sysctl_out += (
            "dev.storvsc.2.%pnpinfo: "
            "classid=ba6163d9-04a1-4d29-b605-72e2ffb1dc7f "
            "deviceid=f8b3781a-1e82-4818-a1c3-63d806ec15bb\n"
        )
        sysctl_out += (
            "dev.storvsc.1.%pnpinfo: "
            "classid=32412632-86cb-44a2-9b5c-50d1417354f5 "
            "deviceid=00000000-0001-8899-0000-000000000000\n"
        )
        camctl_devbus = """
scbus0 on ata0 bus 0
scbus1 on ata1 bus 0
scbus2 on blkvsc0 bus 0
scbus3 on blkvsc1 bus 0
scbus4 on storvsc2 bus 0
scbus5 on storvsc3 bus 0
scbus-1 on xpt0 bus 0
        """
        camctl_dev = """
<Msft Virtual CD/ROM 1.0>          at scbus1 target 0 lun 0 (cd0,pass0)
<Msft Virtual Disk 1.0>            at scbus2 target 0 lun 0 (da0,pass1)
<Msft Virtual Disk 1.0>            at scbus3 target 1 lun 0 (da1,pass2)
        """
        self.apply_patches(
            [
                (
                    dsaz,
                    "get_dev_storvsc_sysctl",
                    mock.MagicMock(return_value=sysctl_out),
                ),
                (
                    dsaz,
                    "get_camcontrol_dev_bus",
                    mock.MagicMock(return_value=camctl_devbus),
                ),
                (
                    dsaz,
                    "get_camcontrol_dev",
                    mock.MagicMock(return_value=camctl_dev),
                ),
            ]
        )
        return dsaz

    def _get_ds(
        self,
        data,
        distro="ubuntu",
        apply_network=None,
        instance_id=None,
        write_ovf_to_data_dir: bool = False,
        write_ovf_to_seed_dir: bool = True,
    ):
        def _wait_for_files(flist, _maxwait=None, _naplen=None):
            data["waited"] = flist
            return []

        def _load_possible_azure_ds(seed_dir, cache_dir):
            yield seed_dir
            yield dsaz.DEFAULT_PROVISIONING_ISO_DEV
            yield from data.get("dsdevs", [])
            if cache_dir:
                yield cache_dir

        seed_dir = os.path.join(self.paths.seed_dir, "azure")
        if write_ovf_to_seed_dir and data.get("ovfcontent") is not None:
            populate_dir(seed_dir, {"ovf-env.xml": data["ovfcontent"]})

        if write_ovf_to_data_dir and data.get("ovfcontent") is not None:
            populate_dir(self.waagent_d, {"ovf-env.xml": data["ovfcontent"]})

        dsaz.BUILTIN_DS_CONFIG["data_dir"] = self.waagent_d

        self.m_get_metadata_from_fabric = mock.MagicMock(return_value=[])
        self.m_report_failure_to_fabric = mock.MagicMock(autospec=True)
        self.m_list_possible_azure_ds = mock.MagicMock(
            side_effect=_load_possible_azure_ds
        )

        if instance_id:
            self.instance_id = instance_id
        else:
            self.instance_id = EXAMPLE_UUID

        def _dmi_mocks(key):
            if key == "system-uuid":
                return self.instance_id
            elif key == "chassis-asset-tag":
                return "7783-7084-3265-9085-8269-3286-77"
            raise RuntimeError()

        self.m_read_dmi_data = mock.MagicMock(autospec=True)
        self.m_read_dmi_data.side_effect = _dmi_mocks

        self.apply_patches(
            [
                (
                    dsaz,
                    "list_possible_azure_ds",
                    self.m_list_possible_azure_ds,
                ),
                (
                    dsaz,
                    "get_metadata_from_fabric",
                    self.m_get_metadata_from_fabric,
                ),
                (
                    dsaz,
                    "report_failure_to_fabric",
                    self.m_report_failure_to_fabric,
                ),
                (dsaz, "get_boot_telemetry", mock.MagicMock()),
                (dsaz, "get_system_info", mock.MagicMock()),
                (
                    dsaz.net,
                    "get_interface_mac",
                    mock.MagicMock(return_value="00:15:5d:69:63:ba"),
                ),
                (dsaz.subp, "which", lambda x: True),
                (
                    dmi,
                    "read_dmi_data",
                    self.m_read_dmi_data,
                ),
                (
                    dsaz.util,
                    "wait_for_files",
                    mock.MagicMock(side_effect=_wait_for_files),
                ),
            ]
        )

        if isinstance(distro, str):
            distro_cls = distros.fetch(distro)
            distro = distro_cls(distro, data.get("sys_cfg", {}), self.paths)
        distro.get_tmp_exec_path = mock.Mock(side_effect=self.tmp_dir)
        dsrc = dsaz.DataSourceAzure(
            data.get("sys_cfg", {}), distro=distro, paths=self.paths
        )
        if apply_network is not None:
            dsrc.ds_cfg["apply_network_config"] = apply_network

        return dsrc

    def _get_and_setup(self, dsrc):
        ret = dsrc.get_data()
        if ret:
            dsrc.setup(True)
        return ret

    def xml_equals(self, oxml, nxml):
        """Compare two sets of XML to make sure they are equal"""

        def create_tag_index(xml):
            et = ET.fromstring(xml)
            ret = {}
            for x in et.iter():
                ret[x.tag] = x
            return ret

        def tags_exists(x, y):
            for tag in x.keys():
                assert tag in y
            for tag in y.keys():
                assert tag in x

        def tags_equal(x, y):
            for x_val in x.values():
                y_val = y.get(x_val.tag)
                assert x_val.text == y_val.text

        old_cnt = create_tag_index(oxml)
        new_cnt = create_tag_index(nxml)
        tags_exists(old_cnt, new_cnt)
        tags_equal(old_cnt, new_cnt)

    def xml_notequals(self, oxml, nxml):
        try:
            self.xml_equals(oxml, nxml)
        except AssertionError:
            return
        raise AssertionError("XML is the same")

    def test_get_resource_disk(self):
        ds = self._get_mockds()
        dev = ds.get_resource_disk_on_freebsd(1)
        self.assertEqual("da1", dev)

    def test_not_ds_detect_seed_should_return_no_datasource(self):
        """Check seed_dir using ds_detect and return False."""
        # Return a non-matching asset tag value
        data = {}
        dsrc = self._get_ds(data)
        self.m_read_dmi_data.side_effect = lambda x: "notazure"
        with mock.patch.object(
            dsrc, "crawl_metadata"
        ) as m_crawl_metadata, mock.patch.object(
            dsrc, "_report_failure"
        ) as m_report_failure:
            ret = dsrc.get_data()
            assert self.m_read_dmi_data.mock_calls == [
                mock.call("chassis-asset-tag")
            ]
            self.assertFalse(ret)
            # Assert that for non viable platforms,
            # there is no communication with the Azure datasource.
            self.assertEqual(0, m_crawl_metadata.call_count)
            self.assertEqual(0, m_report_failure.call_count)

    def test_platform_viable_but_no_devs_should_return_no_datasource(self):
        """For platforms where the Azure platform is viable
        (which is indicated by the matching asset tag),
        the absence of any devs at all (devs == candidate sources
        for crawling Azure datasource) is NOT expected.
        Report failure to Azure as this is an unexpected fatal error.
        """
        data = {}
        dsrc = self._get_ds(data)
        with mock.patch.object(dsrc, "_report_failure") as m_report_failure:
            ret = dsrc.get_data()
            self.assertFalse(ret)
            self.assertEqual(1, m_report_failure.call_count)

    def test_crawl_metadata_exception_returns_no_datasource(self):
        data = {}
        dsrc = self._get_ds(data)
        with mock.patch.object(dsrc, "crawl_metadata") as m_crawl_metadata:
            m_crawl_metadata.side_effect = Exception
            ret = dsrc.get_data()
            self.assertEqual(1, m_crawl_metadata.call_count)
            self.assertFalse(ret)

    def test_crawl_metadata_exception_should_report_failure(self):
        data = {}
        dsrc = self._get_ds(data)
        with mock.patch.object(
            dsrc, "crawl_metadata"
        ) as m_crawl_metadata, mock.patch.object(
            dsrc, "_report_failure"
        ) as m_report_failure:
            m_crawl_metadata.side_effect = Exception
            dsrc.get_data()
            self.assertEqual(1, m_crawl_metadata.call_count)
            m_report_failure.assert_called_once_with(mock.ANY)

    def test_crawl_metadata_exc_should_log_could_not_crawl_msg(self):
        data = {}
        dsrc = self._get_ds(data)
        with mock.patch.object(dsrc, "crawl_metadata") as m_crawl_metadata:
            m_crawl_metadata.side_effect = Exception
            dsrc.get_data()
            self.assertEqual(1, m_crawl_metadata.call_count)
            self.assertIn(
                "Azure datasource failure occurred:", self.logs.getvalue()
            )

    def test_basic_seed_dir(self):
        data = {
            "ovfcontent": construct_ovf_env(hostname="myhost"),
            "sys_cfg": {},
        }
        dsrc = self._get_ds(data)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEqual(dsrc.userdata_raw, "")
        self.assertEqual(dsrc.metadata["local-hostname"], "myhost")
        self.assertTrue(
            os.path.isfile(os.path.join(self.waagent_d, "ovf-env.xml"))
        )
        self.assertEqual("azure", dsrc.cloud_name)
        self.assertEqual("azure", dsrc.platform_type)
        self.assertEqual(
            "seed-dir (%s/seed/azure)" % self.tmp, dsrc.subplatform
        )

    def test_data_dir_without_imds_data(self):
        data = {
            "ovfcontent": construct_ovf_env(hostname="myhost"),
            "sys_cfg": {},
        }
        dsrc = self._get_ds(
            data, write_ovf_to_data_dir=True, write_ovf_to_seed_dir=False
        )

        self.m_fetch.return_value = {}
        with mock.patch(MOCKPATH + "util.mount_cb") as m_mount_cb:
            m_mount_cb.side_effect = [
                MountFailedError("fail"),
                ({"local-hostname": "me"}, "ud", {"cfg": ""}, {}),
            ]
            ret = dsrc.get_data()

        self.assertTrue(ret)
        self.assertEqual(dsrc.userdata_raw, "")
        self.assertEqual(dsrc.metadata["local-hostname"], "myhost")
        self.assertTrue(
            os.path.isfile(os.path.join(self.waagent_d, "ovf-env.xml"))
        )
        self.assertEqual("azure", dsrc.cloud_name)
        self.assertEqual("azure", dsrc.platform_type)
        self.assertEqual("seed-dir (%s)" % self.waagent_d, dsrc.subplatform)

    def test_basic_dev_file(self):
        """When a device path is used, present that in subplatform."""
        data = {"sys_cfg": {}, "dsdevs": ["/dev/cd0"]}
        dsrc = self._get_ds(data)
        # DSAzure will attempt to mount /dev/sr0 first, which should
        # fail with mount error since the list of devices doesn't have
        # /dev/sr0
        with mock.patch(MOCKPATH + "util.mount_cb") as m_mount_cb:
            m_mount_cb.side_effect = [
                MountFailedError("fail"),
                ({"local-hostname": "me"}, "ud", {"cfg": ""}, {}),
            ]
            self.assertTrue(dsrc.get_data())
        self.assertEqual(dsrc.userdata_raw, "ud")
        self.assertEqual(dsrc.metadata["local-hostname"], "me")
        self.assertEqual("azure", dsrc.cloud_name)
        self.assertEqual("azure", dsrc.platform_type)
        self.assertEqual("config-disk (/dev/cd0)", dsrc.subplatform)

    def test_get_data_non_ubuntu_will_not_remove_network_scripts(self):
        """get_data on non-Ubuntu will not remove ubuntu net scripts."""
        data = {
            "ovfcontent": construct_ovf_env(
                hostname="myhost", username="myuser"
            ),
            "sys_cfg": {},
        }

        dsrc = self._get_ds(data, distro="debian")
        dsrc.get_data()
        self.m_remove_ubuntu_network_scripts.assert_not_called()

    def test_get_data_on_ubuntu_will_remove_network_scripts(self):
        """get_data will remove ubuntu net scripts on Ubuntu distro."""
        sys_cfg = {"datasource": {"Azure": {"apply_network_config": True}}}
        data = {
            "ovfcontent": construct_ovf_env(),
            "sys_cfg": sys_cfg,
        }

        dsrc = self._get_ds(data, distro="ubuntu")
        dsrc.get_data()
        self.m_remove_ubuntu_network_scripts.assert_called_once_with()

    def test_get_data_on_ubuntu_will_not_remove_network_scripts_disabled(self):
        """When apply_network_config false, do not remove scripts on Ubuntu."""
        sys_cfg = {"datasource": {"Azure": {"apply_network_config": False}}}
        data = {
            "ovfcontent": construct_ovf_env(),
            "sys_cfg": sys_cfg,
        }

        dsrc = self._get_ds(data, distro="ubuntu")
        dsrc.get_data()
        self.m_remove_ubuntu_network_scripts.assert_not_called()

    def test_crawl_metadata_returns_structured_data_and_caches_nothing(self):
        """Return all structured metadata and cache no class attributes."""
        data = {
            "ovfcontent": construct_ovf_env(
                hostname="myhost", username="myuser", custom_data="FOOBAR"
            ),
            "sys_cfg": {},
        }
        dsrc = self._get_ds(data)
        expected_cfg = {
            "PreprovisionedVMType": None,
            "PreprovisionedVm": False,
            "ProvisionGuestProxyAgent": False,
            "system_info": {"default_user": {"name": "myuser"}},
        }
        expected_metadata = {
            "imds": NETWORK_METADATA,
            "instance-id": EXAMPLE_UUID,
            "local-hostname": "myhost",
            "random_seed": "wild",
        }

        crawled_metadata = dsrc.crawl_metadata()

        self.assertCountEqual(
            crawled_metadata.keys(),
            ["cfg", "files", "metadata", "userdata_raw"],
        )
        self.assertEqual(crawled_metadata["cfg"], expected_cfg)
        self.assertEqual(
            list(crawled_metadata["files"].keys()), ["ovf-env.xml"]
        )
        self.assertIn(
            b"<ns1:HostName>myhost</ns1:HostName>",
            crawled_metadata["files"]["ovf-env.xml"],
        )
        self.assertEqual(crawled_metadata["metadata"], expected_metadata)
        self.assertEqual(crawled_metadata["userdata_raw"], b"FOOBAR")
        self.assertEqual(dsrc.userdata_raw, None)
        self.assertEqual(dsrc.metadata, {})
        self.assertEqual(dsrc._metadata_imds, UNSET)
        self.assertFalse(
            os.path.isfile(os.path.join(self.waagent_d, "ovf-env.xml"))
        )

    def test_crawl_metadata_raises_invalid_metadata_on_error(self):
        """crawl_metadata raises an exception on invalid ovf-env.xml."""
        data = {"ovfcontent": "BOGUS", "sys_cfg": {}}
        dsrc = self._get_ds(data)
        error_msg = "error parsing ovf-env.xml: syntax error: line 1, column 0"
        with self.assertRaises(
            errors.ReportableErrorOvfParsingException
        ) as cm:
            dsrc.crawl_metadata()
        self.assertEqual(cm.exception.reason, error_msg)

    def test_crawl_metadata_call_imds_once_no_reprovision(self):
        """If reprovisioning, report ready at the end"""
        ovfenv = construct_ovf_env(preprovisioned_vm=False)

        data = {"ovfcontent": ovfenv, "sys_cfg": {}}
        dsrc = self._get_ds(data)
        dsrc.crawl_metadata()
        self.assertEqual(1, self.m_fetch.call_count)

    @mock.patch("cloudinit.sources.DataSourceAzure.util.write_file")
    @mock.patch(
        "cloudinit.sources.DataSourceAzure.DataSourceAzure._report_ready"
    )
    @mock.patch("cloudinit.sources.DataSourceAzure.DataSourceAzure._poll_imds")
    def test_crawl_metadata_call_imds_twice_with_reprovision(
        self, poll_imds_func, m_report_ready, m_write
    ):
        """If reprovisioning, imds metadata will be fetched twice"""
        ovfenv = construct_ovf_env(preprovisioned_vm=True)

        data = {"ovfcontent": ovfenv, "sys_cfg": {}}
        dsrc = self._get_ds(data)
        poll_imds_func.return_value = ovfenv
        dsrc.crawl_metadata()
        self.assertEqual(2, self.m_fetch.call_count)

    def test_waagent_d_has_0700_perms(self):
        # we expect /var/lib/waagent to be created 0700
        dsrc = self._get_ds({"ovfcontent": construct_ovf_env()})
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertTrue(os.path.isdir(self.waagent_d))
        self.assertEqual(stat.S_IMODE(os.stat(self.waagent_d).st_mode), 0o700)

    def test_network_config_set_from_imds(self):
        """Datasource.network_config returns IMDS network data."""
        sys_cfg = {"datasource": {"Azure": {"apply_network_config": True}}}
        data = {
            "ovfcontent": construct_ovf_env(),
            "sys_cfg": sys_cfg,
        }
        expected_network_config = {
            "ethernets": {
                "eth0": {
                    "set-name": "eth0",
                    "match": {"macaddress": "00:0d:3a:04:75:98"},
                    "dhcp6": False,
                    "dhcp4": True,
                    "dhcp4-overrides": {"route-metric": 100},
                },
            },
            "version": 2,
        }
        dsrc = self._get_ds(data)
        dsrc.get_data()
        self.assertEqual(expected_network_config, dsrc.network_config)

    def test_network_config_set_from_imds_route_metric_for_secondary_nic(self):
        """Datasource.network_config adds route-metric to secondary nics."""
        sys_cfg = {"datasource": {"Azure": {"apply_network_config": True}}}
        data = {
            "ovfcontent": construct_ovf_env(),
            "sys_cfg": sys_cfg,
        }
        expected_network_config = {
            "ethernets": {
                "eth0": {
                    "set-name": "eth0",
                    "match": {"macaddress": "00:0d:3a:04:75:98"},
                    "dhcp6": False,
                    "dhcp4": True,
                    "dhcp4-overrides": {"route-metric": 100},
                },
                "eth1": {
                    "set-name": "eth1",
                    "match": {"macaddress": "22:0d:3a:04:75:98"},
                    "dhcp6": False,
                    "dhcp4": True,
                    "dhcp4-overrides": {"route-metric": 200, "use-dns": False},
                },
                "eth2": {
                    "set-name": "eth2",
                    "match": {"macaddress": "33:0d:3a:04:75:98"},
                    "dhcp6": False,
                    "dhcp4": True,
                    "dhcp4-overrides": {"route-metric": 300, "use-dns": False},
                },
            },
            "version": 2,
        }
        imds_data = copy.deepcopy(NETWORK_METADATA)
        imds_data["network"]["interface"].append(SECONDARY_INTERFACE)
        third_intf = copy.deepcopy(SECONDARY_INTERFACE)
        third_intf["macAddress"] = third_intf["macAddress"].replace("22", "33")
        third_intf["ipv4"]["subnet"][0]["address"] = "10.0.2.0"
        third_intf["ipv4"]["ipAddress"][0]["privateIpAddress"] = "10.0.2.6"
        imds_data["network"]["interface"].append(third_intf)

        self.m_fetch.return_value = imds_data
        dsrc = self._get_ds(data)
        dsrc.get_data()
        self.assertEqual(expected_network_config, dsrc.network_config)

    def test_network_config_set_from_imds_for_secondary_nic_no_ip(self):
        """If an IP address is empty then there should no config for it."""
        sys_cfg = {"datasource": {"Azure": {"apply_network_config": True}}}
        data = {
            "ovfcontent": construct_ovf_env(),
            "sys_cfg": sys_cfg,
        }
        expected_network_config = {
            "ethernets": {
                "eth0": {
                    "set-name": "eth0",
                    "match": {"macaddress": "00:0d:3a:04:75:98"},
                    "dhcp6": False,
                    "dhcp4": True,
                    "dhcp4-overrides": {"route-metric": 100},
                },
            },
            "version": 2,
        }
        imds_data = copy.deepcopy(NETWORK_METADATA)
        imds_data["network"]["interface"].append(SECONDARY_INTERFACE_NO_IP)
        self.m_fetch.return_value = imds_data
        dsrc = self._get_ds(data)
        dsrc.get_data()
        self.assertEqual(expected_network_config, dsrc.network_config)

    def test_availability_zone_set_from_imds(self):
        """Datasource.availability returns IMDS platformFaultDomain."""
        sys_cfg = {"datasource": {"Azure": {"apply_network_config": True}}}
        data = {
            "ovfcontent": construct_ovf_env(),
            "sys_cfg": sys_cfg,
        }
        dsrc = self._get_ds(data)
        dsrc.get_data()
        self.assertEqual("0", dsrc.availability_zone)

    def test_region_set_from_imds(self):
        """Datasource.region returns IMDS region location."""
        sys_cfg = {"datasource": {"Azure": {"apply_network_config": True}}}
        data = {
            "ovfcontent": construct_ovf_env(),
            "sys_cfg": sys_cfg,
        }
        dsrc = self._get_ds(data)
        dsrc.get_data()
        self.assertEqual("eastus2", dsrc.region)

    def test_sys_cfg_set_never_destroy_ntfs(self):
        sys_cfg = {
            "datasource": {
                "Azure": {"never_destroy_ntfs": "user-supplied-value"}
            }
        }
        data = {
            "ovfcontent": construct_ovf_env(),
            "sys_cfg": sys_cfg,
        }

        dsrc = self._get_ds(data)
        ret = self._get_and_setup(dsrc)
        self.assertTrue(ret)
        self.assertEqual(
            dsrc.ds_cfg.get(dsaz.DS_CFG_KEY_PRESERVE_NTFS),
            "user-supplied-value",
        )

    def test_username_used(self):
        data = {"ovfcontent": construct_ovf_env(username="myuser")}

        dsrc = self._get_ds(data)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEqual(
            dsrc.cfg["system_info"]["default_user"]["name"], "myuser"
        )

        assert "ssh_pwauth" not in dsrc.cfg

    def test_password_given(self):
        data = {
            "ovfcontent": construct_ovf_env(
                username="myuser", password="mypass"
            )
        }

        dsrc = self._get_ds(data)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertIn("default_user", dsrc.cfg["system_info"])
        defuser = dsrc.cfg["system_info"]["default_user"]

        # default user should be updated username and should not be locked.
        self.assertEqual(defuser["name"], "myuser")
        self.assertFalse(defuser["lock_passwd"])
        # passwd is crypt formated string $id$salt$encrypted
        # encrypting plaintext with salt value of everything up to final '$'
        # should equal that after the '$'
        self.assertTrue(
            passlib.hash.sha512_crypt.verify(
                "mypass", defuser["hashed_passwd"]
            )
        )

        assert dsrc.cfg["ssh_pwauth"] is True

    def test_password_with_disable_ssh_pw_auth_true(self):
        data = {
            "ovfcontent": construct_ovf_env(
                username="myuser",
                password="mypass",
                disable_ssh_password_auth=True,
            )
        }

        dsrc = self._get_ds(data)
        dsrc.get_data()

        assert dsrc.cfg["ssh_pwauth"] is False

    def test_password_with_disable_ssh_pw_auth_false(self):
        data = {
            "ovfcontent": construct_ovf_env(
                username="myuser",
                password="mypass",
                disable_ssh_password_auth=False,
            )
        }

        dsrc = self._get_ds(data)
        dsrc.get_data()

        assert dsrc.cfg["ssh_pwauth"] is True

    def test_password_with_disable_ssh_pw_auth_unspecified(self):
        data = {
            "ovfcontent": construct_ovf_env(
                username="myuser",
                password="mypass",
                disable_ssh_password_auth=None,
            )
        }

        dsrc = self._get_ds(data)
        dsrc.get_data()

        assert dsrc.cfg["ssh_pwauth"] is True

    def test_no_password_with_disable_ssh_pw_auth_true(self):
        data = {
            "ovfcontent": construct_ovf_env(
                username="myuser",
                disable_ssh_password_auth=True,
            )
        }

        dsrc = self._get_ds(data)
        dsrc.get_data()

        assert dsrc.cfg["ssh_pwauth"] is False

    def test_no_password_with_disable_ssh_pw_auth_false(self):
        data = {
            "ovfcontent": construct_ovf_env(
                username="myuser",
                disable_ssh_password_auth=False,
            )
        }

        dsrc = self._get_ds(data)
        dsrc.get_data()

        assert dsrc.cfg["ssh_pwauth"] is True

    def test_no_password_with_disable_ssh_pw_auth_unspecified(self):
        data = {
            "ovfcontent": construct_ovf_env(
                username="myuser",
                disable_ssh_password_auth=None,
            )
        }

        dsrc = self._get_ds(data)
        dsrc.get_data()

        assert "ssh_pwauth" not in dsrc.cfg

    def test_user_not_locked_if_password_redacted(self):
        data = {
            "ovfcontent": construct_ovf_env(
                username="myuser",
                password=dsaz.DEF_PASSWD_REDACTION,
            )
        }

        dsrc = self._get_ds(data)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertIn("default_user", dsrc.cfg["system_info"])
        defuser = dsrc.cfg["system_info"]["default_user"]

        # default user should be updated username and should not be locked.
        self.assertEqual(defuser["name"], "myuser")
        self.assertIn("lock_passwd", defuser)
        self.assertFalse(defuser["lock_passwd"])

    def test_userdata_found(self):
        mydata = "FOOBAR"
        data = {"ovfcontent": construct_ovf_env(custom_data=mydata)}

        dsrc = self._get_ds(data)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEqual(dsrc.userdata_raw, mydata.encode("utf-8"))

    def test_default_ephemeral_configs_ephemeral_exists(self):
        # make sure the ephemeral configs are correct if disk present
        data = {
            "ovfcontent": construct_ovf_env(),
            "sys_cfg": {},
        }

        orig_exists = dsaz.os.path.exists

        def changed_exists(path):
            return (
                True if path == dsaz.RESOURCE_DISK_PATH else orig_exists(path)
            )

        with mock.patch(MOCKPATH + "os.path.exists", new=changed_exists):
            dsrc = self._get_ds(data)
            ret = dsrc.get_data()
            self.assertTrue(ret)
            cfg = dsrc.get_config_obj()

            self.assertEqual(
                dsrc.device_name_to_device("ephemeral0"),
                dsaz.RESOURCE_DISK_PATH,
            )
            assert "disk_setup" in cfg
            assert "fs_setup" in cfg
            self.assertIsInstance(cfg["disk_setup"], dict)
            self.assertIsInstance(cfg["fs_setup"], list)

    def test_default_ephemeral_configs_ephemeral_does_not_exist(self):
        # make sure the ephemeral configs are correct if disk not present
        data = {
            "ovfcontent": construct_ovf_env(),
            "sys_cfg": {},
        }

        orig_exists = dsaz.os.path.exists

        def changed_exists(path):
            return (
                False if path == dsaz.RESOURCE_DISK_PATH else orig_exists(path)
            )

        with mock.patch(MOCKPATH + "os.path.exists", new=changed_exists):
            dsrc = self._get_ds(data)
            ret = dsrc.get_data()
            self.assertTrue(ret)
            cfg = dsrc.get_config_obj()

            assert "disk_setup" not in cfg
            assert "fs_setup" not in cfg

    def test_userdata_arrives(self):
        userdata = "This is my user-data"
        xml = construct_ovf_env(custom_data=userdata)
        data = {"ovfcontent": xml}
        dsrc = self._get_ds(data)
        dsrc.get_data()

        self.assertEqual(userdata.encode("us-ascii"), dsrc.userdata_raw)

    def test_password_redacted_in_ovf(self):
        data = {
            "ovfcontent": construct_ovf_env(
                username="myuser", password="mypass"
            )
        }
        dsrc = self._get_ds(data)
        ret = dsrc.get_data()

        self.assertTrue(ret)
        ovf_env_path = os.path.join(self.waagent_d, "ovf-env.xml")

        # The XML should not be same since the user password is redacted
        on_disk_ovf = load_text_file(ovf_env_path)
        self.xml_notequals(data["ovfcontent"], on_disk_ovf)

        # Make sure that the redacted password on disk is not used by CI
        self.assertNotEqual(
            dsrc.cfg.get("password"), dsaz.DEF_PASSWD_REDACTION
        )

        # Make sure that the password was really encrypted
        et = ET.fromstring(on_disk_ovf)
        for elem in et.iter():
            if "UserPassword" in elem.tag:
                self.assertEqual(dsaz.DEF_PASSWD_REDACTION, elem.text)

    def test_ovf_env_arrives_in_waagent_dir(self):
        xml = construct_ovf_env(custom_data="FOODATA")
        dsrc = self._get_ds({"ovfcontent": xml})
        dsrc.get_data()

        # 'data_dir' is '/var/lib/waagent' (walinux-agent's state dir)
        # we expect that the ovf-env.xml file is copied there.
        ovf_env_path = os.path.join(self.waagent_d, "ovf-env.xml")
        self.assertTrue(os.path.exists(ovf_env_path))
        self.xml_equals(xml, load_text_file(ovf_env_path))

    def test_ovf_can_include_unicode(self):
        xml = construct_ovf_env()
        xml = "\ufeff{0}".format(xml)
        dsrc = self._get_ds({"ovfcontent": xml})
        dsrc.get_data()

    def test_dsaz_report_ready_returns_true_when_report_succeeds(self):
        dsrc = self._get_ds({"ovfcontent": construct_ovf_env()})
        assert dsrc._report_ready() == []

    @mock.patch(MOCKPATH + "report_diagnostic_event")
    def test_dsaz_report_ready_failure_reports_telemetry(self, m_report_diag):
        dsrc = self._get_ds({"ovfcontent": construct_ovf_env()})
        self.m_get_metadata_from_fabric.side_effect = Exception("foo")

        with pytest.raises(Exception):
            dsrc._report_ready()

        assert m_report_diag.mock_calls == [
            mock.call(
                "Error communicating with Azure fabric; "
                "You may experience connectivity issues: foo",
                logger_func=dsaz.LOG.warning,
            )
        ]

    def test_dsaz_report_failure_returns_true_when_report_succeeds(self):
        dsrc = self._get_ds({"ovfcontent": construct_ovf_env()})

        with mock.patch.object(dsrc, "crawl_metadata") as m_crawl_metadata:
            # mock crawl metadata failure to cause report failure
            m_crawl_metadata.side_effect = Exception

            error = errors.ReportableError(reason="foo")
            self.assertTrue(dsrc._report_failure(error))
            self.assertEqual(1, self.m_report_failure_to_fabric.call_count)

    def test_dsaz_report_failure_returns_false_and_does_not_propagate_exc(
        self,
    ):
        dsrc = self._get_ds({"ovfcontent": construct_ovf_env()})

        with mock.patch.object(
            dsrc, "crawl_metadata"
        ) as m_crawl_metadata, mock.patch.object(
            dsrc, "_ephemeral_dhcp_ctx"
        ) as m_ephemeral_dhcp_ctx, mock.patch.object(
            dsrc.distro.networking, "is_up"
        ) as m_dsrc_distro_networking_is_up:
            # mock crawl metadata failure to cause report failure
            m_crawl_metadata.side_effect = Exception

            # setup mocks to allow using cached ephemeral dhcp lease
            m_dsrc_distro_networking_is_up.return_value = True
            test_lease_dhcp_option_245 = "test_lease_dhcp_option_245"
            test_lease = {"unknown-245": test_lease_dhcp_option_245}
            m_ephemeral_dhcp_ctx.lease = test_lease

            # We expect 2 calls to report_failure_to_fabric,
            # because we try 2 different methods of calling report failure.
            # The different methods are attempted in the following order:
            # 1. Using cached ephemeral dhcp context to report failure to Azure
            # 2. Using new ephemeral dhcp to report failure to Azure
            self.m_report_failure_to_fabric.side_effect = Exception

            error = errors.ReportableError(reason="foo")
            self.assertFalse(dsrc._report_failure(error))
            self.assertEqual(2, self.m_report_failure_to_fabric.call_count)

    def test_dsaz_report_failure(self):
        dsrc = self._get_ds({"ovfcontent": construct_ovf_env()})

        with mock.patch.object(dsrc, "crawl_metadata") as m_crawl_metadata:
            m_crawl_metadata.side_effect = Exception

            error = errors.ReportableError(reason="foo")
            self.assertTrue(dsrc._report_failure(error))
            self.m_report_failure_to_fabric.assert_called_once_with(
                endpoint="168.63.129.16", error=error
            )

    def test_dsaz_report_failure_uses_cached_ephemeral_dhcp_ctx_lease(self):
        dsrc = self._get_ds({"ovfcontent": construct_ovf_env()})

        with mock.patch.object(
            dsrc, "crawl_metadata"
        ) as m_crawl_metadata, mock.patch.object(
            dsrc, "_wireserver_endpoint", "test-ep"
        ):
            # mock crawl metadata failure to cause report failure
            m_crawl_metadata.side_effect = Exception

            error = errors.ReportableError(reason="foo")
            self.assertTrue(dsrc._report_failure(error))

            # ensure called with cached ephemeral dhcp lease option 245
            self.m_report_failure_to_fabric.assert_called_once_with(
                endpoint="test-ep", error=error
            )

    def test_dsaz_report_failure_no_net_uses_new_ephemeral_dhcp_lease(self):
        dsrc = self._get_ds({"ovfcontent": construct_ovf_env()})

        with mock.patch.object(dsrc, "crawl_metadata") as m_crawl_metadata:
            # mock crawl metadata failure to cause report failure
            m_crawl_metadata.side_effect = Exception

            test_lease_dhcp_option_245 = "1.2.3.4"
            test_lease = {
                "unknown-245": test_lease_dhcp_option_245,
                "interface": "eth0",
            }
            self.m_dhcp.return_value.obtain_lease.return_value = test_lease

            error = errors.ReportableError(reason="foo")
            self.assertTrue(dsrc._report_failure(error))

            # ensure called with the newly discovered
            # ephemeral dhcp lease option 245
            self.m_report_failure_to_fabric.assert_called_once_with(
                endpoint="1.2.3.4", error=error
            )

    def test_exception_fetching_fabric_data_doesnt_propagate(self):
        """Errors communicating with fabric should warn, but return True."""
        dsrc = self._get_ds({"ovfcontent": construct_ovf_env()})
        self.m_get_metadata_from_fabric.side_effect = Exception
        ret = self._get_and_setup(dsrc)
        self.assertTrue(ret)

    def test_fabric_data_included_in_metadata(self):
        dsrc = self._get_ds({"ovfcontent": construct_ovf_env()})
        self.m_get_metadata_from_fabric.return_value = ["ssh-key-value"]
        ret = self._get_and_setup(dsrc)
        self.assertTrue(ret)
        self.assertEqual(["ssh-key-value"], dsrc.metadata["public-keys"])

    def test_instance_id_case_insensitive(self):
        """Return the previous iid when current is a case-insensitive match."""
        lower_iid = EXAMPLE_UUID.lower()
        upper_iid = EXAMPLE_UUID.upper()
        # lowercase current UUID
        ds = self._get_ds(
            {"ovfcontent": construct_ovf_env()}, instance_id=lower_iid
        )
        # UPPERCASE previous
        write_file(
            os.path.join(self.paths.cloud_dir, "data", "instance-id"),
            upper_iid,
        )
        ds.get_data()
        self.assertEqual(upper_iid, ds.metadata["instance-id"])

        # UPPERCASE current UUID
        ds = self._get_ds(
            {"ovfcontent": construct_ovf_env()}, instance_id=upper_iid
        )
        # lowercase previous
        write_file(
            os.path.join(self.paths.cloud_dir, "data", "instance-id"),
            lower_iid,
        )
        ds.get_data()
        self.assertEqual(lower_iid, ds.metadata["instance-id"])

    def test_instance_id_endianness(self):
        """Return the previous iid when dmi uuid is the byteswapped iid."""
        ds = self._get_ds({"ovfcontent": construct_ovf_env()})
        # byte-swapped previous
        write_file(
            os.path.join(self.paths.cloud_dir, "data", "instance-id"),
            "544CDFD0-CB4E-4B4A-9954-5BDF3ED5C3B8",
        )
        ds.get_data()
        self.assertEqual(
            "544CDFD0-CB4E-4B4A-9954-5BDF3ED5C3B8", ds.metadata["instance-id"]
        )
        # not byte-swapped previous
        write_file(
            os.path.join(self.paths.cloud_dir, "data", "instance-id"),
            "644CDFD0-CB4E-4B4A-9954-5BDF3ED5C3B8",
        )
        ds.get_data()
        self.assertEqual(self.instance_id, ds.metadata["instance-id"])

    def test_instance_id_from_dmidecode_used(self):
        ds = self._get_ds({"ovfcontent": construct_ovf_env()})
        ds.get_data()
        self.assertEqual(self.instance_id, ds.metadata["instance-id"])

    def test_instance_id_from_dmidecode_used_for_builtin(self):
        ds = self._get_ds({"ovfcontent": construct_ovf_env()})
        ds.get_data()
        self.assertEqual(self.instance_id, ds.metadata["instance-id"])

    @mock.patch(MOCKPATH + "util.is_FreeBSD")
    @mock.patch(MOCKPATH + "_check_freebsd_cdrom")
    def test_list_possible_azure_ds(self, m_check_fbsd_cdrom, m_is_FreeBSD):
        """On FreeBSD, possible devs should show /dev/cd0."""
        m_is_FreeBSD.return_value = True
        m_check_fbsd_cdrom.return_value = True
        possible_ds = []
        for src in dsaz.list_possible_azure_ds("seed_dir", "cache_dir"):
            possible_ds.append(src)
        self.assertEqual(
            possible_ds,
            [
                "seed_dir",
                dsaz.DEFAULT_PROVISIONING_ISO_DEV,
                "/dev/cd0",
                "cache_dir",
            ],
        )
        self.assertEqual(
            [mock.call("/dev/cd0")], m_check_fbsd_cdrom.call_args_list
        )

    @mock.patch(MOCKPATH + "net.get_interfaces")
    def test_blacklist_through_distro(self, m_net_get_interfaces):
        """Verify Azure DS updates blacklist drivers in the distro's
        networking object."""
        data = {
            "ovfcontent": construct_ovf_env(),
            "sys_cfg": {},
        }

        distro_cls = distros.fetch("ubuntu")
        distro = distro_cls("ubuntu", {}, self.paths)
        dsrc = self._get_ds(data, distro=distro)
        dsrc.get_data()

        distro.networking.get_interfaces_by_mac()
        m_net_get_interfaces.assert_called_with()

    @mock.patch(
        "cloudinit.sources.helpers.azure.OpenSSLManager.parse_certificates"
    )
    def test_get_public_ssh_keys_with_imds(self, m_parse_certificates):
        sys_cfg = {"datasource": {"Azure": {"apply_network_config": True}}}
        data = {
            "ovfcontent": construct_ovf_env(),
            "sys_cfg": sys_cfg,
        }
        dsrc = self._get_ds(data)
        dsrc.get_data()
        dsrc.setup(True)
        ssh_keys = dsrc.get_public_ssh_keys()
        self.assertEqual(ssh_keys, ["ssh-rsa key1"])
        self.assertEqual(m_parse_certificates.call_count, 0)

    def test_key_without_crlf_valid(self):
        test_key = "ssh-rsa somerandomkeystuff some comment"
        assert True is dsaz._key_is_openssh_formatted(test_key)

    def test_key_with_crlf_invalid(self):
        test_key = "ssh-rsa someran\r\ndomkeystuff some comment"
        assert False is dsaz._key_is_openssh_formatted(test_key)

    def test_key_endswith_crlf_valid(self):
        test_key = "ssh-rsa somerandomkeystuff some comment\r\n"
        assert True is dsaz._key_is_openssh_formatted(test_key)

    @mock.patch(
        "cloudinit.sources.helpers.azure.OpenSSLManager.parse_certificates"
    )
    def test_get_public_ssh_keys_with_no_openssh_format(
        self, m_parse_certificates
    ):
        imds_data = copy.deepcopy(NETWORK_METADATA)
        imds_data["compute"]["publicKeys"][0]["keyData"] = "no-openssh-format"
        self.m_fetch.return_value = imds_data
        sys_cfg = {"datasource": {"Azure": {"apply_network_config": True}}}
        data = {
            "ovfcontent": construct_ovf_env(),
            "sys_cfg": sys_cfg,
        }
        dsrc = self._get_ds(data)
        dsrc.get_data()
        dsrc.setup(True)
        ssh_keys = dsrc.get_public_ssh_keys()
        self.assertEqual(ssh_keys, [])
        self.assertEqual(m_parse_certificates.call_count, 0)

    def test_get_public_ssh_keys_without_imds(self):
        self.m_fetch.return_value = dict()
        sys_cfg = {"datasource": {"Azure": {"apply_network_config": True}}}
        data = {
            "ovfcontent": construct_ovf_env(),
            "sys_cfg": sys_cfg,
        }
        dsrc = self._get_ds(data)
        dsaz.get_metadata_from_fabric.return_value = ["key2"]
        dsrc.get_data()
        dsrc.setup(True)
        ssh_keys = dsrc.get_public_ssh_keys()
        self.assertEqual(ssh_keys, ["key2"])

    def test_hostname_from_imds(self):
        sys_cfg = {"datasource": {"Azure": {"apply_network_config": True}}}
        data = {
            "ovfcontent": construct_ovf_env(),
            "sys_cfg": sys_cfg,
        }
        imds_data_with_os_profile = copy.deepcopy(NETWORK_METADATA)
        imds_data_with_os_profile["compute"]["osProfile"] = dict(
            adminUsername="username1",
            computerName="hostname1",
            disablePasswordAuthentication="true",
        )
        self.m_fetch.return_value = imds_data_with_os_profile
        dsrc = self._get_ds(data)
        dsrc.get_data()
        self.assertEqual(dsrc.metadata["local-hostname"], "hostname1")

    def test_username_from_imds(self):
        sys_cfg = {"datasource": {"Azure": {"apply_network_config": True}}}
        data = {
            "ovfcontent": construct_ovf_env(),
            "sys_cfg": sys_cfg,
        }
        imds_data_with_os_profile = copy.deepcopy(NETWORK_METADATA)
        imds_data_with_os_profile["compute"]["osProfile"] = dict(
            adminUsername="username1",
            computerName="hostname1",
            disablePasswordAuthentication="true",
        )
        self.m_fetch.return_value = imds_data_with_os_profile
        dsrc = self._get_ds(data)
        dsrc.get_data()
        self.assertEqual(
            dsrc.cfg["system_info"]["default_user"]["name"], "username1"
        )

    def test_disable_password_from_imds(self):
        sys_cfg = {"datasource": {"Azure": {"apply_network_config": True}}}
        data = {
            "ovfcontent": construct_ovf_env(),
            "sys_cfg": sys_cfg,
        }
        imds_data_with_os_profile = copy.deepcopy(NETWORK_METADATA)
        imds_data_with_os_profile["compute"]["osProfile"] = dict(
            adminUsername="username1",
            computerName="hostname1",
            disablePasswordAuthentication="true",
        )
        self.m_fetch.return_value = imds_data_with_os_profile
        dsrc = self._get_ds(data)
        dsrc.get_data()
        self.assertTrue(dsrc.metadata["disable_password"])

    def test_userdata_from_imds(self):
        sys_cfg = {"datasource": {"Azure": {"apply_network_config": True}}}
        data = {
            "ovfcontent": construct_ovf_env(),
            "sys_cfg": sys_cfg,
        }
        userdata = "userdataImds"
        imds_data = copy.deepcopy(NETWORK_METADATA)
        imds_data["compute"]["osProfile"] = dict(
            adminUsername="username1",
            computerName="hostname1",
            disablePasswordAuthentication="true",
        )
        imds_data["compute"]["userData"] = b64e(userdata)
        self.m_fetch.return_value = imds_data
        dsrc = self._get_ds(data)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEqual(dsrc.userdata_raw, userdata.encode("utf-8"))

    def test_userdata_from_imds_with_customdata_from_OVF(self):
        userdataOVF = "userdataOVF"
        sys_cfg = {"datasource": {"Azure": {"apply_network_config": True}}}
        data = {
            "ovfcontent": construct_ovf_env(custom_data=userdataOVF),
            "sys_cfg": sys_cfg,
        }

        userdataImds = "userdataImds"
        imds_data = copy.deepcopy(NETWORK_METADATA)
        imds_data["compute"]["osProfile"] = dict(
            adminUsername="username1",
            computerName="hostname1",
            disablePasswordAuthentication="true",
        )
        imds_data["compute"]["userData"] = b64e(userdataImds)
        self.m_fetch.return_value = imds_data
        dsrc = self._get_ds(data)
        ret = dsrc.get_data()
        self.assertTrue(ret)
        self.assertEqual(dsrc.userdata_raw, userdataOVF.encode("utf-8"))


class TestLoadAzureDsDir(CiTestCase):
    """Tests for load_azure_ds_dir."""

    def setUp(self):
        self.source_dir = self.tmp_dir()
        super(TestLoadAzureDsDir, self).setUp()

    def test_missing_ovf_env_xml_raises_non_azure_datasource_error(self):
        """load_azure_ds_dir raises an error When ovf-env.xml doesn't exit."""
        with self.assertRaises(dsaz.NonAzureDataSource) as context_manager:
            dsaz.load_azure_ds_dir(self.source_dir)
        self.assertEqual(
            "No ovf-env file found", str(context_manager.exception)
        )

    def test_wb_invalid_ovf_env_xml_calls_read_azure_ovf(self):
        """load_azure_ds_dir calls read_azure_ovf to parse the xml."""
        ovf_path = os.path.join(self.source_dir, "ovf-env.xml")
        with open(ovf_path, "wb") as stream:
            stream.write(b"invalid xml")
        with self.assertRaises(
            errors.ReportableErrorOvfParsingException
        ) as context_manager:
            dsaz.load_azure_ds_dir(self.source_dir)
        self.assertEqual(
            "error parsing ovf-env.xml: syntax error: line 1, column 0",
            context_manager.exception.reason,
        )


class TestReadAzureOvf(CiTestCase):
    def test_invalid_xml_raises_non_azure_ds(self):
        invalid_xml = "<foo>" + construct_ovf_env()
        self.assertRaises(
            errors.ReportableErrorOvfParsingException,
            dsaz.read_azure_ovf,
            invalid_xml,
        )

    def test_load_with_pubkeys(self):
        public_keys = [{"fingerprint": "fp1", "path": "path1", "value": ""}]
        content = construct_ovf_env(public_keys=public_keys)
        (_md, _ud, cfg) = dsaz.read_azure_ovf(content)
        for pk in public_keys:
            self.assertIn(pk, cfg["_pubkeys"])


class TestCanDevBeReformatted(CiTestCase):
    with_logs = True
    warning_file = "dataloss_warning_readme.txt"

    def _domock(self, mockpath, sattr=None):
        patcher = mock.patch(mockpath)
        setattr(self, sattr, patcher.start())
        self.addCleanup(patcher.stop)

    def patchup(self, devs):
        bypath = {}
        for path, data in devs.items():
            bypath[path] = data
            if "realpath" in data:
                bypath[data["realpath"]] = data
            for ppath, pdata in data.get("partitions", {}).items():
                bypath[ppath] = pdata
                if "realpath" in data:
                    bypath[pdata["realpath"]] = pdata

        def realpath(d):
            return bypath[d].get("realpath", d)

        def partitions_on_device(devpath):
            parts = bypath.get(devpath, {}).get("partitions", {})
            ret = []
            for path, data in parts.items():
                ret.append((data.get("num"), realpath(path)))
            # return sorted by partition number
            return sorted(ret, key=lambda d: d[0])

        def has_ntfs_fs(device):
            return bypath.get(device, {}).get("fs") == "ntfs"

        p = MOCKPATH
        self._domock(p + "_partitions_on_device", "m_partitions_on_device")
        self._domock(p + "_has_ntfs_filesystem", "m_has_ntfs_filesystem")
        self._domock(p + "os.path.realpath", "m_realpath")
        self._domock(p + "os.path.exists", "m_exists")
        self._domock(p + "util.SeLinuxGuard", "m_selguard")

        self.m_exists.side_effect = lambda p: p in bypath
        self.m_realpath.side_effect = realpath
        self.m_has_ntfs_filesystem.side_effect = has_ntfs_fs
        self.m_partitions_on_device.side_effect = partitions_on_device
        self.m_selguard.__enter__ = mock.Mock(return_value=False)
        self.m_selguard.__exit__ = mock.Mock()

        return bypath

    M_PATH = "cloudinit.util."

    @mock.patch(M_PATH + "subp.subp")
    def test_ntfs_mount_logs(self, m_subp):
        """can_dev_be_reformatted does not log errors in case of
        unknown filesystem 'ntfs'."""
        self.patchup(
            {
                "/dev/sda": {
                    "partitions": {
                        "/dev/fake0": {"num": 1, "fs": "ntfs", "files": []}
                    }
                }
            }
        )

        log_msg = "Failed to mount device"

        m_subp.side_effect = subp.ProcessExecutionError(
            "", "unknown filesystem type 'ntfs'"
        )

        dsaz.can_dev_be_reformatted("/dev/sda", preserve_ntfs=False)
        self.assertNotIn(log_msg, self.logs.getvalue())

    def _domock_mount_cb(self, bypath):
        def mount_cb(
            device, callback, mtype, update_env_for_mount, log_error=False
        ):
            self.assertEqual("ntfs", mtype)
            self.assertEqual("C", update_env_for_mount.get("LANG"))
            p = self.tmp_dir()
            for f in bypath.get(device).get("files", []):
                write_file(os.path.join(p, f), content=f)
            return callback(p)

        p = MOCKPATH
        self._domock(p + "util.mount_cb", "m_mount_cb")
        self.m_mount_cb.side_effect = mount_cb

    def test_three_partitions_is_false(self):
        """A disk with 3 partitions can not be formatted."""
        bypath = self.patchup(
            {
                "/dev/sda": {
                    "partitions": {
                        "/dev/sda1": {"num": 1},
                        "/dev/sda2": {"num": 2},
                        "/dev/sda3": {"num": 3},
                    }
                }
            }
        )
        self._domock_mount_cb(bypath)
        value, msg = dsaz.can_dev_be_reformatted(
            "/dev/sda", preserve_ntfs=False
        )
        self.assertFalse(value)
        self.assertIn("3 or more", msg.lower())

    def test_no_partitions_is_false(self):
        """A disk with no partitions can not be formatted."""
        bypath = self.patchup({"/dev/sda": {}})
        self._domock_mount_cb(bypath)
        value, msg = dsaz.can_dev_be_reformatted(
            "/dev/sda", preserve_ntfs=False
        )
        self.assertFalse(value)
        self.assertIn("not partitioned", msg.lower())

    def test_two_partitions_not_ntfs_false(self):
        """2 partitions and 2nd not ntfs can not be formatted."""
        bypath = self.patchup(
            {
                "/dev/sda": {
                    "partitions": {
                        "/dev/sda1": {"num": 1},
                        "/dev/sda2": {"num": 2, "fs": "ext4", "files": []},
                    }
                }
            }
        )
        self._domock_mount_cb(bypath)
        value, msg = dsaz.can_dev_be_reformatted(
            "/dev/sda", preserve_ntfs=False
        )
        self.assertFalse(value)
        self.assertIn("not ntfs", msg.lower())

    def test_two_partitions_ntfs_populated_false(self):
        """2 partitions and populated ntfs fs on 2nd can not be formatted."""
        bypath = self.patchup(
            {
                "/dev/sda": {
                    "partitions": {
                        "/dev/sda1": {"num": 1},
                        "/dev/sda2": {
                            "num": 2,
                            "fs": "ntfs",
                            "files": ["secret.txt"],
                        },
                    }
                }
            }
        )
        self._domock_mount_cb(bypath)
        value, msg = dsaz.can_dev_be_reformatted(
            "/dev/sda", preserve_ntfs=False
        )
        self.assertFalse(value)
        self.assertIn("files on it", msg.lower())

    def test_two_partitions_ntfs_empty_is_true(self):
        """2 partitions and empty ntfs fs on 2nd can be formatted."""
        bypath = self.patchup(
            {
                "/dev/sda": {
                    "partitions": {
                        "/dev/sda1": {"num": 1},
                        "/dev/sda2": {"num": 2, "fs": "ntfs", "files": []},
                    }
                }
            }
        )
        self._domock_mount_cb(bypath)
        value, msg = dsaz.can_dev_be_reformatted(
            "/dev/sda", preserve_ntfs=False
        )
        self.assertTrue(value)
        self.assertIn("safe for", msg.lower())

    def test_one_partition_not_ntfs_false(self):
        """1 partition witih fs other than ntfs can not be formatted."""
        bypath = self.patchup(
            {
                "/dev/sda": {
                    "partitions": {
                        "/dev/sda1": {"num": 1, "fs": "zfs"},
                    }
                }
            }
        )
        self._domock_mount_cb(bypath)
        value, msg = dsaz.can_dev_be_reformatted(
            "/dev/sda", preserve_ntfs=False
        )
        self.assertFalse(value)
        self.assertIn("not ntfs", msg.lower())

    def test_one_partition_ntfs_populated_false(self):
        """1 mountable ntfs partition with many files can not be formatted."""
        bypath = self.patchup(
            {
                "/dev/sda": {
                    "partitions": {
                        "/dev/sda1": {
                            "num": 1,
                            "fs": "ntfs",
                            "files": ["file1.txt", "file2.exe"],
                        },
                    }
                }
            }
        )
        self._domock_mount_cb(bypath)
        with mock.patch.object(dsaz.LOG, "warning") as warning:
            value, msg = dsaz.can_dev_be_reformatted(
                "/dev/sda", preserve_ntfs=False
            )
            wmsg = warning.call_args[0][0]
            self.assertIn(
                "looks like you're using NTFS on the ephemeral disk", wmsg
            )
            self.assertFalse(value)
            self.assertIn("files on it", msg.lower())

    def test_one_partition_ntfs_empty_is_true(self):
        """1 mountable ntfs partition and no files can be formatted."""
        bypath = self.patchup(
            {
                "/dev/sda": {
                    "partitions": {
                        "/dev/sda1": {"num": 1, "fs": "ntfs", "files": []}
                    }
                }
            }
        )
        self._domock_mount_cb(bypath)
        value, msg = dsaz.can_dev_be_reformatted(
            "/dev/sda", preserve_ntfs=False
        )
        self.assertTrue(value)
        self.assertIn("safe for", msg.lower())

    def test_one_partition_ntfs_empty_with_dataloss_file_is_true(self):
        """1 mountable ntfs partition and only warn file can be formatted."""
        bypath = self.patchup(
            {
                "/dev/sda": {
                    "partitions": {
                        "/dev/sda1": {
                            "num": 1,
                            "fs": "ntfs",
                            "files": ["dataloss_warning_readme.txt"],
                        }
                    }
                }
            }
        )
        self._domock_mount_cb(bypath)
        value, msg = dsaz.can_dev_be_reformatted(
            "/dev/sda", preserve_ntfs=False
        )
        self.assertTrue(value)
        self.assertIn("safe for", msg.lower())

    def test_one_partition_ntfs_empty_with_svi_file_is_true(self):
        """1 mountable ntfs partition and only warn file can be formatted."""
        bypath = self.patchup(
            {
                "/dev/sda": {
                    "partitions": {
                        "/dev/sda1": {
                            "num": 1,
                            "fs": "ntfs",
                            "files": ["System Volume Information"],
                        }
                    }
                }
            }
        )
        self._domock_mount_cb(bypath)
        value, msg = dsaz.can_dev_be_reformatted(
            "/dev/sda", preserve_ntfs=False
        )
        self.assertTrue(value)
        self.assertIn("safe for", msg.lower())

    def test_one_partition_through_realpath_is_true(self):
        """A symlink to a device with 1 ntfs partition can be formatted."""
        epath = "/dev/disk/cloud/azure_resource"
        bypath = self.patchup(
            {
                epath: {
                    "realpath": "/dev/sdb",
                    "partitions": {
                        epath
                        + "-part1": {
                            "num": 1,
                            "fs": "ntfs",
                            "files": [self.warning_file],
                            "realpath": "/dev/sdb1",
                        }
                    },
                }
            }
        )
        self._domock_mount_cb(bypath)
        value, msg = dsaz.can_dev_be_reformatted(epath, preserve_ntfs=False)
        self.assertTrue(value)
        self.assertIn("safe for", msg.lower())

    def test_three_partition_through_realpath_is_false(self):
        """A symlink to a device with 3 partitions can not be formatted."""
        epath = "/dev/disk/cloud/azure_resource"
        bypath = self.patchup(
            {
                epath: {
                    "realpath": "/dev/sdb",
                    "partitions": {
                        epath
                        + "-part1": {
                            "num": 1,
                            "fs": "ntfs",
                            "files": [self.warning_file],
                            "realpath": "/dev/sdb1",
                        },
                        epath
                        + "-part2": {
                            "num": 2,
                            "fs": "ext3",
                            "realpath": "/dev/sdb2",
                        },
                        epath
                        + "-part3": {
                            "num": 3,
                            "fs": "ext",
                            "realpath": "/dev/sdb3",
                        },
                    },
                }
            }
        )
        self._domock_mount_cb(bypath)
        value, msg = dsaz.can_dev_be_reformatted(epath, preserve_ntfs=False)
        self.assertFalse(value)
        self.assertIn("3 or more", msg.lower())

    def test_ntfs_mount_errors_true(self):
        """can_dev_be_reformatted does not fail if NTFS is unknown fstype."""
        bypath = self.patchup(
            {
                "/dev/sda": {
                    "partitions": {
                        "/dev/sda1": {"num": 1, "fs": "ntfs", "files": []}
                    }
                }
            }
        )
        self._domock_mount_cb(bypath)

        error_msgs = [
            "Stderr: mount: unknown filesystem type 'ntfs'",  # RHEL
            "Stderr: mount: /dev/sdb1: unknown filesystem type 'ntfs'",  # SLES
        ]

        for err_msg in error_msgs:
            self.m_mount_cb.side_effect = MountFailedError(
                "Failed mounting %s to %s due to: \nUnexpected.\n%s"
                % ("/dev/sda", "/fake-tmp/dir", err_msg)
            )

            value, msg = dsaz.can_dev_be_reformatted(
                "/dev/sda", preserve_ntfs=False
            )
            self.assertTrue(value)
            self.assertIn("cannot mount NTFS, assuming", msg)

    def test_never_destroy_ntfs_config_false(self):
        """Normally formattable situation with never_destroy_ntfs set."""
        bypath = self.patchup(
            {
                "/dev/sda": {
                    "partitions": {
                        "/dev/sda1": {
                            "num": 1,
                            "fs": "ntfs",
                            "files": ["dataloss_warning_readme.txt"],
                        }
                    }
                }
            }
        )
        self._domock_mount_cb(bypath)
        value, msg = dsaz.can_dev_be_reformatted(
            "/dev/sda", preserve_ntfs=True
        )
        self.assertFalse(value)
        self.assertIn(
            "config says to never destroy NTFS "
            "(datasource.Azure.never_destroy_ntfs)",
            msg,
        )


class TestClearCachedData(CiTestCase):
    def test_clear_cached_attrs_clears_imds(self):
        """All class attributes are reset to defaults, including imds data."""
        tmp = self.tmp_dir()
        paths = helpers.Paths({"cloud_dir": tmp, "run_dir": tmp})
        dsrc = dsaz.DataSourceAzure({}, distro=mock.Mock(), paths=paths)
        clean_values = [dsrc.metadata, dsrc.userdata, dsrc._metadata_imds]
        dsrc.metadata = "md"
        dsrc.userdata = "ud"
        dsrc._metadata_imds = "imds"
        dsrc._dirty_cache = True
        dsrc.clear_cached_attrs()
        self.assertEqual(
            [dsrc.metadata, dsrc.userdata, dsrc._metadata_imds], clean_values
        )


class TestAzureNetExists(CiTestCase):
    def test_azure_net_must_exist_for_legacy_objpkl(self):
        """DataSourceAzureNet must exist for old obj.pkl files
        that reference it."""
        self.assertTrue(hasattr(dsaz, "DataSourceAzureNet"))


class TestPreprovisioningReadAzureOvfFlag(CiTestCase):
    def test_read_azure_ovf_with_true_flag(self):
        """The read_azure_ovf method should set the PreprovisionedVM
        cfg flag if the proper setting is present."""
        content = construct_ovf_env(preprovisioned_vm=True)
        ret = dsaz.read_azure_ovf(content)
        cfg = ret[2]
        self.assertTrue(cfg["PreprovisionedVm"])

    def test_read_azure_ovf_with_false_flag(self):
        """The read_azure_ovf method should set the PreprovisionedVM
        cfg flag to false if the proper setting is false."""
        content = construct_ovf_env(preprovisioned_vm=False)
        ret = dsaz.read_azure_ovf(content)
        cfg = ret[2]
        self.assertFalse(cfg["PreprovisionedVm"])

    def test_read_azure_ovf_without_flag(self):
        """The read_azure_ovf method should not set the
        PreprovisionedVM cfg flag."""
        content = construct_ovf_env()
        ret = dsaz.read_azure_ovf(content)
        cfg = ret[2]
        self.assertFalse(cfg["PreprovisionedVm"])
        self.assertEqual(None, cfg["PreprovisionedVMType"])

    def test_read_azure_ovf_with_running_type(self):
        """The read_azure_ovf method should set PreprovisionedVMType
        cfg flag to Running."""
        content = construct_ovf_env(
            preprovisioned_vm=True, preprovisioned_vm_type="Running"
        )
        ret = dsaz.read_azure_ovf(content)
        cfg = ret[2]
        self.assertTrue(cfg["PreprovisionedVm"])
        self.assertEqual("Running", cfg["PreprovisionedVMType"])

    def test_read_azure_ovf_with_savable_type(self):
        """The read_azure_ovf method should set PreprovisionedVMType
        cfg flag to Savable."""
        content = construct_ovf_env(
            preprovisioned_vm=True, preprovisioned_vm_type="Savable"
        )
        ret = dsaz.read_azure_ovf(content)
        cfg = ret[2]
        self.assertTrue(cfg["PreprovisionedVm"])
        self.assertEqual("Savable", cfg["PreprovisionedVMType"])

    def test_read_azure_ovf_with_proxy_guest_agent_true(self):
        """The read_azure_ovf method should set ProvisionGuestProxyAgent
        cfg flag to True."""
        content = construct_ovf_env(provision_guest_proxy_agent=True)
        ret = dsaz.read_azure_ovf(content)
        cfg = ret[2]
        assert cfg["ProvisionGuestProxyAgent"] is True

    def test_read_azure_ovf_with_proxy_guest_agent_false(self):
        """The read_azure_ovf method should set ProvisionGuestProxyAgent
        cfg flag to False."""
        content = construct_ovf_env(provision_guest_proxy_agent=False)
        ret = dsaz.read_azure_ovf(content)
        cfg = ret[2]
        assert cfg["ProvisionGuestProxyAgent"] is False


@pytest.mark.parametrize(
    "ovf_cfg,imds_md,pps_type",
    [
        (
            {"PreprovisionedVm": False, "PreprovisionedVMType": None},
            {},
            dsaz.PPSType.NONE,
        ),
        (
            {"PreprovisionedVm": True, "PreprovisionedVMType": "Running"},
            {},
            dsaz.PPSType.RUNNING,
        ),
        (
            {"PreprovisionedVm": True, "PreprovisionedVMType": "Savable"},
            {},
            dsaz.PPSType.SAVABLE,
        ),
        (
            {"PreprovisionedVm": True},
            {},
            dsaz.PPSType.RUNNING,
        ),
        (
            {},
            {"extended": {"compute": {"ppsType": "None"}}},
            dsaz.PPSType.NONE,
        ),
        (
            {},
            {"extended": {"compute": {"ppsType": "Running"}}},
            dsaz.PPSType.RUNNING,
        ),
        (
            {},
            {"extended": {"compute": {"ppsType": "Savable"}}},
            dsaz.PPSType.SAVABLE,
        ),
        (
            {"PreprovisionedVm": False, "PreprovisionedVMType": None},
            {"extended": {"compute": {"ppsType": "None"}}},
            dsaz.PPSType.NONE,
        ),
        (
            {"PreprovisionedVm": True, "PreprovisionedVMType": "Running"},
            {"extended": {"compute": {"ppsType": "Running"}}},
            dsaz.PPSType.RUNNING,
        ),
        (
            {"PreprovisionedVm": True, "PreprovisionedVMType": "Savable"},
            {"extended": {"compute": {"ppsType": "Savable"}}},
            dsaz.PPSType.SAVABLE,
        ),
        (
            {"PreprovisionedVm": True},
            {"extended": {"compute": {"ppsType": "Running"}}},
            dsaz.PPSType.RUNNING,
        ),
    ],
)
class TestDeterminePPSTypeScenarios:
    @mock.patch("os.path.isfile", return_value=False)
    def test_determine_pps_without_reprovision_marker(
        self, is_file, azure_ds, ovf_cfg, imds_md, pps_type
    ):
        assert azure_ds._determine_pps_type(ovf_cfg, imds_md) == pps_type

    @mock.patch("os.path.isfile", return_value=True)
    def test_determine_pps_with_reprovision_marker(
        self, is_file, azure_ds, ovf_cfg, imds_md, pps_type
    ):
        assert (
            azure_ds._determine_pps_type(ovf_cfg, imds_md)
            == dsaz.PPSType.UNKNOWN
        )
        assert is_file.mock_calls == [
            mock.call(azure_ds._reported_ready_marker_file)
        ]


class TestPreprovisioningHotAttachNics(CiTestCase):
    def setUp(self):
        super(TestPreprovisioningHotAttachNics, self).setUp()
        self.tmp = self.tmp_dir()
        self.waagent_d = self.tmp_path("/var/lib/waagent", self.tmp)
        self.paths = helpers.Paths({"cloud_dir": self.tmp})
        dsaz.BUILTIN_DS_CONFIG["data_dir"] = self.waagent_d
        self.paths = helpers.Paths({"cloud_dir": self.tmp})

    @mock.patch(MOCKPATH + "util.write_file", autospec=True)
    @mock.patch(MOCKPATH + "DataSourceAzure._report_ready")
    @mock.patch(
        MOCKPATH + "DataSourceAzure._wait_for_hot_attached_primary_nic"
    )
    @mock.patch(MOCKPATH + "DataSourceAzure._wait_for_nic_detach")
    def test_detect_nic_attach_reports_ready_and_waits_for_detach(
        self,
        m_detach,
        m_wait_for_hot_attached_primary_nic,
        m_report_ready,
        m_writefile,
    ):
        """Report ready first and then wait for nic detach"""
        dsa = dsaz.DataSourceAzure({}, distro=None, paths=self.paths)
        dsa._wait_for_pps_savable_reuse()
        self.assertEqual(1, m_report_ready.call_count)
        self.assertEqual(1, m_wait_for_hot_attached_primary_nic.call_count)
        self.assertEqual(1, m_detach.call_count)
        self.assertEqual(1, m_writefile.call_count)
        m_writefile.assert_called_with(
            dsa._reported_ready_marker_file, mock.ANY
        )

    @mock.patch(MOCKPATH + "util.write_file", autospec=True)
    @mock.patch(MOCKPATH + "DataSourceAzure._report_ready")
    @mock.patch(MOCKPATH + "DataSourceAzure.wait_for_link_up")
    @mock.patch("cloudinit.sources.helpers.netlink.wait_for_nic_attach_event")
    @mock.patch(MOCKPATH + "EphemeralDHCPv4", autospec=True)
    @mock.patch(MOCKPATH + "DataSourceAzure._wait_for_nic_detach")
    @mock.patch("os.path.isfile")
    def test_wait_for_nic_attach_multinic_attach(
        self,
        m_isfile,
        m_detach,
        m_dhcpv4,
        m_attach,
        m_link_up,
        m_report_ready,
        m_writefile,
    ):
        """Wait for nic attach if we do not have a fallback interface.
        Skip waiting for additional nics after we have found primary"""
        distro = mock.MagicMock()
        distro.get_tmp_exec_path = self.tmp_dir
        dsa = dsaz.DataSourceAzure({}, distro=distro, paths=self.paths)
        lease = {
            "interface": "eth9",
            "fixed-address": "192.168.2.9",
            "routers": "192.168.2.1",
            "subnet-mask": "255.255.255.0",
            "unknown-245": "624c3620",
        }

        # Simulate two NICs by adding the same one twice.
        m_isfile.return_value = True
        m_attach.side_effect = [
            "eth0",
            "eth1",
        ]
        dhcp_ctx_primary = mock.MagicMock(lease=lease)
        dhcp_ctx_primary.obtain_lease.return_value = lease
        dhcp_ctx_primary._ephipv4 = ephemeral.EphemeralIPv4Network(
            distro="ubuntu",
            interface="eth0",
            ip="10.0.0.4",
            prefix_or_mask="32",
            broadcast="255.255.255.255",
            interface_addrs_before_dhcp=example_netdev,
            router="10.0.0.1",
            static_routes=[
                ("0.0.0.0/0", "10.0.0.1"),
                ("168.63.129.16/32", "10.0.0.1"),
                ("169.254.169.254/32", "10.0.0.1"),
            ],
        )
        m_dhcpv4.side_effect = [dhcp_ctx_primary]

        dsa._wait_for_pps_savable_reuse()

        self.assertEqual(1, m_detach.call_count)
        # only wait for primary nic
        self.assertEqual(1, m_attach.call_count)
        # DHCP and network metadata calls will only happen on the primary NIC.
        self.assertEqual(1, m_dhcpv4.call_count)
        # no call to bring link up on secondary nic
        self.assertEqual(1, m_link_up.call_count)

        # reset mock to test again with primary nic being eth1
        dhcp_ctx_primary.interface = "eth1"
        dhcp_ctx_secondary = mock.MagicMock(lease=lease)
        dhcp_ctx_secondary.obtain_lease.return_value = lease
        dhcp_ctx_secondary._ephipv4 = ephemeral.EphemeralIPv4Network(
            distro="ubuntu",
            interface="eth0",
            ip="10.0.0.4",
            prefix_or_mask="32",
            broadcast="255.255.255.255",
            interface_addrs_before_dhcp=example_netdev,
            router="10.0.0.1",
            static_routes=None,
        )
        m_detach.reset_mock()
        m_attach.reset_mock()
        m_dhcpv4.reset_mock()
        m_dhcpv4.side_effect = [dhcp_ctx_secondary, dhcp_ctx_primary]
        m_link_up.reset_mock()
        m_attach.side_effect = ["eth0", "eth1"]
        dsa = dsaz.DataSourceAzure({}, distro=distro, paths=self.paths)
        dsa._wait_for_pps_savable_reuse()
        self.assertEqual(1, m_detach.call_count)
        self.assertEqual(2, m_attach.call_count)
        self.assertEqual(2, m_dhcpv4.call_count)
        self.assertEqual(2, m_link_up.call_count)

    @mock.patch("cloudinit.distros.networking.LinuxNetworking.try_set_link_up")
    def test_wait_for_link_up_returns_if_already_up(self, m_is_link_up):
        """Waiting for link to be up should return immediately if the link is
        already up."""

        distro_cls = distros.fetch("ubuntu")
        distro = distro_cls("ubuntu", {}, self.paths)
        dsa = dsaz.DataSourceAzure({}, distro=distro, paths=self.paths)
        m_is_link_up.return_value = True

        dsa.wait_for_link_up("eth0")
        self.assertEqual(1, m_is_link_up.call_count)

    @mock.patch("cloudinit.distros.networking.LinuxNetworking.try_set_link_up")
    @mock.patch(MOCKPATH + "sleep")
    def test_wait_for_link_up_checks_link_after_sleep(
        self, m_sleep, m_try_set_link_up
    ):
        """Waiting for link to be up should return immediately if the link is
        already up."""

        distro_cls = distros.fetch("ubuntu")
        distro = distro_cls("ubuntu", {}, self.paths)
        dsa = dsaz.DataSourceAzure({}, distro=distro, paths=self.paths)
        m_try_set_link_up.return_value = False

        dsa.wait_for_link_up("eth0")

        self.assertEqual(100, m_try_set_link_up.call_count)
        self.assertEqual(99 * [mock.call(0.1)], m_sleep.mock_calls)

    @mock.patch(
        "cloudinit.sources.helpers.netlink.create_bound_netlink_socket"
    )
    def test_wait_for_all_nics_ready_raises_if_socket_fails(self, m_socket):
        """Waiting for all nics should raise exception if netlink socket
        creation fails."""

        m_socket.side_effect = netlink.NetlinkCreateSocketError
        distro_cls = distros.fetch("ubuntu")
        distro = distro_cls("ubuntu", {}, self.paths)
        dsa = dsaz.DataSourceAzure({}, distro=distro, paths=self.paths)

        self.assertRaises(
            netlink.NetlinkCreateSocketError, dsa._wait_for_pps_savable_reuse
        )


@mock.patch("cloudinit.net.find_fallback_nic", return_value="eth9")
@mock.patch(MOCKPATH + "EphemeralDHCPv4")
@mock.patch(
    "cloudinit.sources.helpers.netlink.wait_for_media_disconnect_connect"
)
@mock.patch(MOCKPATH + "imds.fetch_reprovision_data")
class TestPreprovisioningPollIMDS(CiTestCase):
    def setUp(self):
        super(TestPreprovisioningPollIMDS, self).setUp()
        self.tmp = self.tmp_dir()
        self.waagent_d = self.tmp_path("/var/lib/waagent", self.tmp)
        self.paths = helpers.Paths({"cloud_dir": self.tmp})
        dsaz.BUILTIN_DS_CONFIG["data_dir"] = self.waagent_d

    @mock.patch("time.sleep", mock.MagicMock())
    def test_poll_imds_re_dhcp_on_timeout(
        self,
        m_fetch_reprovisiondata,
        m_media_switch,
        m_dhcp,
        m_fallback,
    ):
        """The poll_imds will retry DHCP on IMDS timeout."""
        m_fetch_reprovisiondata.side_effect = [
            url_helper.UrlError(requests.Timeout("Fake connection timeout")),
            b"ovf data",
        ]
        lease = {
            "interface": "eth9",
            "fixed-address": "192.168.2.9",
            "routers": "192.168.2.1",
            "subnet-mask": "255.255.255.0",
            "unknown-245": "624c3620",
        }
        m_dhcp.obtain_lease.return_value = [lease]
        m_media_switch.return_value = None
        dhcp_ctx = mock.MagicMock(lease=lease)
        dhcp_ctx.obtain_lease.return_value = lease
        dhcp_ctx.iface = lease["interface"]

        dsa = dsaz.DataSourceAzure({}, distro=mock.Mock(), paths=self.paths)
        dsa._ephemeral_dhcp_ctx = dhcp_ctx
        dsa._poll_imds()

        self.assertEqual(1, m_dhcp.call_count, "Expected 1 DHCP calls")
        assert m_fetch_reprovisiondata.call_count == 2

    @mock.patch("os.path.isfile")
    def test_poll_imds_skips_dhcp_if_ctx_present(
        self,
        m_isfile,
        m_fetch_reprovisiondata,
        m_media_switch,
        m_dhcp,
        m_fallback,
    ):
        """The poll_imds function should reuse the dhcp ctx if it is already
        present. This happens when we wait for nic to be hot-attached before
        polling for reprovisiondata. Note that if this ctx is set when
        _poll_imds is called, then it is not expected to be waiting for
        media_disconnect_connect either."""
        m_isfile.return_value = True
        dsa = dsaz.DataSourceAzure({}, distro=None, paths=self.paths)
        dsa._ephemeral_dhcp_ctx = mock.Mock(lease={})
        dsa._poll_imds()
        self.assertEqual(0, m_dhcp.call_count)
        self.assertEqual(0, m_media_switch.call_count)

    @mock.patch("os.path.isfile")
    def test_poll_imds_does_dhcp_on_retries_if_ctx_present(
        self,
        m_isfile,
        m_fetch_reprovisiondata,
        m_media_switch,
        m_dhcp,
        m_fallback,
    ):
        """The poll_imds function should reuse the dhcp ctx if it is already
        present. This happens when we wait for nic to be hot-attached before
        polling for reprovisiondata. Note that if this ctx is set when
        _poll_imds is called, then it is not expected to be waiting for
        media_disconnect_connect either."""
        m_fetch_reprovisiondata.side_effect = [
            url_helper.UrlError(
                requests.ConnectionError(
                    "Failed to establish a new connection: "
                    "[Errno 101] Network is unreachable"
                )
            ),
            b"ovf data",
        ]
        m_isfile.return_value = True
        distro = mock.MagicMock()
        distro.get_tmp_exec_path = self.tmp_dir
        dsa = dsaz.DataSourceAzure({}, distro=distro, paths=self.paths)
        with mock.patch.object(dsa, "_ephemeral_dhcp_ctx") as m_dhcp_ctx:
            m_dhcp_ctx.obtain_lease.return_value = "Dummy lease"
            dsa._ephemeral_dhcp_ctx = m_dhcp_ctx
            dsa._poll_imds()
            self.assertEqual(1, m_dhcp_ctx.clean_network.call_count)
        self.assertEqual(1, m_dhcp.call_count)
        self.assertEqual(0, m_media_switch.call_count)
        self.assertEqual(2, m_fetch_reprovisiondata.call_count)


class TestRemoveUbuntuNetworkConfigScripts(CiTestCase):
    with_logs = True

    def setUp(self):
        super(TestRemoveUbuntuNetworkConfigScripts, self).setUp()
        self.tmp = self.tmp_dir()

    def test_remove_network_scripts_removes_both_files_and_directories(self):
        """Any files or directories in paths are removed when present."""
        file1 = self.tmp_path("file1", dir=self.tmp)
        subdir = self.tmp_path("sub1", dir=self.tmp)
        subfile = self.tmp_path("leaf1", dir=subdir)
        write_file(file1, "file1content")
        write_file(subfile, "leafcontent")
        dsaz.maybe_remove_ubuntu_network_config_scripts(paths=[subdir, file1])

        for path in (file1, subdir, subfile):
            self.assertFalse(
                os.path.exists(path), "Found unremoved: %s" % path
            )

        expected_logs = [
            "INFO: Removing Ubuntu extended network scripts because cloud-init"
            " updates Azure network configuration on the following events:"
            " ['boot', 'boot-legacy']",
            "Recursively deleting %s" % subdir,
            "Attempting to remove %s" % file1,
        ]
        for log in expected_logs:
            self.assertIn(log, self.logs.getvalue())

    def test_remove_network_scripts_only_attempts_removal_if_path_exists(self):
        """Any files or directories absent are skipped without error."""
        dsaz.maybe_remove_ubuntu_network_config_scripts(
            paths=[
                self.tmp_path("nodirhere/", dir=self.tmp),
                self.tmp_path("notfilehere", dir=self.tmp),
            ]
        )
        self.assertNotIn("/not/a", self.logs.getvalue())  # No delete logs

    @mock.patch(MOCKPATH + "os.path.exists")
    def test_remove_network_scripts_default_removes_stock_scripts(
        self, m_exists
    ):
        """Azure's stock ubuntu image scripts and artifacts are removed."""
        # Report path absent on all to avoid delete operation
        m_exists.return_value = False
        dsaz.maybe_remove_ubuntu_network_config_scripts()
        calls = m_exists.call_args_list
        for path in dsaz.UBUNTU_EXTENDED_NETWORK_SCRIPTS:
            self.assertIn(mock.call(path), calls)


class TestIsPlatformViable:
    @pytest.mark.parametrize(
        "tag",
        [
            identity.ChassisAssetTag.AZURE_CLOUD.value,
        ],
    )
    def test_true_on_azure_chassis(
        self, azure_ds, mock_chassis_asset_tag, tag
    ):
        mock_chassis_asset_tag.return_value = tag

        assert dsaz.DataSourceAzure.ds_detect(None) is True

    def test_true_on_azure_ovf_env_in_seed_dir(
        self, azure_ds, mock_chassis_asset_tag, tmpdir
    ):
        mock_chassis_asset_tag.return_value = "notazure"

        seed_path = Path(azure_ds.seed_dir, "ovf-env.xml")
        seed_path.parent.mkdir(exist_ok=True, parents=True)
        seed_path.write_text("")

        assert dsaz.DataSourceAzure.ds_detect(seed_path.parent) is True

    def test_false_on_no_matching_azure_criteria(
        self, azure_ds, mock_chassis_asset_tag
    ):
        mock_chassis_asset_tag.return_value = None

        seed_path = Path(azure_ds.seed_dir, "ovf-env.xml")
        seed_path.parent.mkdir(exist_ok=True, parents=True)
        paths = helpers.Paths(
            {"cloud_dir": "/tmp/", "run_dir": "/tmp/", "seed_dir": seed_path}
        )

        assert (
            dsaz.DataSourceAzure({}, mock.Mock(), paths).ds_detect() is False
        )


class TestRandomSeed(CiTestCase):
    """Test proper handling of random_seed"""

    def test_non_ascii_seed_is_serializable(self):
        """Pass if a random string from the Azure infrastructure which
        contains at least one non-Unicode character can be converted to/from
        JSON without alteration and without throwing an exception.
        """
        path = resourceLocation("azure/non_unicode_random_string")
        result = dsaz._get_random_seed(path)

        obj = {"seed": result}
        try:
            serialized = json_dumps(obj)
            deserialized = load_json(serialized)
        except UnicodeDecodeError:
            self.fail("Non-serializable random seed returned")

        self.assertEqual(deserialized["seed"], result)


class TestEphemeralNetworking:
    @pytest.mark.parametrize("iface", [None, "fakeEth0"])
    def test_basic_setup(
        self,
        azure_ds,
        mock_ephemeral_dhcp_v4,
        mock_sleep,
        iface,
    ):
        lease = {
            "interface": "fakeEth0",
            "unknown-245": dhcp.IscDhclient.get_ip_from_lease_value(
                "10:ff:fe:fd"
            ),
        }
        mock_ephemeral_dhcp_v4.return_value.obtain_lease.side_effect = [lease]

        azure_ds._setup_ephemeral_networking(iface=iface)

        assert mock_ephemeral_dhcp_v4.mock_calls == [
            mock.call(
                azure_ds.distro,
                iface=iface,
                dhcp_log_func=dsaz.dhcp_log_cb,
            ),
            mock.call().obtain_lease(),
        ]
        assert mock_sleep.mock_calls == []
        assert azure_ds._wireserver_endpoint == "16.255.254.253"
        assert azure_ds._ephemeral_dhcp_ctx.iface == lease["interface"]

    @pytest.mark.parametrize("iface", [None, "fakeEth0"])
    def test_basic_setup_without_wireserver_opt(
        self,
        azure_ds,
        mock_ephemeral_dhcp_v4,
        mock_sleep,
        iface,
    ):
        lease = {
            "interface": "fakeEth0",
        }
        mock_ephemeral_dhcp_v4.return_value.obtain_lease.side_effect = [lease]

        azure_ds._setup_ephemeral_networking(iface=iface)

        assert mock_ephemeral_dhcp_v4.mock_calls == [
            mock.call(
                azure_ds.distro,
                iface=iface,
                dhcp_log_func=dsaz.dhcp_log_cb,
            ),
            mock.call().obtain_lease(),
        ]
        assert mock_sleep.mock_calls == []
        assert azure_ds._wireserver_endpoint == "168.63.129.16"
        assert azure_ds._ephemeral_dhcp_ctx.iface == lease["interface"]

    def test_no_retry_missing_dhclient_error(
        self,
        azure_ds,
        mock_ephemeral_dhcp_v4,
        mock_sleep,
    ):
        mock_ephemeral_dhcp_v4.return_value.obtain_lease.side_effect = [
            dhcp.NoDHCPLeaseMissingDhclientError
        ]

        with pytest.raises(dhcp.NoDHCPLeaseMissingDhclientError):
            azure_ds._setup_ephemeral_networking()

        assert azure_ds._ephemeral_dhcp_ctx is None

    def test_retry_interface_error(
        self,
        azure_ds,
        mock_ephemeral_dhcp_v4,
        mock_kvp_report_failure_to_host,
        mock_sleep,
    ):
        lease = {
            "interface": "fakeEth0",
        }
        mock_ephemeral_dhcp_v4.return_value.obtain_lease.side_effect = [
            dhcp.NoDHCPLeaseInterfaceError,
            lease,
        ]

        azure_ds._setup_ephemeral_networking()

        assert mock_ephemeral_dhcp_v4.mock_calls == [
            mock.call(
                azure_ds.distro,
                iface=None,
                dhcp_log_func=dsaz.dhcp_log_cb,
            ),
            mock.call().obtain_lease(),
            mock.call().obtain_lease(),
        ]
        assert mock_sleep.mock_calls == [mock.call(1)]
        assert azure_ds._wireserver_endpoint == "168.63.129.16"
        assert azure_ds._ephemeral_dhcp_ctx.iface == "fakeEth0"

        error_reasons = [
            c[0][0].reason
            for c in mock_kvp_report_failure_to_host.call_args_list
        ]
        assert error_reasons == ["failure to find DHCP interface"]

    def test_retry_process_error(
        self,
        azure_ds,
        mock_ephemeral_dhcp_v4,
        mock_report_diagnostic_event,
        mock_sleep,
    ):
        lease = {
            "interface": "fakeEth0",
        }
        mock_ephemeral_dhcp_v4.return_value.obtain_lease.side_effect = [
            subp.ProcessExecutionError(
                cmd=["failed", "cmd"],
                stdout="test_stdout",
                stderr="test_stderr",
                exit_code=4,
            ),
            lease,
        ]

        azure_ds._setup_ephemeral_networking()

        assert mock_ephemeral_dhcp_v4.mock_calls == [
            mock.call(
                azure_ds.distro,
                iface=None,
                dhcp_log_func=dsaz.dhcp_log_cb,
            ),
            mock.call().obtain_lease(),
            mock.call().obtain_lease(),
        ]
        assert mock_sleep.mock_calls == [mock.call(1)]
        assert mock_report_diagnostic_event.mock_calls == [
            mock.call(
                "Bringing up ephemeral networking with iface=None: "
                "[('dummy0', '9e:65:d6:19:19:01', None, None), "
                "('enP3', '00:11:22:33:44:02', 'unknown_accel', '0x3'), "
                "('eth0', '00:11:22:33:44:00', 'hv_netvsc', '0x3'), "
                "('eth2', '00:11:22:33:44:01', 'unknown', '0x3'), "
                "('eth3', '00:11:22:33:44:02', "
                "'unknown_with_unknown_vf', '0x3'), "
                "('lo', '00:00:00:00:00:00', None, None)]",
                logger_func=dsaz.LOG.debug,
            ),
            mock.call(
                "Command failed: cmd=['failed', 'cmd'] "
                "stderr='test_stderr' stdout='test_stdout' exit_code=4",
                logger_func=dsaz.LOG.error,
            ),
            mock.call(
                "Obtained DHCP lease on interface 'fakeEth0' "
                "(primary=True driver='fake_driver' router='10.0.0.1' "
                "routes=[('0.0.0.0/0', '10.0.0.1'), "
                "('168.63.129.16/32', '10.0.0.1'), "
                "('169.254.169.254/32', '10.0.0.1')] "
                "lease={'interface': 'fakeEth0'} "
                "imds_routed=True wireserver_routed=True)",
                logger_func=dsaz.LOG.debug,
            ),
        ]

    @pytest.mark.parametrize(
        "error_class,error_reason",
        [
            (dhcp.NoDHCPLeaseInterfaceError, "failure to find DHCP interface"),
            (dhcp.NoDHCPLeaseError, "failure to obtain DHCP lease"),
        ],
    )
    def test_retry_sleeps(
        self,
        azure_ds,
        mock_ephemeral_dhcp_v4,
        mock_kvp_report_failure_to_host,
        mock_sleep,
        error_class,
        error_reason,
    ):
        lease = {
            "interface": "fakeEth0",
        }
        mock_ephemeral_dhcp_v4.return_value.obtain_lease.side_effect = [
            error_class()
        ] * 10 + [lease]

        azure_ds._setup_ephemeral_networking()

        assert (
            mock_ephemeral_dhcp_v4.mock_calls
            == [
                mock.call(
                    azure_ds.distro,
                    iface=None,
                    dhcp_log_func=dsaz.dhcp_log_cb,
                ),
            ]
            + [mock.call().obtain_lease()] * 11
        )
        assert mock_sleep.mock_calls == [mock.call(1)] * 10
        assert azure_ds._wireserver_endpoint == "168.63.129.16"
        assert azure_ds._ephemeral_dhcp_ctx.iface == "fakeEth0"

        error_reasons = [
            c[0][0].reason
            for c in mock_kvp_report_failure_to_host.call_args_list
        ]
        assert error_reasons == [error_reason] * 10

    @pytest.mark.parametrize(
        "error_class,error_reason",
        [
            (dhcp.NoDHCPLeaseInterfaceError, "failure to find DHCP interface"),
            (dhcp.NoDHCPLeaseError, "failure to obtain DHCP lease"),
        ],
    )
    def test_retry_times_out(
        self,
        azure_ds,
        mock_ephemeral_dhcp_v4,
        mock_kvp_report_failure_to_host,
        mock_sleep,
        mock_time,
        mock_monotonic,
        error_class,
        error_reason,
    ):
        mock_monotonic.side_effect = [
            0.0,  # start
            60.1,  # duration check for host error report
            60.11,  # loop check
            120.1,  # duration check for host error report
            120.11,  # loop check
            180.1,  # duration check for host error report
            180.11,  # loop check timeout
        ]
        mock_ephemeral_dhcp_v4.return_value.obtain_lease.side_effect = [
            error_class()
        ] * 3

        with pytest.raises(dhcp.NoDHCPLeaseError):
            azure_ds._setup_ephemeral_networking(timeout_minutes=3)

        assert (
            mock_ephemeral_dhcp_v4.return_value.mock_calls
            == [mock.call.obtain_lease()] * 3
        )
        assert mock_sleep.mock_calls == [mock.call(1)] * 2
        assert azure_ds._wireserver_endpoint == "168.63.129.16"
        assert azure_ds._ephemeral_dhcp_ctx is None

        error_reasons = [
            c[0][0].reason
            for c in mock_kvp_report_failure_to_host.call_args_list
        ]
        assert error_reasons == [error_reason] * 3


class TestCheckIfPrimary:
    @pytest.mark.parametrize(
        "static_routes",
        [
            [("168.63.129.16/32", "10.0.0.1")],
            [("169.254.169.254/32", "10.0.0.1")],
        ],
    )
    def test_primary(self, azure_ds, static_routes):
        ephipv4 = ephemeral.EphemeralIPv4Network(
            distro="ubuntu",
            interface="eth0",
            ip="10.0.0.4",
            prefix_or_mask="32",
            broadcast="255.255.255.255",
            interface_addrs_before_dhcp=example_netdev,
            router="10.0.0.1",
            static_routes=static_routes,
        )

        assert azure_ds._check_if_primary(ephipv4) is True

    def test_primary_via_wireserver_specified_in_option_245(self, azure_ds):
        ephipv4 = ephemeral.EphemeralIPv4Network(
            distro="ubuntu",
            interface="eth0",
            ip="10.0.0.4",
            prefix_or_mask="32",
            broadcast="255.255.255.255",
            interface_addrs_before_dhcp=example_netdev,
            router="10.0.0.1",
            static_routes=[("1.2.3.4/32", "10.0.0.1")],
        )
        azure_ds._wireserver_endpoint = "1.2.3.4"

        assert azure_ds._check_if_primary(ephipv4) is True

    @pytest.mark.parametrize(
        "static_routes",
        [
            [],
            [("0.0.0.0/0", "10.0.0.1")],
            [("10.10.10.10/16", "10.0.0.1")],
        ],
    )
    def test_secondary(self, azure_ds, static_routes):
        ephipv4 = ephemeral.EphemeralIPv4Network(
            distro="ubuntu",
            interface="eth0",
            ip="10.0.0.4",
            prefix_or_mask="32",
            broadcast="255.255.255.255",
            interface_addrs_before_dhcp=example_netdev,
            router="10.0.0.1",
            static_routes=static_routes,
        )
        azure_ds._wireserver_endpoint = "1.2.3.4"

        assert azure_ds._check_if_primary(ephipv4) is False


class TestInstanceId:
    def test_metadata(self, azure_ds, mock_dmi_read_dmi_data):
        azure_ds.metadata = {"instance-id": "test-id"}

        id = azure_ds.get_instance_id()

        assert id == "test-id"

    def test_fallback(self, azure_ds, mock_dmi_read_dmi_data):
        id = azure_ds.get_instance_id()

        assert id == "50109936-ef07-47fe-ac82-890c853f60d5"


class TestProvisioning:
    @pytest.fixture(autouse=True)
    def provisioning_setup(
        self,
        azure_ds,
        mock_azure_get_metadata_from_fabric,
        mock_azure_report_failure_to_fabric,
        mock_net_dhcp_maybe_perform_dhcp_discovery,
        mock_ephemeral_ipv4_network,
        mock_dmi_read_dmi_data,
        mock_get_interfaces,
        mock_get_interface_mac,
        mock_kvp_report_failure_to_host,
        mock_kvp_report_success_to_host,
        mock_netlink,
        mock_readurl,
        mock_report_dmesg_to_kvp,
        mock_subp_subp,
        mock_timestamp,
        mock_util_ensure_dir,
        mock_util_find_devs_with,
        mock_util_load_file,
        mock_util_mount_cb,
        wrapped_util_write_file,
        mock_wrapping_setup_ephemeral_networking,
        patched_data_dir_path,
        patched_reported_ready_marker_path,
    ):
        self.azure_ds = azure_ds
        self.mock_azure_get_metadata_from_fabric = (
            mock_azure_get_metadata_from_fabric
        )
        self.mock_azure_report_failure_to_fabric = (
            mock_azure_report_failure_to_fabric
        )
        self.mock_net_dhcp_maybe_perform_dhcp_discovery = (
            mock_net_dhcp_maybe_perform_dhcp_discovery
        )
        self.mock_ephemeral_ipv4_network = mock_ephemeral_ipv4_network
        self.mock_dmi_read_dmi_data = mock_dmi_read_dmi_data
        self.mock_get_interfaces = mock_get_interfaces
        self.mock_get_interface_mac = mock_get_interface_mac
        self.mock_kvp_report_failure_to_host = mock_kvp_report_failure_to_host
        self.mock_kvp_report_success_to_host = mock_kvp_report_success_to_host
        self.mock_netlink = mock_netlink
        self.mock_readurl = mock_readurl
        self.mock_report_dmesg_to_kvp = mock_report_dmesg_to_kvp
        self.mock_subp_subp = mock_subp_subp
        self.mock_timestmp = mock_timestamp
        self.mock_util_ensure_dir = mock_util_ensure_dir
        self.mock_util_find_devs_with = mock_util_find_devs_with
        self.mock_util_load_file = mock_util_load_file
        self.mock_util_mount_cb = mock_util_mount_cb
        self.wrapped_util_write_file = wrapped_util_write_file
        self.mock_wrapping_setup_ephemeral_networking = (
            mock_wrapping_setup_ephemeral_networking
        )
        self.patched_data_dir_path = patched_data_dir_path
        self.patched_reported_ready_marker_path = (
            patched_reported_ready_marker_path
        )

        self.imds_md = {
            "extended": {"compute": {"ppsType": "None"}},
            "network": {
                "interface": [
                    {
                        "ipv4": {
                            "ipAddress": [
                                {
                                    "privateIpAddress": "10.0.0.22",
                                    "publicIpAddress": "",
                                }
                            ],
                            "subnet": [
                                {"address": "10.0.0.0", "prefix": "24"}
                            ],
                        },
                        "ipv6": {"ipAddress": []},
                        "macAddress": "011122334455",
                    },
                ]
            },
        }

    def test_no_pps(self):
        self.mock_readurl.side_effect = [
            mock.MagicMock(contents=json.dumps(self.imds_md).encode()),
        ]
        self.mock_azure_get_metadata_from_fabric.return_value = []

        self.azure_ds._check_and_get_data()

        assert self.mock_readurl.mock_calls == [
            mock.call(
                "http://169.254.169.254/metadata/instance?"
                "api-version=2021-08-01&extended=true",
                timeout=30,
                headers_cb=imds.headers_cb,
                exception_cb=mock.ANY,
                infinite=True,
                log_req_resp=True,
            ),
        ]

        # Verify DHCP is setup once.
        assert self.mock_wrapping_setup_ephemeral_networking.mock_calls == [
            mock.call(timeout_minutes=20)
        ]
        assert self.mock_net_dhcp_maybe_perform_dhcp_discovery.mock_calls == [
            mock.call(
                self.azure_ds.distro,
                None,
                dsaz.dhcp_log_cb,
            )
        ]
        assert self.azure_ds._wireserver_endpoint == "10.11.12.13"
        assert self.azure_ds._is_ephemeral_networking_up() is False

        # Verify DMI usage.
        assert self.mock_dmi_read_dmi_data.mock_calls == [
            mock.call("chassis-asset-tag"),
            mock.call("system-uuid"),
        ]
        assert (
            self.azure_ds.metadata["instance-id"]
            == "50109936-ef07-47fe-ac82-890c853f60d5"
        )

        # Verify IMDS metadata.
        assert self.azure_ds.metadata["imds"] == self.imds_md

        # Verify reporting ready once.
        assert self.mock_azure_get_metadata_from_fabric.mock_calls == [
            mock.call(
                endpoint="10.11.12.13",
                distro=self.azure_ds.distro,
                iso_dev="/dev/sr0",
                pubkey_info=None,
            )
        ]

        # Verify netlink.
        assert self.mock_netlink.mock_calls == []

        # Verify no reported_ready marker written.
        assert self.wrapped_util_write_file.mock_calls == []
        assert self.patched_reported_ready_marker_path.exists() is False

        # Verify reports via KVP.
        assert len(self.mock_kvp_report_failure_to_host.mock_calls) == 0
        assert len(self.mock_kvp_report_success_to_host.mock_calls) == 1

        # Verify dmesg reported via KVP.
        assert len(self.mock_report_dmesg_to_kvp.mock_calls) == 1

    @pytest.mark.parametrize("pps_type", ["Savable", "Running"])
    def test_stale_pps(self, pps_type):
        imds_md_source = copy.deepcopy(self.imds_md)
        imds_md_source["extended"]["compute"]["ppsType"] = pps_type

        nl_sock = mock.MagicMock()
        self.mock_netlink.create_bound_netlink_socket.return_value = nl_sock
        self.mock_readurl.side_effect = [
            mock.MagicMock(contents=json.dumps(imds_md_source).encode()),
            mock.MagicMock(contents=construct_ovf_env().encode()),
            mock.MagicMock(contents=json.dumps(imds_md_source).encode()),
        ]
        self.mock_azure_get_metadata_from_fabric.return_value = []

        self.azure_ds._check_and_get_data()

        assert self.mock_readurl.mock_calls == [
            mock.call(
                "http://169.254.169.254/metadata/instance?"
                "api-version=2021-08-01&extended=true",
                exception_cb=mock.ANY,
                headers_cb=imds.headers_cb,
                infinite=True,
                log_req_resp=True,
                timeout=30,
            ),
            mock.call(
                "http://169.254.169.254/metadata/reprovisiondata?"
                "api-version=2019-06-01",
                exception_cb=mock.ANY,
                headers_cb=imds.headers_cb,
                log_req_resp=False,
                infinite=True,
                timeout=30,
            ),
            mock.call(
                "http://169.254.169.254/metadata/instance?"
                "api-version=2021-08-01&extended=true",
                exception_cb=mock.ANY,
                headers_cb=imds.headers_cb,
                infinite=True,
                log_req_resp=True,
                timeout=30,
            ),
        ]

        # Verify DMI usage.
        assert self.mock_dmi_read_dmi_data.mock_calls == [
            mock.call("chassis-asset-tag"),
            mock.call("system-uuid"),
            mock.call("system-uuid"),
        ]

        # Verify reports via KVP.
        assert len(self.mock_kvp_report_success_to_host.mock_calls) == 1

        assert self.mock_kvp_report_failure_to_host.mock_calls == [
            mock.call(
                errors.ReportableErrorImdsInvalidMetadata(
                    key="extended.compute.ppsType", value=pps_type
                ),
            ),
        ]

    def test_running_pps(self):
        imds_md_source = copy.deepcopy(self.imds_md)
        imds_md_source["extended"]["compute"]["ppsType"] = "Running"

        nl_sock = mock.MagicMock()
        self.mock_netlink.create_bound_netlink_socket.return_value = nl_sock
        self.mock_readurl.side_effect = [
            mock.MagicMock(contents=json.dumps(imds_md_source).encode()),
            mock.MagicMock(contents=construct_ovf_env().encode()),
            mock.MagicMock(contents=json.dumps(self.imds_md).encode()),
        ]
        self.mock_azure_get_metadata_from_fabric.return_value = []

        self.azure_ds._check_and_get_data()

        assert self.mock_readurl.mock_calls == [
            mock.call(
                "http://169.254.169.254/metadata/instance?"
                "api-version=2021-08-01&extended=true",
                exception_cb=mock.ANY,
                headers_cb=imds.headers_cb,
                infinite=True,
                log_req_resp=True,
                timeout=30,
            ),
            mock.call(
                "http://169.254.169.254/metadata/reprovisiondata?"
                "api-version=2019-06-01",
                exception_cb=mock.ANY,
                headers_cb=imds.headers_cb,
                log_req_resp=False,
                infinite=True,
                timeout=30,
            ),
            mock.call(
                "http://169.254.169.254/metadata/instance?"
                "api-version=2021-08-01&extended=true",
                exception_cb=mock.ANY,
                headers_cb=imds.headers_cb,
                infinite=True,
                log_req_resp=True,
                timeout=30,
            ),
        ]

        # Verify DHCP is setup twice.
        assert self.mock_wrapping_setup_ephemeral_networking.mock_calls == [
            mock.call(timeout_minutes=20),
            mock.call(timeout_minutes=5),
        ]
        assert self.mock_net_dhcp_maybe_perform_dhcp_discovery.mock_calls == [
            mock.call(
                self.azure_ds.distro,
                None,
                dsaz.dhcp_log_cb,
            ),
            mock.call(
                self.azure_ds.distro,
                None,
                dsaz.dhcp_log_cb,
            ),
        ]
        assert self.azure_ds._wireserver_endpoint == "10.11.12.13"
        assert self.azure_ds._is_ephemeral_networking_up() is False

        # Verify DMI usage.
        assert self.mock_dmi_read_dmi_data.mock_calls == [
            mock.call("chassis-asset-tag"),
            mock.call("system-uuid"),
        ]
        assert (
            self.azure_ds.metadata["instance-id"]
            == "50109936-ef07-47fe-ac82-890c853f60d5"
        )

        # Verify IMDS metadata.
        assert self.azure_ds.metadata["imds"] == self.imds_md

        # Verify reporting ready twice.
        assert self.mock_azure_get_metadata_from_fabric.mock_calls == [
            mock.call(
                endpoint="10.11.12.13",
                distro=self.azure_ds.distro,
                iso_dev="/dev/sr0",
                pubkey_info=None,
            ),
            mock.call(
                endpoint="10.11.12.13",
                distro=self.azure_ds.distro,
                iso_dev=None,
                pubkey_info=None,
            ),
        ]

        # Verify netlink operations for Running PPS.
        assert self.mock_netlink.mock_calls == [
            mock.call.create_bound_netlink_socket(),
            mock.call.wait_for_media_disconnect_connect(mock.ANY, "ethBoot0"),
            mock.call.create_bound_netlink_socket().close(),
        ]

        # Verify reported_ready marker written and cleaned up.
        assert self.wrapped_util_write_file.mock_calls[0] == mock.call(
            self.patched_reported_ready_marker_path.as_posix(), mock.ANY
        )
        assert self.patched_reported_ready_marker_path.exists() is False

        # Verify reports via KVP.
        assert len(self.mock_kvp_report_failure_to_host.mock_calls) == 0
        assert len(self.mock_kvp_report_success_to_host.mock_calls) == 2

        # Verify dmesg reported via KVP.
        assert len(self.mock_report_dmesg_to_kvp.mock_calls) == 2

    def test_savable_pps(self):
        imds_md_source = copy.deepcopy(self.imds_md)
        imds_md_source["extended"]["compute"]["ppsType"] = "Savable"

        nl_sock = mock.MagicMock()
        self.mock_netlink.create_bound_netlink_socket.return_value = nl_sock
        self.mock_netlink.wait_for_nic_detach_event.return_value = "eth9"
        self.mock_netlink.wait_for_nic_attach_event.return_value = (
            "ethAttached1"
        )
        self.mock_readurl.side_effect = [
            mock.MagicMock(contents=json.dumps(imds_md_source).encode()),
            mock.MagicMock(contents=construct_ovf_env().encode()),
            mock.MagicMock(contents=json.dumps(self.imds_md).encode()),
        ]
        self.mock_azure_get_metadata_from_fabric.return_value = []

        self.azure_ds._check_and_get_data()

        assert self.mock_readurl.mock_calls == [
            mock.call(
                "http://169.254.169.254/metadata/instance?"
                "api-version=2021-08-01&extended=true",
                exception_cb=mock.ANY,
                headers_cb=imds.headers_cb,
                infinite=True,
                log_req_resp=True,
                timeout=30,
            ),
            mock.call(
                "http://169.254.169.254/metadata/reprovisiondata?"
                "api-version=2019-06-01",
                exception_cb=mock.ANY,
                headers_cb=imds.headers_cb,
                log_req_resp=False,
                infinite=True,
                timeout=30,
            ),
            mock.call(
                "http://169.254.169.254/metadata/instance?"
                "api-version=2021-08-01&extended=true",
                exception_cb=mock.ANY,
                headers_cb=imds.headers_cb,
                infinite=True,
                log_req_resp=True,
                timeout=30,
            ),
        ]

        # Verify DHCP is setup twice.
        assert self.mock_wrapping_setup_ephemeral_networking.mock_calls == [
            mock.call(timeout_minutes=20),
            mock.call(
                iface="ethAttached1",
                timeout_minutes=20,
                report_failure_if_not_primary=False,
            ),
        ]
        assert self.mock_net_dhcp_maybe_perform_dhcp_discovery.mock_calls == [
            mock.call(
                self.azure_ds.distro,
                None,
                dsaz.dhcp_log_cb,
            ),
            mock.call(
                self.azure_ds.distro,
                "ethAttached1",
                dsaz.dhcp_log_cb,
            ),
        ]
        assert self.azure_ds._wireserver_endpoint == "10.11.12.13"
        assert self.azure_ds._is_ephemeral_networking_up() is False

        # Verify DMI usage.
        assert self.mock_dmi_read_dmi_data.mock_calls == [
            mock.call("chassis-asset-tag"),
            mock.call("system-uuid"),
        ]
        assert (
            self.azure_ds.metadata["instance-id"]
            == "50109936-ef07-47fe-ac82-890c853f60d5"
        )

        # Verify IMDS metadata.
        assert self.azure_ds.metadata["imds"] == self.imds_md

        # Verify reporting ready twice.
        assert self.mock_azure_get_metadata_from_fabric.mock_calls == [
            mock.call(
                endpoint="10.11.12.13",
                distro=self.azure_ds.distro,
                iso_dev="/dev/sr0",
                pubkey_info=None,
            ),
            mock.call(
                endpoint="10.11.12.13",
                distro=self.azure_ds.distro,
                iso_dev=None,
                pubkey_info=None,
            ),
        ]

        # Verify netlink operations for Savable PPS.
        assert self.mock_netlink.mock_calls == [
            mock.call.create_bound_netlink_socket(),
            mock.call.wait_for_nic_detach_event(nl_sock),
            mock.call.wait_for_nic_attach_event(nl_sock, ["ethAttached1"]),
            mock.call.create_bound_netlink_socket().close(),
        ]

        # Verify reported_ready marker written and cleaned up.
        assert self.wrapped_util_write_file.mock_calls[0] == mock.call(
            self.patched_reported_ready_marker_path.as_posix(), mock.ANY
        )
        assert self.patched_reported_ready_marker_path.exists() is False

        # Verify reports via KVP.
        assert len(self.mock_kvp_report_failure_to_host.mock_calls) == 0
        assert len(self.mock_kvp_report_success_to_host.mock_calls) == 2

        # Verify dmesg reported via KVP.
        assert len(self.mock_report_dmesg_to_kvp.mock_calls) == 2

    @pytest.mark.parametrize(
        "fabric_side_effect",
        [
            [[], []],
            [
                [
                    url_helper.UrlError(
                        requests.ConnectionError(
                            "Failed to establish a new connection: "
                            "[Errno 101] Network is unreachable"
                        )
                    )
                ],
                [],
            ],
            [
                [url_helper.UrlError(requests.ReadTimeout("Read timed out"))],
                [],
            ],
        ],
    )
    def test_savable_pps_early_unplug(self, fabric_side_effect):
        imds_md_source = copy.deepcopy(self.imds_md)
        imds_md_source["extended"]["compute"]["ppsType"] = "Savable"

        nl_sock = mock.MagicMock()
        self.mock_netlink.create_bound_netlink_socket.return_value = nl_sock
        self.mock_netlink.wait_for_nic_detach_event.return_value = "eth9"
        self.mock_netlink.wait_for_nic_attach_event.return_value = (
            "ethAttached1"
        )
        self.mock_readurl.side_effect = [
            mock.MagicMock(contents=json.dumps(imds_md_source).encode()),
            mock.MagicMock(contents=construct_ovf_env().encode()),
            mock.MagicMock(contents=json.dumps(self.imds_md).encode()),
        ]
        self.mock_azure_get_metadata_from_fabric.side_effect = (
            fabric_side_effect
        )

        # Fake DHCP teardown failure.
        ipv4_net = self.mock_ephemeral_ipv4_network
        ipv4_net.return_value.__exit__.side_effect = [
            subp.ProcessExecutionError(
                cmd=["failed", "cmd"],
                stdout="test_stdout",
                stderr="test_stderr",
                exit_code=4,
            ),
            None,
        ]

        self.azure_ds._check_and_get_data()

        assert self.mock_readurl.mock_calls == [
            mock.call(
                "http://169.254.169.254/metadata/instance?"
                "api-version=2021-08-01&extended=true",
                exception_cb=mock.ANY,
                headers_cb=imds.headers_cb,
                infinite=True,
                log_req_resp=True,
                timeout=30,
            ),
            mock.call(
                "http://169.254.169.254/metadata/reprovisiondata?"
                "api-version=2019-06-01",
                exception_cb=mock.ANY,
                headers_cb=imds.headers_cb,
                infinite=True,
                log_req_resp=False,
                timeout=30,
            ),
            mock.call(
                "http://169.254.169.254/metadata/instance?"
                "api-version=2021-08-01&extended=true",
                exception_cb=mock.ANY,
                headers_cb=imds.headers_cb,
                infinite=True,
                log_req_resp=True,
                timeout=30,
            ),
        ]

        # Verify DHCP is setup twice.
        assert self.mock_wrapping_setup_ephemeral_networking.mock_calls == [
            mock.call(timeout_minutes=20),
            mock.call(
                iface="ethAttached1",
                timeout_minutes=20,
                report_failure_if_not_primary=False,
            ),
        ]
        assert self.mock_net_dhcp_maybe_perform_dhcp_discovery.mock_calls == [
            mock.call(
                self.azure_ds.distro,
                None,
                dsaz.dhcp_log_cb,
            ),
            mock.call(
                self.azure_ds.distro,
                "ethAttached1",
                dsaz.dhcp_log_cb,
            ),
        ]
        assert self.azure_ds._wireserver_endpoint == "10.11.12.13"
        assert self.azure_ds._is_ephemeral_networking_up() is False

        # Verify DMI usage.
        assert self.mock_dmi_read_dmi_data.mock_calls == [
            mock.call("chassis-asset-tag"),
            mock.call("system-uuid"),
        ]
        assert (
            self.azure_ds.metadata["instance-id"]
            == "50109936-ef07-47fe-ac82-890c853f60d5"
        )

        # Verify IMDS metadata.
        assert self.azure_ds.metadata["imds"] == self.imds_md

        # Verify reporting ready twice.
        assert self.mock_azure_get_metadata_from_fabric.mock_calls == [
            mock.call(
                endpoint="10.11.12.13",
                distro=self.azure_ds.distro,
                iso_dev="/dev/sr0",
                pubkey_info=None,
            ),
            mock.call(
                endpoint="10.11.12.13",
                distro=self.azure_ds.distro,
                iso_dev=None,
                pubkey_info=None,
            ),
        ]

        # Verify netlink operations for Savable PPS.
        assert self.mock_netlink.mock_calls == [
            mock.call.create_bound_netlink_socket(),
            mock.call.wait_for_nic_detach_event(nl_sock),
            mock.call.wait_for_nic_attach_event(nl_sock, ["ethAttached1"]),
            mock.call.create_bound_netlink_socket().close(),
        ]

        # Verify reported_ready marker written and cleaned up.
        assert self.wrapped_util_write_file.mock_calls[0] == mock.call(
            self.patched_reported_ready_marker_path.as_posix(), mock.ANY
        )
        assert self.patched_reported_ready_marker_path.exists() is False

    @pytest.mark.parametrize("pps_type", ["Savable", "Running", "None"])
    def test_recovery_pps(self, pps_type):
        self.patched_reported_ready_marker_path.write_text("")
        imds_md_source = copy.deepcopy(self.imds_md)
        imds_md_source["extended"]["compute"]["ppsType"] = pps_type

        self.mock_readurl.side_effect = [
            mock.MagicMock(contents=json.dumps(imds_md_source).encode()),
            mock.MagicMock(contents=construct_ovf_env().encode()),
            mock.MagicMock(contents=json.dumps(self.imds_md).encode()),
        ]
        self.mock_azure_get_metadata_from_fabric.return_value = []

        self.azure_ds._check_and_get_data()

        assert self.mock_readurl.mock_calls == [
            mock.call(
                "http://169.254.169.254/metadata/instance?"
                "api-version=2021-08-01&extended=true",
                exception_cb=mock.ANY,
                headers_cb=imds.headers_cb,
                infinite=True,
                log_req_resp=True,
                timeout=30,
            ),
            mock.call(
                "http://169.254.169.254/metadata/reprovisiondata?"
                "api-version=2019-06-01",
                exception_cb=mock.ANY,
                headers_cb=imds.headers_cb,
                infinite=True,
                log_req_resp=False,
                timeout=30,
            ),
            mock.call(
                "http://169.254.169.254/metadata/instance?"
                "api-version=2021-08-01&extended=true",
                exception_cb=mock.ANY,
                headers_cb=imds.headers_cb,
                infinite=True,
                log_req_resp=True,
                timeout=30,
            ),
        ]

        # Verify DHCP is setup once.
        assert self.mock_wrapping_setup_ephemeral_networking.mock_calls == [
            mock.call(timeout_minutes=20),
        ]
        assert self.mock_net_dhcp_maybe_perform_dhcp_discovery.mock_calls == [
            mock.call(
                self.azure_ds.distro,
                None,
                dsaz.dhcp_log_cb,
            ),
        ]

        # Verify IMDS metadata.
        assert self.azure_ds.metadata["imds"] == self.imds_md

        # Verify reports ready once.
        assert self.mock_azure_get_metadata_from_fabric.mock_calls == [
            mock.call(
                endpoint="10.11.12.13",
                distro=self.azure_ds.distro,
                iso_dev="/dev/sr0",
                pubkey_info=None,
            ),
        ]

        # Verify no netlink operations for recovering PPS.
        assert self.mock_netlink.mock_calls == []

        # Verify reported_ready marker not written.
        assert self.wrapped_util_write_file.mock_calls == [
            mock.call(
                filename=str(self.patched_data_dir_path / "ovf-env.xml"),
                content=mock.ANY,
                mode=mock.ANY,
            )
        ]
        assert self.patched_reported_ready_marker_path.exists() is False

        # Verify reports via KVP.
        assert len(self.mock_kvp_report_failure_to_host.mock_calls) == 0
        assert len(self.mock_kvp_report_success_to_host.mock_calls) == 1

    @pytest.mark.parametrize("pps_type", ["Savable", "Running", "Unknown"])
    def test_source_pps_fails_initial_dhcp(self, pps_type):
        self.imds_md["extended"]["compute"]["ppsType"] = pps_type

        nl_sock = mock.MagicMock()
        self.mock_netlink.create_bound_netlink_socket.return_value = nl_sock
        self.mock_readurl.side_effect = [
            mock.MagicMock(contents=json.dumps(self.imds_md).encode()),
            mock.MagicMock(contents=construct_ovf_env().encode()),
            mock.MagicMock(contents=json.dumps(self.imds_md).encode()),
        ]
        self.mock_azure_get_metadata_from_fabric.return_value = []

        self.mock_net_dhcp_maybe_perform_dhcp_discovery.side_effect = [
            dhcp.NoDHCPLeaseError()
        ]

        assert self.azure_ds._get_data() is False

        assert self.mock_wrapping_setup_ephemeral_networking.mock_calls == [
            mock.call(timeout_minutes=20),
            # Second round for _report_failure().
            mock.call(timeout_minutes=20),
        ]
        assert self.mock_readurl.mock_calls == []
        assert self.mock_azure_get_metadata_from_fabric.mock_calls == []
        assert self.mock_netlink.mock_calls == []

        # Verify reports via KVP.
        assert len(self.mock_kvp_report_failure_to_host.mock_calls) == 2
        assert len(self.mock_kvp_report_success_to_host.mock_calls) == 0

    @pytest.mark.parametrize(
        "subp_side_effect",
        [
            subp.SubpResult("okie dokie", ""),
            subp.ProcessExecutionError(
                cmd=["failed", "cmd"],
                stdout="test_stdout",
                stderr="test_stderr",
                exit_code=4,
            ),
        ],
    )
    def test_os_disk_pps(self, mock_sleep, subp_side_effect):
        self.imds_md["extended"]["compute"]["ppsType"] = "PreprovisionedOSDisk"

        self.mock_subp_subp.side_effect = [subp_side_effect]
        self.mock_readurl.side_effect = [
            mock.MagicMock(contents=json.dumps(self.imds_md).encode()),
        ]

        self.azure_ds._get_data()

        assert self.mock_readurl.mock_calls == [
            mock.call(
                "http://169.254.169.254/metadata/instance?"
                "api-version=2021-08-01&extended=true",
                exception_cb=mock.ANY,
                headers_cb=imds.headers_cb,
                infinite=True,
                log_req_resp=True,
                timeout=30,
            ),
        ]

        assert self.mock_subp_subp.mock_calls == []
        assert mock_sleep.mock_calls == [mock.call(31536000)]

        # Verify DHCP is setup once.
        assert self.mock_wrapping_setup_ephemeral_networking.mock_calls == [
            mock.call(timeout_minutes=20)
        ]
        assert self.mock_net_dhcp_maybe_perform_dhcp_discovery.mock_calls == [
            mock.call(
                self.azure_ds.distro,
                None,
                dsaz.dhcp_log_cb,
            )
        ]
        assert self.azure_ds._wireserver_endpoint == "10.11.12.13"
        assert self.azure_ds._is_ephemeral_networking_up() is False

        # Verify reported ready once.
        assert self.mock_azure_get_metadata_from_fabric.mock_calls == [
            mock.call(
                endpoint="10.11.12.13",
                distro=self.azure_ds.distro,
                iso_dev="/dev/sr0",
                pubkey_info=None,
            )
        ]

        # Verify no netlink operations for os disk PPS.
        assert self.mock_netlink.mock_calls == []

        # Ensure no reported ready marker is left behind as the VM's next
        # boot will behave like a typical provisioning boot.
        assert self.patched_reported_ready_marker_path.exists() is False
        assert self.wrapped_util_write_file.mock_calls == []

        # Verify reports via KVP. Ignore failure reported after sleep().
        assert len(self.mock_kvp_report_failure_to_host.mock_calls) == 1
        assert len(self.mock_kvp_report_success_to_host.mock_calls) == 1

    def test_imds_failure_results_in_provisioning_failure(self):
        self.mock_readurl.side_effect = url_helper.UrlError(
            requests.ConnectionError(
                "Failed to establish a new connection: "
                "[Errno 101] Network is unreachable"
            )
        )

        self.mock_azure_get_metadata_from_fabric.return_value = []

        self.azure_ds._check_and_get_data()

        assert self.mock_readurl.mock_calls == [
            mock.call(
                "http://169.254.169.254/metadata/instance?"
                "api-version=2021-08-01&extended=true",
                timeout=30,
                headers_cb=imds.headers_cb,
                exception_cb=mock.ANY,
                infinite=True,
                log_req_resp=True,
            ),
        ]

        # Verify DHCP is setup once.
        assert self.mock_wrapping_setup_ephemeral_networking.mock_calls == [
            mock.call(timeout_minutes=20)
        ]

        # Verify reporting ready once.
        assert self.mock_azure_get_metadata_from_fabric.mock_calls == []

        # Verify netlink.
        assert self.mock_netlink.mock_calls == []

        # Verify no reported_ready marker written.
        assert self.wrapped_util_write_file.mock_calls == []
        assert self.patched_reported_ready_marker_path.exists() is False

        # Verify reports via KVP.
        assert len(self.mock_kvp_report_failure_to_host.mock_calls) == 1
        assert len(self.mock_kvp_report_success_to_host.mock_calls) == 0


class TestGetMetadataFromImds:
    @pytest.mark.parametrize("route_configured_for_imds", [False, True])
    @pytest.mark.parametrize("report_failure", [False, True])
    @pytest.mark.parametrize(
        "exception,reported_error_type",
        [
            (
                url_helper.UrlError(requests.ConnectionError()),
                errors.ReportableErrorImdsUrlError,
            ),
            (
                ValueError("bad data"),
                errors.ReportableErrorImdsMetadataParsingException,
            ),
        ],
    )
    def test_errors(
        self,
        azure_ds,
        exception,
        mock_azure_report_failure_to_fabric,
        mock_imds_fetch_metadata_with_api_fallback,
        mock_kvp_report_failure_to_host,
        mock_time,
        mock_monotonic,
        monkeypatch,
        report_failure,
        reported_error_type,
        route_configured_for_imds,
    ):
        monkeypatch.setattr(
            azure_ds, "_is_ephemeral_networking_up", lambda: True
        )
        azure_ds._route_configured_for_imds = route_configured_for_imds
        mock_imds_fetch_metadata_with_api_fallback.side_effect = exception
        mock_monotonic.return_value = 0.0
        max_connection_errors = None if route_configured_for_imds else 11

        assert (
            azure_ds.get_metadata_from_imds(report_failure=report_failure)
            == {}
        )
        assert mock_imds_fetch_metadata_with_api_fallback.mock_calls == [
            mock.call(
                max_connection_errors=max_connection_errors,
                retry_deadline=mock.ANY,
            )
        ]

        expected_duration = 300
        assert (
            mock_imds_fetch_metadata_with_api_fallback.call_args[1][
                "retry_deadline"
            ]
            == expected_duration
        )

        reported_error = mock_kvp_report_failure_to_host.call_args[0][0]
        assert isinstance(reported_error, reported_error_type)
        assert reported_error.supporting_data["exception"] == repr(exception)
        assert mock_kvp_report_failure_to_host.mock_calls == [
            mock.call(reported_error)
        ]

        connection_error = isinstance(
            exception, url_helper.UrlError
        ) and isinstance(exception.cause, requests.ConnectionError)
        report_skipped = not route_configured_for_imds and connection_error
        if report_failure and not report_skipped:
            assert mock_azure_report_failure_to_fabric.mock_calls == [
                mock.call(endpoint=mock.ANY, error=reported_error)
            ]
        else:
            assert mock_azure_report_failure_to_fabric.mock_calls == []


class TestReportFailure:
    @pytest.mark.parametrize("kvp_enabled", [False, True])
    def test_report_host_only_kvp_enabled(
        self,
        azure_ds,
        kvp_enabled,
        mock_azure_report_failure_to_fabric,
        mock_kvp_report_failure_to_host,
        mock_kvp_report_success_to_host,
        mock_report_dmesg_to_kvp,
    ):
        mock_kvp_report_failure_to_host.return_value = kvp_enabled
        error = errors.ReportableError(reason="foo")

        assert azure_ds._report_failure(error, host_only=True) == kvp_enabled

        assert mock_kvp_report_failure_to_host.mock_calls == [mock.call(error)]
        assert mock_kvp_report_success_to_host.mock_calls == []
        assert mock_azure_report_failure_to_fabric.mock_calls == []
        assert mock_report_dmesg_to_kvp.mock_calls == [mock.call()]


class TestValidateIMDSMetadata:
    @pytest.mark.parametrize(
        "mac,expected",
        [
            ("001122aabbcc", "00:11:22:aa:bb:cc"),
            ("001122AABBCC", "00:11:22:aa:bb:cc"),
            ("00:11:22:aa:bb:cc", "00:11:22:aa:bb:cc"),
            ("00:11:22:AA:BB:CC", "00:11:22:aa:bb:cc"),
            ("pass-through-the-unexpected", "pass-through-the-unexpected"),
            ("", ""),
        ],
    )
    def test_normalize_scenarios(self, mac, expected):
        normalized = dsaz.normalize_mac_address(mac)
        assert normalized == expected

    def test_empty(
        self, azure_ds, caplog, mock_get_interfaces, mock_get_interface_mac
    ):
        imds_md = {}

        assert azure_ds.validate_imds_network_metadata(imds_md) is False
        assert (
            "cloudinit.sources.DataSourceAzure",
            30,
            "IMDS network metadata has incomplete configuration: None",
        ) in caplog.record_tuples

    def test_validates_one_nic(
        self, azure_ds, mock_get_interfaces, mock_get_interface_mac
    ):
        mock_get_interfaces.return_value = [
            ("dummy0", "9e:65:d6:19:19:01", None, None),
            ("test0", "00:11:22:33:44:55", "hv_netvsc", "0x3"),
            ("lo", "00:00:00:00:00:00", None, None),
        ]
        azure_ds._ephemeral_dhcp_ctx = mock.Mock(iface="test0")

        imds_md = {
            "network": {
                "interface": [
                    {
                        "ipv4": {
                            "ipAddress": [
                                {
                                    "privateIpAddress": "10.0.0.22",
                                    "publicIpAddress": "",
                                }
                            ],
                            "subnet": [
                                {"address": "10.0.0.0", "prefix": "24"}
                            ],
                        },
                        "ipv6": {"ipAddress": []},
                        "macAddress": "001122334455",
                    }
                ]
            }
        }

        assert azure_ds.validate_imds_network_metadata(imds_md) is True

    def test_validates_multiple_nic(
        self, azure_ds, mock_get_interfaces, mock_get_interface_mac
    ):
        mock_get_interfaces.return_value = [
            ("dummy0", "9e:65:d6:19:19:01", None, None),
            ("test0", "00:11:22:33:44:55", "hv_netvsc", "0x3"),
            ("test1", "01:11:22:33:44:55", "hv_netvsc", "0x3"),
            ("lo", "00:00:00:00:00:00", None, None),
        ]
        azure_ds._ephemeral_dhcp_ctx = mock.Mock(iface="test0")

        imds_md = {
            "network": {
                "interface": [
                    {
                        "ipv4": {
                            "ipAddress": [
                                {
                                    "privateIpAddress": "10.0.0.22",
                                    "publicIpAddress": "",
                                }
                            ],
                            "subnet": [
                                {"address": "10.0.0.0", "prefix": "24"}
                            ],
                        },
                        "ipv6": {"ipAddress": []},
                        "macAddress": "001122334455",
                    },
                    {
                        "ipv4": {
                            "ipAddress": [
                                {
                                    "privateIpAddress": "10.0.0.22",
                                    "publicIpAddress": "",
                                }
                            ],
                            "subnet": [
                                {"address": "10.0.0.0", "prefix": "24"}
                            ],
                        },
                        "ipv6": {"ipAddress": []},
                        "macAddress": "011122334455",
                    },
                ]
            }
        }

        assert azure_ds.validate_imds_network_metadata(imds_md) is True

    def test_missing_all(
        self, azure_ds, caplog, mock_get_interfaces, mock_get_interface_mac
    ):
        mock_get_interfaces.return_value = [
            ("dummy0", "9e:65:d6:19:19:01", None, None),
            ("test0", "00:11:22:33:44:55", "hv_netvsc", "0x3"),
            ("test1", "01:11:22:33:44:55", "hv_netvsc", "0x3"),
            ("lo", "00:00:00:00:00:00", None, None),
        ]
        azure_ds._ephemeral_dhcp_ctx = mock.Mock(iface="test0")

        imds_md = {"network": {"interface": []}}

        assert azure_ds.validate_imds_network_metadata(imds_md) is False
        assert (
            "cloudinit.sources.DataSourceAzure",
            30,
            "IMDS network metadata is missing configuration for NICs "
            "['00:11:22:33:44:55', '01:11:22:33:44:55']: "
            f"{imds_md['network']!r}",
        ) in caplog.record_tuples

    def test_missing_primary(
        self, azure_ds, caplog, mock_get_interfaces, mock_get_interface_mac
    ):
        mock_get_interfaces.return_value = [
            ("dummy0", "9e:65:d6:19:19:01", None, None),
            ("test0", "00:11:22:33:44:55", "hv_netvsc", "0x3"),
            ("test1", "01:11:22:33:44:55", "hv_netvsc", "0x3"),
            ("lo", "00:00:00:00:00:00", None, None),
        ]
        azure_ds._ephemeral_dhcp_ctx = mock.Mock(iface="test0")

        imds_md = {
            "network": {
                "interface": [
                    {
                        "ipv4": {
                            "ipAddress": [
                                {
                                    "privateIpAddress": "10.0.0.22",
                                    "publicIpAddress": "",
                                }
                            ],
                            "subnet": [
                                {"address": "10.0.0.0", "prefix": "24"}
                            ],
                        },
                        "ipv6": {"ipAddress": []},
                        "macAddress": "011122334455",
                    },
                ]
            }
        }

        assert azure_ds.validate_imds_network_metadata(imds_md) is False
        assert (
            "cloudinit.sources.DataSourceAzure",
            30,
            "IMDS network metadata is missing configuration for NICs "
            f"['00:11:22:33:44:55']: {imds_md['network']!r}",
        ) in caplog.record_tuples
        assert (
            "cloudinit.sources.DataSourceAzure",
            30,
            "IMDS network metadata is missing primary NIC "
            f"'00:11:22:33:44:55': {imds_md['network']!r}",
        ) in caplog.record_tuples

    def test_missing_secondary(
        self, azure_ds, mock_get_interfaces, mock_get_interface_mac
    ):
        mock_get_interfaces.return_value = [
            ("dummy0", "9e:65:d6:19:19:01", None, None),
            ("test0", "00:11:22:33:44:55", "hv_netvsc", "0x3"),
            ("test1", "01:11:22:33:44:55", "hv_netvsc", "0x3"),
            ("lo", "00:00:00:00:00:00", None, None),
        ]
        azure_ds._ephemeral_dhcp_ctx = mock.Mock(iface="test0")

        imds_md = {
            "network": {
                "interface": [
                    {
                        "ipv4": {
                            "ipAddress": [
                                {
                                    "privateIpAddress": "10.0.0.22",
                                    "publicIpAddress": "",
                                }
                            ],
                            "subnet": [
                                {"address": "10.0.0.0", "prefix": "24"}
                            ],
                        },
                        "ipv6": {"ipAddress": []},
                        "macAddress": "001122334455",
                    },
                ]
            }
        }

        assert azure_ds.validate_imds_network_metadata(imds_md) is False


class TestDependencyFallback:
    def test_dependency_fallback(self):
        """Ensure that crypt/passlib import failover gets exercised on all
        Python versions
        """
        assert dsaz.encrypt_pass("`")
