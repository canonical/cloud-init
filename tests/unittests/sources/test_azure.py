# This file is part of cloud-init. See LICENSE file for license information.
# pylint: disable=attribute-defined-outside-init

import builtins
import copy
import datetime
import json
import logging
import os
import stat
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    import passlib.hash
except ImportError:
    passlib = None  # type: ignore
import pytest
import requests

from cloudinit import distros, dmi, helpers, subp, url_helper
from cloudinit.atomic_helper import b64e, json_dumps
from cloudinit.config import cc_mounts
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
    assert_count_equal,
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
def mock_wrapping_report_failure(azure_ds):
    with mock.patch.object(
        azure_ds,
        "_report_failure",
        wraps=azure_ds._report_failure,
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


@pytest.fixture
def mock_find_primary_nic():
    with mock.patch(
        MOCKPATH + "find_primary_nic",
        return_value="eth2",
    ) as m:
        yield m


@pytest.fixture(autouse=True)
def mock_get_interface_details():
    with mock.patch(
        MOCKPATH + "get_interface_details",
        return_value=(None, None),
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


@pytest.fixture(autouse=True)
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
def mock_kvp_report_via_kvp():
    with mock.patch(
        MOCKPATH + "kvp.report_via_kvp",
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
    timestamp = datetime.datetime.now(datetime.timezone.utc)
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


@pytest.fixture
def waagent_d(tmp_path):
    return str(tmp_path / "var/lib/waagent")


# @pytest.mark.usefixtures("fake_filesystem")
class TestAzureDataSource:
    @pytest.fixture(autouse=True)
    def fixture(self, mocker):
        # patch cloud_dir, so our 'seed_dir' is guaranteed empty
        mocker.patch.object(dsaz, "_get_random_seed", return_value="wild")

        self.m_dhcp = mocker.patch.object(
            dsaz,
            "EphemeralDHCPv4",
        )
        self.m_dhcp.return_value.lease = {}
        self.m_dhcp.return_value.iface = "eth4"

        self.m_fetch = mocker.patch.object(
            dsaz.imds,
            "fetch_metadata_with_api_fallback",
            mock.MagicMock(return_value=NETWORK_METADATA),
        )
        self.m_fallback_nic = mocker.patch(
            "cloudinit.sources.net.find_fallback_nic", return_value="eth9"
        )
        self.m_remove_ubuntu_network_scripts = mocker.patch.object(
            dsaz,
            "maybe_remove_ubuntu_network_config_scripts",
            mock.MagicMock(),
        )

    @pytest.fixture
    def apply_patches(self, mocker):
        def _apply_patches(patches):
            for module, name, new in patches:
                mocker.patch.object(module, name, new)

        return _apply_patches

    @pytest.fixture
    def _get_mockds(self, apply_patches):
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
        apply_patches(
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

    @pytest.fixture
    def get_ds(self, apply_patches, paths, tmp_path, waagent_d):
        def _get_ds(
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

            seed_dir = os.path.join(paths.seed_dir, "azure")
            if write_ovf_to_seed_dir and data.get("ovfcontent") is not None:
                populate_dir(seed_dir, {"ovf-env.xml": data["ovfcontent"]})

            if write_ovf_to_data_dir and data.get("ovfcontent") is not None:
                populate_dir(waagent_d, {"ovf-env.xml": data["ovfcontent"]})

            dsaz.BUILTIN_DS_CONFIG["data_dir"] = waagent_d

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

            apply_patches(
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
                distro = distro_cls(distro, data.get("sys_cfg", {}), paths)
            distro.get_tmp_exec_path = mock.Mock(side_effect=str(tmp_path))
            dsrc = dsaz.DataSourceAzure(
                data.get("sys_cfg", {}), distro=distro, paths=paths
            )
            if apply_network is not None:
                dsrc.ds_cfg["apply_network_config"] = apply_network

            return dsrc

        return _get_ds

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

    def test_get_resource_disk(self, _get_mockds):
        ds = _get_mockds
        dev = ds.get_resource_disk_on_freebsd(1)
        assert "da1" == dev

    def test_not_ds_detect_seed_should_return_no_datasource(self, get_ds):
        """Check seed_dir using ds_detect and return False."""
        # Return a non-matching asset tag value
        data = {}
        dsrc = get_ds(data)
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
            assert not ret
            # Assert that for non viable platforms,
            # there is no communication with the Azure datasource.
            assert 0 == m_crawl_metadata.call_count
            assert 0 == m_report_failure.call_count

    def test_platform_viable_but_no_devs_should_return_no_datasource(
        self, get_ds, mocker
    ):
        """For platforms where the Azure platform is viable
        (which is indicated by the matching asset tag),
        the absence of any devs at all (devs == candidate sources
        for crawling Azure datasource) is NOT expected.
        Report failure to Azure as this is an unexpected error.
        """
        data = {}
        dsrc = get_ds(data)
        mocker.patch(MOCKPATH + "list_possible_azure_ds", return_value=[])
        with mock.patch.object(dsrc, "_report_failure") as m_report_failure:
            assert dsrc.get_data() is True
            assert 1 == m_report_failure.call_count

    def test_crawl_metadata_exception_returns_no_datasource(self, get_ds):
        data = {}
        dsrc = get_ds(data)
        with mock.patch.object(dsrc, "crawl_metadata") as m_crawl_metadata:
            m_crawl_metadata.side_effect = Exception
            ret = dsrc.get_data()
            assert 1 == m_crawl_metadata.call_count
            assert not ret

    def test_crawl_metadata_exception_should_report_failure(self, get_ds):
        data = {}
        dsrc = get_ds(data)
        with mock.patch.object(
            dsrc, "crawl_metadata"
        ) as m_crawl_metadata, mock.patch.object(
            dsrc, "_report_failure"
        ) as m_report_failure:
            m_crawl_metadata.side_effect = Exception
            dsrc.get_data()
            assert 1 == m_crawl_metadata.call_count
            m_report_failure.assert_called_once_with(mock.ANY)

    def test_crawl_metadata_exc_should_log_could_not_crawl_msg(
        self, caplog, get_ds
    ):
        data = {}
        dsrc = get_ds(data)
        with mock.patch.object(dsrc, "crawl_metadata") as m_crawl_metadata:
            m_crawl_metadata.side_effect = Exception
            dsrc.get_data()
            assert 1 == m_crawl_metadata.call_count
            assert "Azure datasource failure occurred:" in caplog.text

    def test_basic_seed_dir(self, get_ds, paths, waagent_d):
        data = {
            "ovfcontent": construct_ovf_env(hostname="myhost"),
            "sys_cfg": {},
        }
        dsrc = get_ds(data)
        ret = dsrc.get_data()
        assert ret
        assert dsrc.userdata_raw == ""
        assert dsrc.metadata["local-hostname"] == "myhost"
        assert os.path.isfile(os.path.join(waagent_d, "ovf-env.xml"))
        assert "azure" == dsrc.cloud_name
        assert "azure" == dsrc.platform_type
        seed_dir = os.path.join(paths.seed_dir, "azure")
        assert "seed-dir (%s)" % seed_dir == dsrc.subplatform

    def test_data_dir_without_imds_data(self, get_ds, waagent_d):
        data = {
            "ovfcontent": construct_ovf_env(hostname="myhost"),
            "sys_cfg": {},
        }
        dsrc = get_ds(
            data, write_ovf_to_data_dir=True, write_ovf_to_seed_dir=False
        )

        self.m_fetch.return_value = {}
        with mock.patch(MOCKPATH + "util.mount_cb") as m_mount_cb:
            m_mount_cb.side_effect = [
                MountFailedError("fail"),
                ({"local-hostname": "me"}, "ud", {"cfg": ""}, {}),
            ]
            ret = dsrc.get_data()

        assert ret
        assert dsrc.userdata_raw == ""
        assert dsrc.metadata["local-hostname"] == "myhost"
        assert os.path.isfile(os.path.join(waagent_d, "ovf-env.xml"))
        assert "azure" == dsrc.cloud_name
        assert "azure" == dsrc.platform_type
        assert "seed-dir (%s)" % waagent_d == dsrc.subplatform

    def test_basic_dev_file(self, get_ds):
        """When a device path is used, present that in subplatform."""
        data = {"sys_cfg": {}, "dsdevs": ["/dev/cd0"]}
        dsrc = get_ds(data)
        # DSAzure will attempt to mount /dev/sr0 first, which should
        # fail with mount error since the list of devices doesn't have
        # /dev/sr0
        with mock.patch(MOCKPATH + "util.mount_cb") as m_mount_cb:
            m_mount_cb.side_effect = [
                MountFailedError("fail"),
                ({"local-hostname": "me"}, "ud", {"cfg": ""}, {}),
            ]
            assert dsrc.get_data()
        assert dsrc.userdata_raw == "ud"
        assert dsrc.metadata["local-hostname"] == "me"
        assert "azure" == dsrc.cloud_name
        assert "azure" == dsrc.platform_type
        assert "config-disk (/dev/cd0)" == dsrc.subplatform

    def test_get_data_non_ubuntu_will_not_remove_network_scripts(self, get_ds):
        """get_data on non-Ubuntu will not remove ubuntu net scripts."""
        data = {
            "ovfcontent": construct_ovf_env(
                hostname="myhost", username="myuser"
            ),
            "sys_cfg": {},
        }

        dsrc = get_ds(data, distro="debian")
        dsrc.get_data()
        self.m_remove_ubuntu_network_scripts.assert_not_called()

    def test_get_data_on_ubuntu_will_remove_network_scripts(self, get_ds):
        """get_data will remove ubuntu net scripts on Ubuntu distro."""
        sys_cfg = {"datasource": {"Azure": {"apply_network_config": True}}}
        data = {
            "ovfcontent": construct_ovf_env(),
            "sys_cfg": sys_cfg,
        }

        dsrc = get_ds(data, distro="ubuntu")
        dsrc.get_data()
        self.m_remove_ubuntu_network_scripts.assert_called_once_with()

    def test_get_data_on_ubuntu_will_not_remove_network_scripts_disabled(
        self, get_ds
    ):
        """When apply_network_config false, do not remove scripts on Ubuntu."""
        sys_cfg = {"datasource": {"Azure": {"apply_network_config": False}}}
        data = {
            "ovfcontent": construct_ovf_env(),
            "sys_cfg": sys_cfg,
        }

        dsrc = get_ds(data, distro="ubuntu")
        dsrc.get_data()
        self.m_remove_ubuntu_network_scripts.assert_not_called()

    def test_crawl_metadata_returns_structured_data_and_caches_nothing(
        self, get_ds, waagent_d
    ):
        """Return all structured metadata and cache no class attributes."""
        data = {
            "ovfcontent": construct_ovf_env(
                hostname="myhost", username="myuser", custom_data="FOOBAR"
            ),
            "sys_cfg": {},
        }
        dsrc = get_ds(data)
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

        assert_count_equal(
            crawled_metadata.keys(),
            ["cfg", "files", "metadata", "userdata_raw"],
        )
        assert crawled_metadata["cfg"] == expected_cfg
        assert list(crawled_metadata["files"].keys()) == ["ovf-env.xml"]
        assert (
            b"<ns1:HostName>myhost</ns1:HostName>"
            in crawled_metadata["files"]["ovf-env.xml"]
        )
        assert crawled_metadata["metadata"] == expected_metadata
        assert crawled_metadata["userdata_raw"] == b"FOOBAR"
        assert dsrc.userdata_raw is None
        assert dsrc.metadata == {}
        assert dsrc._metadata_imds == UNSET
        assert not os.path.isfile(os.path.join(waagent_d, "ovf-env.xml"))

    def test_crawl_metadata_raises_invalid_metadata_on_error(self, get_ds):
        """crawl_metadata raises an exception on invalid ovf-env.xml."""
        data = {"ovfcontent": "BOGUS", "sys_cfg": {}}
        dsrc = get_ds(data)
        error_msg = "error parsing ovf-env.xml: syntax error: line 1, column 0"
        with pytest.raises(errors.ReportableErrorOvfParsingException) as cm:
            dsrc.crawl_metadata()
        assert cm.value.reason == error_msg

    def test_crawl_metadata_call_imds_once_no_reprovision(self, get_ds):
        """If reprovisioning, report ready at the end"""
        ovfenv = construct_ovf_env(preprovisioned_vm=False)

        data = {"ovfcontent": ovfenv, "sys_cfg": {}}
        dsrc = get_ds(data)
        dsrc.crawl_metadata()
        assert 1 == self.m_fetch.call_count

    @mock.patch("cloudinit.sources.DataSourceAzure.util.write_file")
    @mock.patch(
        "cloudinit.sources.DataSourceAzure.DataSourceAzure._report_ready"
    )
    @mock.patch("cloudinit.sources.DataSourceAzure.DataSourceAzure._poll_imds")
    def test_crawl_metadata_call_imds_twice_with_reprovision(
        self,
        poll_imds_func,
        m_report_ready,
        m_write,
        get_ds,
        fake_socket,
    ):
        """If reprovisioning, imds metadata will be fetched twice"""
        ovfenv = construct_ovf_env(preprovisioned_vm=True)

        data = {"ovfcontent": ovfenv, "sys_cfg": {}}
        dsrc = get_ds(data)
        poll_imds_func.return_value = ovfenv
        dsrc.crawl_metadata()
        assert 2 == self.m_fetch.call_count

    def test_waagent_d_has_0700_perms(self, get_ds, waagent_d):
        # we expect /var/lib/waagent to be created 0700
        dsrc = get_ds({"ovfcontent": construct_ovf_env()})
        ret = dsrc.get_data()
        assert ret
        assert os.path.isdir(waagent_d)
        assert stat.S_IMODE(os.stat(waagent_d).st_mode) == 0o700

    def test_network_config_set_from_imds(self, get_ds):
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
        dsrc = get_ds(data)
        dsrc.get_data()
        assert expected_network_config == dsrc.network_config

    def test_network_config_set_from_imds_route_metric_for_secondary_nic(
        self, get_ds
    ):
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
        dsrc = get_ds(data)
        dsrc.get_data()
        assert expected_network_config == dsrc.network_config

    def test_network_config_set_from_imds_for_secondary_nic_no_ip(
        self, get_ds
    ):
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
        dsrc = get_ds(data)
        dsrc.get_data()
        assert expected_network_config == dsrc.network_config

    def test_availability_zone_set_from_imds(self, get_ds):
        """Datasource.availability returns IMDS platformFaultDomain."""
        sys_cfg = {"datasource": {"Azure": {"apply_network_config": True}}}
        data = {
            "ovfcontent": construct_ovf_env(),
            "sys_cfg": sys_cfg,
        }
        dsrc = get_ds(data)
        dsrc.get_data()
        assert "0" == dsrc.availability_zone

    def test_region_set_from_imds(self, get_ds):
        """Datasource.region returns IMDS region location."""
        sys_cfg = {"datasource": {"Azure": {"apply_network_config": True}}}
        data = {
            "ovfcontent": construct_ovf_env(),
            "sys_cfg": sys_cfg,
        }
        dsrc = get_ds(data)
        dsrc.get_data()
        assert "eastus2" == dsrc.region

    def test_sys_cfg_set_never_destroy_ntfs(self, get_ds):
        sys_cfg = {
            "datasource": {
                "Azure": {"never_destroy_ntfs": "user-supplied-value"}
            }
        }
        data = {
            "ovfcontent": construct_ovf_env(),
            "sys_cfg": sys_cfg,
        }

        dsrc = get_ds(data)
        ret = self._get_and_setup(dsrc)
        assert ret
        assert (
            dsrc.ds_cfg.get(dsaz.DS_CFG_KEY_PRESERVE_NTFS)
            == "user-supplied-value"
        )

    def test_no_admin_username(self, get_ds):
        data = {"ovfcontent": construct_ovf_env(username=None)}

        dsrc = get_ds(data)
        ret = dsrc.get_data()
        assert ret

        assert dsrc.cfg == {
            "PreprovisionedVMType": None,
            "PreprovisionedVm": False,
            "ProvisionGuestProxyAgent": False,
        }

    def test_username_used(self, get_ds):
        data = {"ovfcontent": construct_ovf_env(username="myuser")}

        dsrc = get_ds(data)
        ret = dsrc.get_data()
        assert ret
        assert dsrc.cfg["system_info"]["default_user"]["name"] == "myuser"

        assert "ssh_pwauth" not in dsrc.cfg

    @pytest.mark.skipif(passlib is None, reason="passlib not installed")
    def test_password_given(self, get_ds, mocker):
        # The crypt module has platform-specific behavior and the purpose of
        # this test isn't to verify the differences between crypt and passlib,
        # so hardcode passlib usage as crypt is deprecated.
        mocker.patch.object(
            dsaz, "hash_password", passlib.hash.sha512_crypt.hash
        )
        data = {
            "ovfcontent": construct_ovf_env(
                username="myuser", password="mypass"
            )
        }

        dsrc = get_ds(data)
        ret = dsrc.get_data()
        assert ret
        assert "default_user" in dsrc.cfg["system_info"]
        defuser = dsrc.cfg["system_info"]["default_user"]

        # default user should be updated username and should not be locked.
        assert defuser["name"] == "myuser"
        assert not defuser["lock_passwd"]
        # passwd is crypt formatted string $id$salt$encrypted
        # encrypting plaintext with salt value of everything up to final '$'
        # should equal that after the '$'
        assert passlib.hash.sha512_crypt.verify(
            "mypass", defuser["hashed_passwd"]
        )

        assert dsrc.cfg["ssh_pwauth"] is True

    def test_password_with_disable_ssh_pw_auth_true(self, get_ds):
        data = {
            "ovfcontent": construct_ovf_env(
                username="myuser",
                password="mypass",
                disable_ssh_password_auth=True,
            )
        }

        dsrc = get_ds(data)
        dsrc.get_data()

        assert dsrc.cfg["ssh_pwauth"] is False

    def test_password_with_disable_ssh_pw_auth_false(self, get_ds):
        data = {
            "ovfcontent": construct_ovf_env(
                username="myuser",
                password="mypass",
                disable_ssh_password_auth=False,
            )
        }

        dsrc = get_ds(data)
        dsrc.get_data()

        assert dsrc.cfg["ssh_pwauth"] is True

    def test_password_with_disable_ssh_pw_auth_unspecified(self, get_ds):
        data = {
            "ovfcontent": construct_ovf_env(
                username="myuser",
                password="mypass",
                disable_ssh_password_auth=None,
            )
        }

        dsrc = get_ds(data)
        dsrc.get_data()

        assert dsrc.cfg["ssh_pwauth"] is True

    def test_no_password_with_disable_ssh_pw_auth_true(self, get_ds):
        data = {
            "ovfcontent": construct_ovf_env(
                username="myuser",
                disable_ssh_password_auth=True,
            )
        }

        dsrc = get_ds(data)
        dsrc.get_data()

        assert dsrc.cfg["ssh_pwauth"] is False

    def test_no_password_with_disable_ssh_pw_auth_false(self, get_ds):
        data = {
            "ovfcontent": construct_ovf_env(
                username="myuser",
                disable_ssh_password_auth=False,
            )
        }

        dsrc = get_ds(data)
        dsrc.get_data()

        assert dsrc.cfg["ssh_pwauth"] is True

    def test_no_password_with_disable_ssh_pw_auth_unspecified(self, get_ds):
        data = {
            "ovfcontent": construct_ovf_env(
                username="myuser",
                disable_ssh_password_auth=None,
            )
        }

        dsrc = get_ds(data)
        dsrc.get_data()

        assert "ssh_pwauth" not in dsrc.cfg

    def test_user_not_locked_if_password_redacted(self, get_ds):
        data = {
            "ovfcontent": construct_ovf_env(
                username="myuser",
                password=dsaz.DEF_PASSWD_REDACTION,
            )
        }

        dsrc = get_ds(data)
        ret = dsrc.get_data()
        assert ret
        assert "default_user" in dsrc.cfg["system_info"]
        defuser = dsrc.cfg["system_info"]["default_user"]

        # default user should be updated username and should not be locked.
        assert defuser["name"] == "myuser"
        assert "lock_passwd" in defuser
        assert not defuser["lock_passwd"]

    def test_userdata_found(self, get_ds):
        mydata = "FOOBAR"
        data = {"ovfcontent": construct_ovf_env(custom_data=mydata)}

        dsrc = get_ds(data)
        ret = dsrc.get_data()
        assert ret
        assert dsrc.userdata_raw == mydata.encode("utf-8")

    def test_default_ephemeral_configs_ephemeral_exists(self, get_ds):
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
            dsrc = get_ds(data)
            ret = dsrc.get_data()
            assert ret
            cfg = dsrc.get_config_obj()

            assert (
                dsrc.device_name_to_device("ephemeral0")
                == dsaz.RESOURCE_DISK_PATH
            )
            assert "disk_setup" in cfg
            assert "fs_setup" in cfg
            assert isinstance(cfg["disk_setup"], dict)
            assert isinstance(cfg["fs_setup"], list)

    def test_default_ephemeral_configs_ephemeral_does_not_exist(self, get_ds):
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
            dsrc = get_ds(data)
            ret = dsrc.get_data()
            assert ret
            cfg = dsrc.get_config_obj()

            assert "disk_setup" not in cfg
            assert "fs_setup" not in cfg

    def test_userdata_arrives(self, get_ds):
        userdata = "This is my user-data"
        xml = construct_ovf_env(custom_data=userdata)
        data = {"ovfcontent": xml}
        dsrc = get_ds(data)
        dsrc.get_data()

        assert userdata.encode("us-ascii") == dsrc.userdata_raw

    def test_password_redacted_in_ovf(self, get_ds, waagent_d):
        data = {
            "ovfcontent": construct_ovf_env(
                username="myuser", password="mypass"
            )
        }
        dsrc = get_ds(data)
        ret = dsrc.get_data()

        assert ret
        ovf_env_path = os.path.join(waagent_d, "ovf-env.xml")

        # The XML should not be same since the user password is redacted
        on_disk_ovf = load_text_file(ovf_env_path)
        self.xml_notequals(data["ovfcontent"], on_disk_ovf)

        # Make sure that the redacted password on disk is not used by CI
        assert dsrc.cfg.get("password") != dsaz.DEF_PASSWD_REDACTION

        # Make sure that the password was really encrypted
        et = ET.fromstring(on_disk_ovf)
        for elem in et.iter():
            if "UserPassword" in elem.tag:
                assert dsaz.DEF_PASSWD_REDACTION == elem.text

    def test_ovf_env_arrives_in_waagent_dir(self, get_ds, waagent_d):
        xml = construct_ovf_env(custom_data="FOODATA")
        dsrc = get_ds({"ovfcontent": xml})
        dsrc.get_data()

        # 'data_dir' is '/var/lib/waagent' (walinux-agent's state dir)
        # we expect that the ovf-env.xml file is copied there.
        ovf_env_path = os.path.join(waagent_d, "ovf-env.xml")
        assert os.path.exists(ovf_env_path)
        self.xml_equals(xml, load_text_file(ovf_env_path))

    def test_ovf_can_include_unicode(self, get_ds):
        xml = construct_ovf_env()
        xml = "\ufeff{0}".format(xml)
        dsrc = get_ds({"ovfcontent": xml})
        dsrc.get_data()

    def test_dsaz_report_ready_returns_true_when_report_succeeds(self, get_ds):
        dsrc = get_ds({"ovfcontent": construct_ovf_env()})
        assert dsrc._report_ready() == []

    @mock.patch(MOCKPATH + "report_diagnostic_event")
    def test_dsaz_report_ready_failure_reports_telemetry(
        self, m_report_diag, get_ds
    ):
        dsrc = get_ds({"ovfcontent": construct_ovf_env()})
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

    def test_dsaz_report_failure_returns_true_when_report_succeeds(
        self, get_ds
    ):
        dsrc = get_ds({"ovfcontent": construct_ovf_env()})

        with mock.patch.object(dsrc, "crawl_metadata") as m_crawl_metadata:
            # mock crawl metadata failure to cause report failure
            m_crawl_metadata.side_effect = Exception

            error = errors.ReportableError(reason="foo")
            assert dsrc._report_failure(error)
            assert 1 == self.m_report_failure_to_fabric.call_count

    def test_dsaz_report_failure_returns_false_and_does_not_propagate_exc(
        self, get_ds
    ):
        dsrc = get_ds({"ovfcontent": construct_ovf_env()})

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
            assert not dsrc._report_failure(error)
            assert 2 == self.m_report_failure_to_fabric.call_count

    def test_dsaz_report_failure(self, get_ds):
        dsrc = get_ds({"ovfcontent": construct_ovf_env()})

        with mock.patch.object(dsrc, "crawl_metadata") as m_crawl_metadata:
            m_crawl_metadata.side_effect = Exception

            error = errors.ReportableError(reason="foo")
            assert dsrc._report_failure(error)
            self.m_report_failure_to_fabric.assert_called_once_with(
                endpoint="168.63.129.16",
                encoded_report=error.as_encoded_report(vm_id=dsrc._vm_id),
            )

    def test_dsaz_report_failure_uses_cached_ephemeral_dhcp_ctx_lease(
        self, get_ds
    ):
        dsrc = get_ds({"ovfcontent": construct_ovf_env()})

        with mock.patch.object(
            dsrc, "crawl_metadata"
        ) as m_crawl_metadata, mock.patch.object(
            dsrc, "_wireserver_endpoint", "test-ep"
        ):
            # mock crawl metadata failure to cause report failure
            m_crawl_metadata.side_effect = Exception

            error = errors.ReportableError(reason="foo")
            assert dsrc._report_failure(error)

            # ensure called with cached ephemeral dhcp lease option 245
            self.m_report_failure_to_fabric.assert_called_once_with(
                endpoint="test-ep",
                encoded_report=error.as_encoded_report(vm_id=dsrc._vm_id),
            )

    def test_dsaz_report_failure_no_net_uses_new_ephemeral_dhcp_lease(
        self, get_ds
    ):
        dsrc = get_ds({"ovfcontent": construct_ovf_env()})

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
            assert dsrc._report_failure(error)

            # ensure called with the newly discovered
            # ephemeral dhcp lease option 245
            self.m_report_failure_to_fabric.assert_called_once_with(
                endpoint="1.2.3.4",
                encoded_report=error.as_encoded_report(vm_id=dsrc._vm_id),
            )

    def test_exception_fetching_fabric_data_doesnt_propagate(self, get_ds):
        """Errors communicating with fabric should warn, but return True."""
        dsrc = get_ds({"ovfcontent": construct_ovf_env()})
        self.m_get_metadata_from_fabric.side_effect = Exception
        ret = self._get_and_setup(dsrc)
        assert ret

    def test_fabric_data_included_in_metadata(self, get_ds):
        dsrc = get_ds({"ovfcontent": construct_ovf_env()})
        self.m_get_metadata_from_fabric.return_value = ["ssh-key-value"]
        ret = self._get_and_setup(dsrc)
        assert ret
        assert ["ssh-key-value"] == dsrc.metadata["public-keys"]

    def test_instance_id_case_insensitive(self, get_ds, paths):
        """Return the previous iid when current is a case-insensitive match."""
        lower_iid = EXAMPLE_UUID.lower()
        upper_iid = EXAMPLE_UUID.upper()
        # lowercase current UUID
        ds = get_ds({"ovfcontent": construct_ovf_env()}, instance_id=lower_iid)
        # UPPERCASE previous
        write_file(
            os.path.join(paths.cloud_dir, "data", "instance-id"),
            upper_iid,
        )
        ds.get_data()
        assert upper_iid == ds.metadata["instance-id"]

        # UPPERCASE current UUID
        ds = get_ds({"ovfcontent": construct_ovf_env()}, instance_id=upper_iid)
        # lowercase previous
        write_file(
            os.path.join(paths.cloud_dir, "data", "instance-id"),
            lower_iid,
        )
        ds.get_data()
        assert lower_iid == ds.metadata["instance-id"]

    def test_instance_id_endianness(self, get_ds, paths):
        """Return the previous iid when dmi uuid is the byteswapped iid."""
        ds = get_ds({"ovfcontent": construct_ovf_env()})
        # byte-swapped previous
        write_file(
            os.path.join(paths.cloud_dir, "data", "instance-id"),
            "544CDFD0-CB4E-4B4A-9954-5BDF3ED5C3B8",
        )
        ds.get_data()
        assert (
            "544CDFD0-CB4E-4B4A-9954-5BDF3ED5C3B8"
            == ds.metadata["instance-id"]
        )
        # not byte-swapped previous
        write_file(
            os.path.join(paths.cloud_dir, "data", "instance-id"),
            "644CDFD0-CB4E-4B4A-9954-5BDF3ED5C3B8",
        )
        ds.get_data()
        assert self.instance_id == ds.metadata["instance-id"]

    def test_instance_id_from_dmidecode_used(self, get_ds):
        ds = get_ds({"ovfcontent": construct_ovf_env()})
        ds.get_data()
        assert self.instance_id == ds.metadata["instance-id"]

    def test_instance_id_from_dmidecode_used_for_builtin(self, get_ds):
        ds = get_ds({"ovfcontent": construct_ovf_env()})
        ds.get_data()
        assert self.instance_id == ds.metadata["instance-id"]

    @mock.patch(MOCKPATH + "util.is_FreeBSD")
    @mock.patch(MOCKPATH + "_check_freebsd_cdrom")
    def test_list_possible_azure_ds(self, m_check_fbsd_cdrom, m_is_FreeBSD):
        """On FreeBSD, possible devs should show /dev/cd0."""
        m_is_FreeBSD.return_value = True
        m_check_fbsd_cdrom.return_value = True
        possible_ds = []
        for src in dsaz.list_possible_azure_ds("seed_dir", "cache_dir"):
            possible_ds.append(src)
        assert possible_ds == [
            "seed_dir",
            dsaz.DEFAULT_PROVISIONING_ISO_DEV,
            "/dev/cd0",
            "cache_dir",
        ]
        assert [mock.call("/dev/cd0")] == m_check_fbsd_cdrom.call_args_list

    @mock.patch(MOCKPATH + "net.get_interfaces")
    def test_blacklist_through_distro(
        self, m_net_get_interfaces, get_ds, paths
    ):
        """Verify Azure DS updates blacklist drivers in the distro's
        networking object."""
        data = {
            "ovfcontent": construct_ovf_env(),
            "sys_cfg": {},
        }

        distro_cls = distros.fetch("ubuntu")
        distro = distro_cls("ubuntu", {}, paths)
        dsrc = get_ds(data, distro=distro)
        dsrc.get_data()

        distro.networking.get_interfaces_by_mac()
        m_net_get_interfaces.assert_called_with()

    @mock.patch(
        "cloudinit.sources.helpers.azure.OpenSSLManager.parse_certificates"
    )
    def test_get_public_ssh_keys_with_imds(self, m_parse_certificates, get_ds):
        sys_cfg = {"datasource": {"Azure": {"apply_network_config": True}}}
        data = {
            "ovfcontent": construct_ovf_env(),
            "sys_cfg": sys_cfg,
        }
        dsrc = get_ds(data)
        dsrc.get_data()
        dsrc.setup(True)
        ssh_keys = dsrc.get_public_ssh_keys()
        assert ssh_keys == ["ssh-rsa key1"]
        assert m_parse_certificates.call_count == 0

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
        self, m_parse_certificates, get_ds
    ):
        imds_data = copy.deepcopy(NETWORK_METADATA)
        imds_data["compute"]["publicKeys"][0]["keyData"] = "no-openssh-format"
        self.m_fetch.return_value = imds_data
        sys_cfg = {"datasource": {"Azure": {"apply_network_config": True}}}
        data = {
            "ovfcontent": construct_ovf_env(),
            "sys_cfg": sys_cfg,
        }
        dsrc = get_ds(data)
        dsrc.get_data()
        dsrc.setup(True)
        ssh_keys = dsrc.get_public_ssh_keys()
        assert ssh_keys == []
        assert m_parse_certificates.call_count == 0

    def test_get_public_ssh_keys_without_imds(self, get_ds):
        self.m_fetch.return_value = dict()
        sys_cfg = {"datasource": {"Azure": {"apply_network_config": True}}}
        data = {
            "ovfcontent": construct_ovf_env(),
            "sys_cfg": sys_cfg,
        }
        dsrc = get_ds(data)
        dsaz.get_metadata_from_fabric.return_value = ["key2"]
        dsrc.get_data()
        dsrc.setup(True)
        ssh_keys = dsrc.get_public_ssh_keys()
        assert ssh_keys == ["key2"]

    def test_hostname_from_imds(self, get_ds):
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
        dsrc = get_ds(data)
        dsrc.get_data()
        assert dsrc.metadata["local-hostname"] == "hostname1"

    def test_username_from_imds(self, get_ds):
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
        dsrc = get_ds(data)
        dsrc.get_data()
        assert dsrc.cfg["system_info"]["default_user"]["name"] == "username1"

    def test_disable_password_from_imds_true(self, get_ds):
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
        dsrc = get_ds(data)
        dsrc.get_data()
        assert not dsrc.cfg["ssh_pwauth"]

    def test_disable_password_from_imds_false(self, get_ds):
        sys_cfg = {"datasource": {"Azure": {"apply_network_config": True}}}
        data = {
            "ovfcontent": construct_ovf_env(),
            "sys_cfg": sys_cfg,
            "write_ovf_to_seed_dir": False,
        }
        imds_data_with_os_profile = copy.deepcopy(NETWORK_METADATA)
        imds_data_with_os_profile["compute"]["osProfile"] = dict(
            adminUsername="username1",
            computerName="hostname1",
            disablePasswordAuthentication="false",
        )
        self.m_fetch.return_value = imds_data_with_os_profile
        dsrc = get_ds(data)
        dsrc.get_data()
        assert dsrc.cfg["ssh_pwauth"]

    def test_userdata_from_imds(self, get_ds):
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
        dsrc = get_ds(data)
        ret = dsrc.get_data()
        assert ret
        assert dsrc.userdata_raw == userdata.encode("utf-8")

    def test_userdata_from_imds_with_customdata_from_OVF(self, get_ds):
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
        dsrc = get_ds(data)
        ret = dsrc.get_data()
        assert ret
        assert dsrc.userdata_raw == userdataOVF.encode("utf-8")

    @pytest.mark.usefixtures("fake_filesystem")
    def test_cleanup_resourcedisk_fstab(self, get_ds):
        """Ensure that cloud-init clean will remove resource disk entries
        from /etc/fstab"""
        fstab_original_content = (
            "UUID=abc123 / ext4 defaults 0 0\n"
            "/dev/disk/cloud/azure_resource-part1	/mnt	"
            "auto	defaults,nofail,x-systemd.after="
            "cloud-init.service,_netdev,comment=cloudconfig	0	2\n"
        )
        fstab_expected_content = "UUID=abc123 / ext4 defaults 0 0\n"

        etc_path = "/etc"
        if not os.path.exists(etc_path):
            os.makedirs(etc_path)
        fstab_path = cc_mounts.FSTAB_PATH
        with open(fstab_path, "w") as fd:
            fd.write(fstab_original_content)

        data = {}
        dsrc = get_ds(data)
        dsrc.clean()

        with open(fstab_path, "r") as fd:
            fstab_new_content = fd.read()
            assert fstab_expected_content == fstab_new_content


class TestLoadAzureDsDir:
    """Tests for load_azure_ds_dir."""

    def test_missing_ovf_env_xml_raises_non_azure_datasource_error(
        self, tmp_path
    ):
        """load_azure_ds_dir raises an error When ovf-env.xml doesn't exit."""
        with pytest.raises(
            dsaz.NonAzureDataSource, match="No ovf-env file found"
        ):
            dsaz.load_azure_ds_dir(str(tmp_path))

    def test_wb_invalid_ovf_env_xml_calls_read_azure_ovf(self, tmp_path):
        """load_azure_ds_dir calls read_azure_ovf to parse the xml."""
        ovf_path = os.path.join(str(tmp_path), "ovf-env.xml")
        with open(ovf_path, "wb") as stream:
            stream.write(b"invalid xml")
        with pytest.raises(errors.ReportableErrorOvfParsingException) as cm:
            dsaz.load_azure_ds_dir(str(tmp_path))
        assert (
            "error parsing ovf-env.xml: syntax error: line 1, column 0"
            == cm.value.reason
        )

    def test_import_error_from_failed_import(self):
        """Attempt to import a module that is not present"""
        try:
            import nonexistent_module_that_will_never_exist  # type: ignore[import-not-found] # noqa: F401 # isort:skip
        except ImportError as error:
            reportable_error = errors.ReportableErrorImportError(error=error)

            assert (
                reportable_error.reason == "error importing "
                "nonexistent_module_that_will_never_exist library"
            )
            assert reportable_error.supporting_data["error"] == repr(error)


class TestReadAzureOvf:
    def test_invalid_xml_raises_non_azure_ds(self):
        invalid_xml = "<foo>" + construct_ovf_env()
        with pytest.raises(errors.ReportableErrorOvfParsingException):
            dsaz.read_azure_ovf(
                invalid_xml,
            )

    def test_load_with_pubkeys(self):
        public_keys = [{"fingerprint": "fp1", "path": "path1", "value": ""}]
        content = construct_ovf_env(public_keys=public_keys)
        (_md, _ud, cfg) = dsaz.read_azure_ovf(content)
        for pk in public_keys:
            assert pk in cfg["_pubkeys"]


class TestCanDevBeReformatted:
    warning_file = "dataloss_warning_readme.txt"

    @pytest.fixture
    def patchup(self, mocker):
        def _patchup(devs):
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
            self.m_partitions_on_device = mocker.patch(
                p + "_partitions_on_device"
            )
            self.m_has_ntfs_filesystem = mocker.patch(
                p + "_has_ntfs_filesystem"
            )
            self.m_realpath = mocker.patch(p + "os.path.realpath")
            self.m_exists = mocker.patch(p + "os.path.exists")
            self.m_selguard = mocker.patch(p + "util.SeLinuxGuard")

            self.m_exists.side_effect = lambda p: p in bypath
            self.m_realpath.side_effect = realpath
            self.m_has_ntfs_filesystem.side_effect = has_ntfs_fs
            self.m_partitions_on_device.side_effect = partitions_on_device
            self.m_selguard.__enter__ = mock.Mock(return_value=False)
            self.m_selguard.__exit__ = mock.Mock()

            return bypath

        return _patchup

    @pytest.fixture
    def domock_mount_cb(self, mocker, tmp_path):
        def _do_mock_mount_cb(bypath):
            def mount_cb(
                device, callback, mtype, update_env_for_mount, log_error=False
            ):
                assert "ntfs" == mtype
                assert "C" == update_env_for_mount.get("LANG")
                for f in bypath.get(device).get("files", []):
                    write_file(os.path.join(tmp_path, f), content=f)
                return callback(str(tmp_path))

            p = MOCKPATH
            self.m_mount_cb = mocker.patch(p + "util.mount_cb")
            self.m_mount_cb.side_effect = mount_cb

        return _do_mock_mount_cb

    M_PATH = "cloudinit.util."

    @mock.patch(M_PATH + "subp.subp")
    def test_ntfs_mount_logs(self, m_subp, caplog, patchup):
        """can_dev_be_reformatted does not log errors in case of
        unknown filesystem 'ntfs'."""
        patchup(
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
        assert log_msg not in caplog.text

    def test_three_partitions_is_false(self, domock_mount_cb, patchup):
        """A disk with 3 partitions can not be formatted."""
        bypath = patchup(
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
        domock_mount_cb(bypath)
        value, msg = dsaz.can_dev_be_reformatted(
            "/dev/sda", preserve_ntfs=False
        )
        assert not value
        assert "3 or more" in msg.lower()

    def test_no_partitions_is_false(self, patchup, domock_mount_cb):
        """A disk with no partitions can not be formatted."""
        bypath = patchup({"/dev/sda": {}})
        domock_mount_cb(bypath)
        value, msg = dsaz.can_dev_be_reformatted(
            "/dev/sda", preserve_ntfs=False
        )
        assert not value
        assert "not partitioned" in msg.lower()

    def test_two_partitions_not_ntfs_false(self, patchup, domock_mount_cb):
        """2 partitions and 2nd not ntfs can not be formatted."""
        bypath = patchup(
            {
                "/dev/sda": {
                    "partitions": {
                        "/dev/sda1": {"num": 1},
                        "/dev/sda2": {"num": 2, "fs": "ext4", "files": []},
                    }
                }
            }
        )
        domock_mount_cb(bypath)
        value, msg = dsaz.can_dev_be_reformatted(
            "/dev/sda", preserve_ntfs=False
        )
        assert not value
        assert "not ntfs" in msg.lower()

    def test_two_partitions_ntfs_populated_false(
        self, patchup, domock_mount_cb
    ):
        """2 partitions and populated ntfs fs on 2nd can not be formatted."""
        bypath = patchup(
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
        domock_mount_cb(bypath)
        value, msg = dsaz.can_dev_be_reformatted(
            "/dev/sda", preserve_ntfs=False
        )
        assert not value
        assert "files on it" in msg.lower()

    def test_two_partitions_ntfs_empty_is_true(self, patchup, domock_mount_cb):
        """2 partitions and empty ntfs fs on 2nd can be formatted."""
        bypath = patchup(
            {
                "/dev/sda": {
                    "partitions": {
                        "/dev/sda1": {"num": 1},
                        "/dev/sda2": {"num": 2, "fs": "ntfs", "files": []},
                    }
                }
            }
        )
        domock_mount_cb(bypath)
        value, msg = dsaz.can_dev_be_reformatted(
            "/dev/sda", preserve_ntfs=False
        )
        assert value
        assert "safe for" in msg.lower()

    def test_one_partition_not_ntfs_false(self, patchup, domock_mount_cb):
        """1 partition witih fs other than ntfs can not be formatted."""
        bypath = patchup(
            {
                "/dev/sda": {
                    "partitions": {
                        "/dev/sda1": {"num": 1, "fs": "zfs"},
                    }
                }
            }
        )
        domock_mount_cb(bypath)
        value, msg = dsaz.can_dev_be_reformatted(
            "/dev/sda", preserve_ntfs=False
        )
        assert not value
        assert "not ntfs" in msg.lower()

    def test_one_partition_ntfs_populated_false(
        self, patchup, domock_mount_cb
    ):
        """1 mountable ntfs partition with many files can not be formatted."""
        bypath = patchup(
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
        domock_mount_cb(bypath)
        with mock.patch.object(dsaz.LOG, "warning") as warning:
            value, msg = dsaz.can_dev_be_reformatted(
                "/dev/sda", preserve_ntfs=False
            )
            wmsg = warning.call_args[0][0]
            assert "looks like you're using NTFS on the ephemeral disk" in wmsg
            assert not value
            assert "files on it" in msg.lower()

    def test_one_partition_ntfs_empty_is_true(self, patchup, domock_mount_cb):
        """1 mountable ntfs partition and no files can be formatted."""
        bypath = patchup(
            {
                "/dev/sda": {
                    "partitions": {
                        "/dev/sda1": {"num": 1, "fs": "ntfs", "files": []}
                    }
                }
            }
        )
        domock_mount_cb(bypath)
        value, msg = dsaz.can_dev_be_reformatted(
            "/dev/sda", preserve_ntfs=False
        )
        assert value
        assert "safe for" in msg.lower()

    def test_one_partition_ntfs_empty_with_dataloss_file_is_true(
        self, patchup, domock_mount_cb
    ):
        """1 mountable ntfs partition and only warn file can be formatted."""
        bypath = patchup(
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
        domock_mount_cb(bypath)
        value, msg = dsaz.can_dev_be_reformatted(
            "/dev/sda", preserve_ntfs=False
        )
        assert value
        assert "safe for" in msg.lower()

    def test_one_partition_ntfs_empty_with_svi_file_is_true(
        self, patchup, domock_mount_cb
    ):
        """1 mountable ntfs partition and only warn file can be formatted."""
        bypath = patchup(
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
        domock_mount_cb(bypath)
        value, msg = dsaz.can_dev_be_reformatted(
            "/dev/sda", preserve_ntfs=False
        )
        assert value
        assert "safe for" in msg.lower()

    def test_one_partition_through_realpath_is_true(
        self, patchup, domock_mount_cb
    ):
        """A symlink to a device with 1 ntfs partition can be formatted."""
        epath = "/dev/disk/cloud/azure_resource"
        bypath = patchup(
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
        domock_mount_cb(bypath)
        value, msg = dsaz.can_dev_be_reformatted(epath, preserve_ntfs=False)
        assert value
        assert "safe for" in msg.lower()

    def test_three_partition_through_realpath_is_false(
        self, patchup, domock_mount_cb
    ):
        """A symlink to a device with 3 partitions can not be formatted."""
        epath = "/dev/disk/cloud/azure_resource"
        bypath = patchup(
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
        domock_mount_cb(bypath)
        value, msg = dsaz.can_dev_be_reformatted(epath, preserve_ntfs=False)
        assert not value
        assert "3 or more" in msg.lower()

    def test_ntfs_mount_errors_true(self, patchup, domock_mount_cb):
        """can_dev_be_reformatted does not fail if NTFS is unknown fstype."""
        bypath = patchup(
            {
                "/dev/sda": {
                    "partitions": {
                        "/dev/sda1": {"num": 1, "fs": "ntfs", "files": []}
                    }
                }
            }
        )
        domock_mount_cb(bypath)

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
            assert value
            assert "cannot mount NTFS, assuming" in msg

    def test_never_destroy_ntfs_config_false(self, patchup, domock_mount_cb):
        """Normally formattable situation with never_destroy_ntfs set."""
        bypath = patchup(
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
        domock_mount_cb(bypath)
        value, msg = dsaz.can_dev_be_reformatted(
            "/dev/sda", preserve_ntfs=True
        )
        assert not value
        assert (
            "config says to never destroy NTFS "
            "(datasource.Azure.never_destroy_ntfs)" in msg
        )


class TestClearCachedData:
    def test_clear_cached_attrs_clears_imds(self, paths):
        """All class attributes are reset to defaults, including imds data."""
        dsrc = dsaz.DataSourceAzure({}, distro=mock.Mock(), paths=paths)
        clean_values = [dsrc.metadata, dsrc.userdata, dsrc._metadata_imds]
        dsrc.metadata = "md"
        dsrc.userdata = "ud"
        dsrc._metadata_imds = "imds"
        dsrc._dirty_cache = True
        dsrc.clear_cached_attrs()
        assert [
            dsrc.metadata,
            dsrc.userdata,
            dsrc._metadata_imds,
        ] == clean_values


class TestAzureNetExists:
    def test_azure_net_must_exist_for_legacy_objpkl(self):
        """DataSourceAzureNet must exist for old obj.pkl files
        that reference it."""
        assert hasattr(dsaz, "DataSourceAzureNet")


class TestPreprovisioningReadAzureOvfFlag:
    def test_read_azure_ovf_with_true_flag(self):
        """The read_azure_ovf method should set the PreprovisionedVM
        cfg flag if the proper setting is present."""
        content = construct_ovf_env(preprovisioned_vm=True)
        ret = dsaz.read_azure_ovf(content)
        cfg = ret[2]
        assert cfg["PreprovisionedVm"]

    def test_read_azure_ovf_with_false_flag(self):
        """The read_azure_ovf method should set the PreprovisionedVM
        cfg flag to false if the proper setting is false."""
        content = construct_ovf_env(preprovisioned_vm=False)
        ret = dsaz.read_azure_ovf(content)
        cfg = ret[2]
        assert not cfg["PreprovisionedVm"]

    def test_read_azure_ovf_without_flag(self):
        """The read_azure_ovf method should not set the
        PreprovisionedVM cfg flag."""
        content = construct_ovf_env()
        ret = dsaz.read_azure_ovf(content)
        cfg = ret[2]
        assert not cfg["PreprovisionedVm"]
        assert None is cfg["PreprovisionedVMType"]

    def test_read_azure_ovf_with_running_type(self):
        """The read_azure_ovf method should set PreprovisionedVMType
        cfg flag to Running."""
        content = construct_ovf_env(
            preprovisioned_vm=True, preprovisioned_vm_type="Running"
        )
        ret = dsaz.read_azure_ovf(content)
        cfg = ret[2]
        assert cfg["PreprovisionedVm"]
        assert "Running" == cfg["PreprovisionedVMType"]

    def test_read_azure_ovf_with_savable_type(self):
        """The read_azure_ovf method should set PreprovisionedVMType
        cfg flag to Savable."""
        content = construct_ovf_env(
            preprovisioned_vm=True, preprovisioned_vm_type="Savable"
        )
        ret = dsaz.read_azure_ovf(content)
        cfg = ret[2]
        assert cfg["PreprovisionedVm"]
        assert "Savable" == cfg["PreprovisionedVMType"]

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


class TestPreprovisioningHotAttachNics:
    @pytest.fixture(autouse=True)
    def fixtures(self, waagent_d):
        dsaz.BUILTIN_DS_CONFIG["data_dir"] = waagent_d

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
        paths,
        fake_socket,
    ):
        """Report ready first and then wait for nic detach"""
        dsa = dsaz.DataSourceAzure({}, distro=None, paths=paths)
        dsa._wait_for_pps_savable_reuse()
        assert 1 == m_report_ready.call_count
        assert 1 == m_wait_for_hot_attached_primary_nic.call_count
        assert 1 == m_detach.call_count
        assert 1 == m_writefile.call_count
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
        paths,
        tmp_path,
        fake_socket,
    ):
        """Wait for nic attach if we do not have a fallback interface.
        Skip waiting for additional nics after we have found primary"""
        distro = mock.MagicMock()
        distro.get_tmp_exec_path = str(tmp_path)
        dsa = dsaz.DataSourceAzure({}, distro=distro, paths=paths)
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

        assert 1 == m_detach.call_count
        # only wait for primary nic
        assert 1 == m_attach.call_count
        # DHCP and network metadata calls will only happen on the primary NIC.
        assert 1 == m_dhcpv4.call_count
        # no call to bring link up on secondary nic
        assert 1 == m_link_up.call_count

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
        dsa = dsaz.DataSourceAzure({}, distro=distro, paths=paths)
        dsa._wait_for_pps_savable_reuse()
        assert 1 == m_detach.call_count
        assert 2 == m_attach.call_count
        assert 2 == m_dhcpv4.call_count
        assert 2 == m_link_up.call_count

    @mock.patch("cloudinit.distros.networking.LinuxNetworking.try_set_link_up")
    def test_wait_for_link_up_returns_if_already_up(self, m_is_link_up, paths):
        """Waiting for link to be up should return immediately if the link is
        already up."""

        distro_cls = distros.fetch("ubuntu")
        distro = distro_cls("ubuntu", {}, paths)
        dsa = dsaz.DataSourceAzure({}, distro=distro, paths=paths)
        m_is_link_up.return_value = True

        dsa.wait_for_link_up("eth0")
        assert 1 == m_is_link_up.call_count

    @mock.patch("cloudinit.distros.networking.LinuxNetworking.try_set_link_up")
    @mock.patch(MOCKPATH + "sleep")
    def test_wait_for_link_up_checks_link_after_sleep(
        self, m_sleep, m_try_set_link_up, paths
    ):
        """Waiting for link to be up should return immediately if the link is
        already up."""

        distro_cls = distros.fetch("ubuntu")
        distro = distro_cls("ubuntu", {}, paths)
        dsa = dsaz.DataSourceAzure({}, distro=distro, paths=paths)
        m_try_set_link_up.return_value = False

        dsa.wait_for_link_up("eth0")

        assert 100 == m_try_set_link_up.call_count
        assert 99 * [mock.call(0.1)] == m_sleep.mock_calls

    @mock.patch(
        "cloudinit.sources.helpers.netlink.create_bound_netlink_socket"
    )
    def test_wait_for_all_nics_ready_raises_if_socket_fails(
        self, m_socket, paths
    ):
        """Waiting for all nics should raise exception if netlink socket
        creation fails."""

        m_socket.side_effect = netlink.NetlinkCreateSocketError
        distro_cls = distros.fetch("ubuntu")
        distro = distro_cls("ubuntu", {}, paths)
        dsa = dsaz.DataSourceAzure({}, distro=distro, paths=paths)

        with pytest.raises(netlink.NetlinkCreateSocketError):
            dsa._wait_for_pps_savable_reuse()


@mock.patch("cloudinit.net.find_fallback_nic", return_value="eth9")
@mock.patch(MOCKPATH + "EphemeralDHCPv4")
@mock.patch(
    "cloudinit.sources.helpers.netlink.wait_for_media_disconnect_connect"
)
@mock.patch(MOCKPATH + "imds.fetch_reprovision_data")
class TestPreprovisioningPollIMDS:
    @pytest.fixture(autouse=True)
    def fixtures(self, waagent_d):
        dsaz.BUILTIN_DS_CONFIG["data_dir"] = waagent_d

    @mock.patch("time.sleep", mock.MagicMock())
    def test_poll_imds_re_dhcp_on_timeout(
        self,
        m_fetch_reprovisiondata,
        m_media_switch,
        m_dhcp,
        m_fallback,
        paths,
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

        dsa = dsaz.DataSourceAzure({}, distro=mock.Mock(), paths=paths)
        dsa._ephemeral_dhcp_ctx = dhcp_ctx
        dsa._poll_imds()

        assert 1 == m_dhcp.call_count, "Expected 1 DHCP calls"
        assert m_fetch_reprovisiondata.call_count == 2

    @mock.patch("os.path.isfile")
    def test_poll_imds_skips_dhcp_if_ctx_present(
        self,
        m_isfile,
        m_fetch_reprovisiondata,
        m_media_switch,
        m_dhcp,
        m_fallback,
        paths,
    ):
        """The poll_imds function should reuse the dhcp ctx if it is already
        present. This happens when we wait for nic to be hot-attached before
        polling for reprovisiondata. Note that if this ctx is set when
        _poll_imds is called, then it is not expected to be waiting for
        media_disconnect_connect either."""
        m_isfile.return_value = True
        dsa = dsaz.DataSourceAzure({}, distro=None, paths=paths)
        dsa._ephemeral_dhcp_ctx = mock.Mock(lease={})
        dsa._poll_imds()
        assert 0 == m_dhcp.call_count
        assert 0 == m_media_switch.call_count

    @mock.patch("os.path.isfile")
    def test_poll_imds_does_dhcp_on_retries_if_ctx_present(
        self,
        m_isfile,
        m_fetch_reprovisiondata,
        m_media_switch,
        m_dhcp,
        m_fallback,
        paths,
        tmp_path,
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
        distro.get_tmp_exec_path = str(tmp_path)
        dsa = dsaz.DataSourceAzure({}, distro=distro, paths=paths)
        with mock.patch.object(dsa, "_ephemeral_dhcp_ctx") as m_dhcp_ctx:
            m_dhcp_ctx.obtain_lease.return_value = "Dummy lease"
            dsa._ephemeral_dhcp_ctx = m_dhcp_ctx
            dsa._poll_imds()
            assert 1 == m_dhcp_ctx.clean_network.call_count
        assert 1 == m_dhcp.call_count
        assert 0 == m_media_switch.call_count
        assert 2 == m_fetch_reprovisiondata.call_count


class TestRemoveUbuntuNetworkConfigScripts:
    def test_remove_network_scripts_removes_both_files_and_directories(
        self, caplog, tmp_path
    ):
        """Any files or directories in paths are removed when present."""
        file1 = tmp_path / "file1"
        subdir = tmp_path / "sub1"
        subfile = subdir / "leaf1"
        write_file(file1, "file1content")
        write_file(subfile, "leafcontent")
        dsaz.maybe_remove_ubuntu_network_config_scripts(paths=[subdir, file1])

        for path in (file1, subdir, subfile):
            assert not os.path.exists(path), "Found unremoved: %s" % path

        expected_logs = [
            (
                mock.ANY,
                logging.INFO,
                "Removing Ubuntu extended network scripts because cloud-init"
                " updates Azure network configuration on the following events:"
                " ['boot', 'boot-legacy'].",
            ),
            (mock.ANY, logging.DEBUG, "Recursively deleting %s" % subdir),
            (mock.ANY, logging.DEBUG, "Attempting to remove %s" % file1),
        ]
        for log in expected_logs:
            assert log in caplog.record_tuples

    def test_remove_network_scripts_only_attempts_removal_if_path_exists(
        self, caplog, tmp_path
    ):
        """Any files or directories absent are skipped without error."""
        dsaz.maybe_remove_ubuntu_network_config_scripts(
            paths=[
                tmp_path / "nodirhere/",
                tmp_path / "notfilehere",
            ]
        )
        assert "/not/a" not in caplog.text  # No delete logs

    # Report path absent on all to avoid delete operation
    @mock.patch(MOCKPATH + "os.path.exists", return_value=False)
    def test_remove_network_scripts_default_removes_stock_scripts(
        self, m_exists
    ):
        """Azure's stock ubuntu image scripts and artifacts are removed."""
        dsaz.maybe_remove_ubuntu_network_config_scripts()
        calls = m_exists.call_args_list
        for path in dsaz.UBUNTU_EXTENDED_NETWORK_SCRIPTS:
            assert mock.call(path) in calls


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


class TestRandomSeed:
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
            pytest.fail("Non-serializable random seed returned")

        assert deserialized["seed"] == result


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

    def test_retry_missing_driver(
        self, azure_ds, caplog, mock_ephemeral_dhcp_v4, mock_sleep
    ):
        lease = {
            "interface": "fakeEth0",
        }
        mock_ephemeral_dhcp_v4.return_value.obtain_lease.side_effect = [
            FileNotFoundError,
            FileNotFoundError,
            lease,
        ]

        azure_ds._setup_ephemeral_networking()

        assert mock_ephemeral_dhcp_v4.return_value.mock_calls == [
            mock.call.obtain_lease(),
            mock.call.obtain_lease(),
            mock.call.obtain_lease(),
        ]
        assert "File not found during DHCP" in caplog.text

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
        mock_kvp_report_via_kvp,
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

        assert len(mock_kvp_report_via_kvp.call_args_list) == 1
        for call in mock_kvp_report_via_kvp.call_args_list:
            assert call[0][0].startswith(
                "result=error|reason=failure to find DHCP interface"
            )

    def test_logging_found_iface_mac_driver(
        self,
        azure_ds,
        mock_find_primary_nic,
        mock_ephemeral_dhcp_v4,
        mock_get_interface_details,
        mock_report_diagnostic_event,
        mock_sleep,
    ):
        mock_get_interface_details.return_value = (
            "00:11:22:33:44:01",
            "unknown",
        )
        azure_ds._setup_ephemeral_networking()

        assert (
            mock.call(
                "Bringing up ephemeral networking with "
                "iface=eth2 mac=00:11:22:33:44:01 driver=unknown: "
                "[('dummy0', '9e:65:d6:19:19:01', None, None), "
                "('enP3', '00:11:22:33:44:02', 'unknown_accel', '0x3'), "
                "('eth0', '00:11:22:33:44:00', 'hv_netvsc', '0x3'), "
                "('eth2', '00:11:22:33:44:01', 'unknown', '0x3'), "
                "('eth3', '00:11:22:33:44:02', "
                "'unknown_with_unknown_vf', '0x3'), "
                "('lo', '00:00:00:00:00:00', None, None)]",
                logger_func=dsaz.LOG.debug,
            )
            in mock_report_diagnostic_event.mock_calls
        )

    def test_retry_process_error(
        self,
        azure_ds,
        mock_find_primary_nic,
        mock_ephemeral_dhcp_v4,
        mock_get_interface_details,
        mock_report_diagnostic_event,
        mock_sleep,
    ):
        mock_find_primary_nic.return_value = "fakeEth0"
        mock_get_interface_details.return_value = (
            "00:11:22:33:44:00",
            "fake_driver",
        )

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
                "Bringing up ephemeral networking with "
                "iface=fakeEth0 mac=00:11:22:33:44:00 driver=fake_driver: "
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
                "Bringing up ephemeral networking with "
                "iface=fakeEth0 mac=00:11:22:33:44:00 driver=fake_driver: "
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
        mock_kvp_report_via_kvp,
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

        assert len(mock_kvp_report_via_kvp.call_args_list) == 10
        for call in mock_kvp_report_via_kvp.call_args_list:
            assert call[0][0].startswith(f"result=error|reason={error_reason}")

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
        mock_kvp_report_via_kvp,
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

        assert len(mock_kvp_report_via_kvp.call_args_list) == 3
        for call in mock_kvp_report_via_kvp.call_args_list:
            assert call[0][0].startswith(f"result=error|reason={error_reason}")

    def test_update_primary_nic_changes_interface(
        self,
        azure_ds,
        mock_ephemeral_dhcp_v4,
        mock_find_primary_nic,
        mock_get_interface_details,
        mock_report_diagnostic_event,
        mock_sleep,
    ):
        """Test that interface updates when update_primary_nic=True.

        When iface=None (update_primary_nic=True), the interface should be
        dynamically discovered via find_primary_nic() on each retry, allowing
        it to change between attempts.
        """
        # the primary NIC gets updated each loop iteration
        mock_find_primary_nic.side_effect = ["eth0", "eth1", "eth2"]

        mock_get_interface_details.side_effect = [
            ("00:11:22:33:44:00", "hv_netvsc"),  # eth0
            ("00:11:22:33:44:01", "unknown1"),  # eth1
            ("00:11:22:33:44:02", "unknown2"),  # eth2 (final success)
        ]

        lease = {
            "interface": "eth2",
        }
        mock_ephemeral_dhcp_v4.return_value.obtain_lease.side_effect = [
            dhcp.NoDHCPLeaseError(),
            dhcp.NoDHCPLeaseError(),
            lease,
        ]

        azure_ds._setup_ephemeral_networking(iface=None)

        assert mock_find_primary_nic.call_count == 3

        assert mock_get_interface_details.mock_calls == [
            mock.call("eth0"),
            mock.call("eth1"),
            mock.call("eth2"),
        ]

        assert mock_ephemeral_dhcp_v4.return_value.iface == "eth2"
        assert mock_ephemeral_dhcp_v4.return_value.obtain_lease.call_count == 3

        # Verify the diagnostic messages in order, ignoring dynamic values
        expected = [
            (
                "Bringing up ephemeral networking with "
                "iface=eth0 mac=00:11:22:33:44:00 driver=hv_netvsc",
                dsaz.LOG.debug,
            ),
            (
                "Failed to obtain DHCP lease "
                "(iface=eth0 mac=00:11:22:33:44:00 driver=hv_netvsc)",
                dsaz.LOG.error,
            ),
            (
                [
                    "Azure datasource failure occurred",
                    "driver=hv_netvsc",
                    "interface=eth0",
                    "mac_address=00:11:22:33:44:00",
                ],
                dsaz.LOG.error,
            ),
            (
                "Bringing up ephemeral networking with iface=eth1 "
                "mac=00:11:22:33:44:01 driver=unknown1",
                dsaz.LOG.debug,
            ),
            (
                "Failed to obtain DHCP lease "
                "(iface=eth1 mac=00:11:22:33:44:01 driver=unknown1)",
                dsaz.LOG.error,
            ),
            (
                [
                    "Azure datasource failure occurred",
                    "driver=unknown1",
                    "interface=eth1",
                    "mac_address=00:11:22:33:44:01",
                ],
                dsaz.LOG.error,
            ),
            (
                "Bringing up ephemeral networking with "
                "iface=eth2 mac=00:11:22:33:44:02 driver=unknown2",
                dsaz.LOG.debug,
            ),
            (
                [
                    "Obtained DHCP lease on interface 'eth2'",
                    "driver='fake_driver'",
                    "primary=True",
                ],
                dsaz.LOG.debug,
            ),
        ]

        assert mock_report_diagnostic_event.call_count == 8
        calls = mock_report_diagnostic_event.call_args_list
        for i, (expected_msg, expected_logger) in enumerate(expected):
            actual_msg = calls[i][0][0]
            if isinstance(expected_msg, list):
                for fragment in expected_msg:
                    assert (
                        fragment in actual_msg
                    ), f"Call {i}: expected '{fragment}' in message"
            else:
                assert (
                    expected_msg in actual_msg
                ), f"Call {i}: expected message to contain '{expected_msg}'"
            assert (
                calls[i][1]["logger_func"] == expected_logger
            ), f"Call {i}: wrong logger level"

        # Final ephemeral dhcp context should have eth2
        assert azure_ds._ephemeral_dhcp_ctx.iface == "eth2"


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
        mock_kvp_report_via_kvp,
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
        self.mock_kvp_report_via_kvp = mock_kvp_report_via_kvp
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
        ovf = construct_ovf_env(provision_guest_proxy_agent=False)
        md, ud, cfg = dsaz.read_azure_ovf(ovf)
        self.mock_util_mount_cb.return_value = (md, ud, cfg, {})
        self.mock_readurl.side_effect = [
            mock.MagicMock(contents=json.dumps(self.imds_md).encode()),
        ]
        self.mock_azure_get_metadata_from_fabric.return_value = []

        self.azure_ds._check_and_get_data()

        assert self.mock_subp_subp.mock_calls == []

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
        assert not self.mock_kvp_report_via_kvp.mock_calls
        assert not self.mock_azure_report_failure_to_fabric.mock_calls
        assert len(self.mock_kvp_report_success_to_host.mock_calls) == 1

        # Verify dmesg reported via KVP.
        assert len(self.mock_report_dmesg_to_kvp.mock_calls) == 1

    def test_no_pps_gpa(self):
        """test full provisioning scope when azure-proxy-agent
        is enabled and running."""
        self.mock_subp_subp.side_effect = [
            subp.SubpResult("Guest Proxy Agent running", ""),
        ]
        ovf = construct_ovf_env(provision_guest_proxy_agent=True)
        md, ud, cfg = dsaz.read_azure_ovf(ovf)
        self.mock_util_mount_cb.return_value = (md, ud, cfg, {})
        self.mock_readurl.side_effect = [
            mock.MagicMock(contents=json.dumps(self.imds_md).encode()),
        ]
        self.mock_azure_get_metadata_from_fabric.return_value = []

        self.azure_ds._check_and_get_data()

        assert self.mock_subp_subp.mock_calls == [
            mock.call(
                ["azure-proxy-agent", "--status", "--wait", "120"],
            ),
        ]
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
        assert not self.mock_kvp_report_via_kvp.mock_calls
        assert not self.mock_azure_report_failure_to_fabric.mock_calls
        assert len(self.mock_kvp_report_success_to_host.mock_calls) == 1

        # Verify dmesg reported via KVP.
        assert len(self.mock_report_dmesg_to_kvp.mock_calls) == 1

    def test_no_pps_gpa_fail(self):
        """test full provisioning scope when azure-proxy-agent is enabled and
        throwing an exception during provisioning."""
        self.mock_subp_subp.side_effect = [
            subp.ProcessExecutionError(
                cmd=["failed", "azure-proxy-agent"],
                stdout="test_stdout",
                stderr="test_stderr",
                exit_code=4,
            ),
        ]
        ovf = construct_ovf_env(provision_guest_proxy_agent=True)
        md, ud, cfg = dsaz.read_azure_ovf(ovf)
        self.mock_util_mount_cb.return_value = (md, ud, cfg, {})
        self.mock_readurl.side_effect = [
            mock.MagicMock(contents=json.dumps(self.imds_md).encode()),
        ]
        self.mock_azure_get_metadata_from_fabric.return_value = []

        self.azure_ds._check_and_get_data()

        assert self.mock_subp_subp.mock_calls == [
            mock.call(
                ["azure-proxy-agent", "--status", "--wait", "120"],
            ),
        ]
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
        assert self.mock_azure_get_metadata_from_fabric.mock_calls == []

        # Verify netlink.
        assert self.mock_netlink.mock_calls == []

        # Verify no reported_ready marker written.
        assert self.wrapped_util_write_file.mock_calls == []
        assert self.patched_reported_ready_marker_path.exists() is False

        # Verify reports via KVP.
        assert len(self.mock_kvp_report_via_kvp.mock_calls) == 1
        assert len(self.mock_azure_report_failure_to_fabric.mock_calls) == 1
        assert not self.mock_kvp_report_success_to_host.mock_calls

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
        ]

        # Verify reports via KVP.
        assert len(self.mock_kvp_report_success_to_host.mock_calls) == 1

        assert self.mock_kvp_report_via_kvp.mock_calls == [
            mock.call(
                errors.ReportableErrorImdsInvalidMetadata(
                    key="extended.compute.ppsType", value=pps_type
                ).as_encoded_report(vm_id=self.azure_ds._vm_id),
            ),
        ]

    def test_running_pps(self):
        imds_md_source = copy.deepcopy(self.imds_md)
        imds_md_source["extended"]["compute"]["ppsType"] = "Running"

        nl_sock = mock.MagicMock()
        self.mock_netlink.create_bound_netlink_socket.return_value = nl_sock
        self.mock_readurl.side_effect = [
            mock.MagicMock(contents=json.dumps(imds_md_source).encode()),
            mock.MagicMock(
                contents=construct_ovf_env(
                    provision_guest_proxy_agent=False
                ).encode()
            ),
            mock.MagicMock(contents=json.dumps(self.imds_md).encode()),
        ]
        self.mock_azure_get_metadata_from_fabric.return_value = []

        self.azure_ds._check_and_get_data()

        assert self.mock_subp_subp.mock_calls == []

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
        assert not self.mock_kvp_report_via_kvp.mock_calls
        assert len(self.mock_kvp_report_success_to_host.mock_calls) == 2

        # Verify dmesg reported via KVP.
        assert len(self.mock_report_dmesg_to_kvp.mock_calls) == 2

    def test_running_pps_gpa(self):
        self.mock_subp_subp.side_effect = [
            subp.SubpResult("Guest Proxy Agent running", ""),
        ]
        imds_md_source = copy.deepcopy(self.imds_md)
        imds_md_source["extended"]["compute"]["ppsType"] = "Running"

        nl_sock = mock.MagicMock()
        self.mock_netlink.create_bound_netlink_socket.return_value = nl_sock
        self.mock_readurl.side_effect = [
            mock.MagicMock(contents=json.dumps(imds_md_source).encode()),
            mock.MagicMock(
                contents=construct_ovf_env(
                    provision_guest_proxy_agent=True
                ).encode()
            ),
            mock.MagicMock(contents=json.dumps(self.imds_md).encode()),
        ]
        self.mock_azure_get_metadata_from_fabric.return_value = []

        self.azure_ds._check_and_get_data()

        assert self.mock_subp_subp.mock_calls == [
            mock.call(
                ["azure-proxy-agent", "--status", "--wait", "120"],
            ),
        ]

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
        assert not self.mock_kvp_report_via_kvp.mock_calls
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
            mock.MagicMock(
                contents=construct_ovf_env(
                    provision_guest_proxy_agent=False
                ).encode()
            ),
            mock.MagicMock(contents=json.dumps(self.imds_md).encode()),
        ]
        self.mock_azure_get_metadata_from_fabric.return_value = []

        self.azure_ds._check_and_get_data()

        assert self.mock_subp_subp.mock_calls == []

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
        assert not self.mock_kvp_report_via_kvp.mock_calls
        assert len(self.mock_kvp_report_success_to_host.mock_calls) == 2

        # Verify dmesg reported via KVP.
        assert len(self.mock_report_dmesg_to_kvp.mock_calls) == 2

    def test_savable_pps_gpa(self):
        self.mock_subp_subp.side_effect = [
            subp.SubpResult("Guest Proxy Agent running", ""),
        ]
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
            mock.MagicMock(
                contents=construct_ovf_env(
                    provision_guest_proxy_agent=True
                ).encode()
            ),
            mock.MagicMock(contents=json.dumps(self.imds_md).encode()),
        ]
        self.mock_azure_get_metadata_from_fabric.return_value = []

        self.azure_ds._check_and_get_data()

        assert self.mock_subp_subp.mock_calls == [
            mock.call(
                ["azure-proxy-agent", "--status", "--wait", "120"],
            ),
        ]

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
        assert not self.mock_kvp_report_via_kvp.mock_calls
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
        assert not self.mock_kvp_report_via_kvp.mock_calls
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
        assert len(self.mock_kvp_report_via_kvp.mock_calls) == 2
        assert not self.mock_kvp_report_success_to_host.mock_calls

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
        assert len(self.mock_kvp_report_via_kvp.mock_calls) == 1
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
        assert len(self.mock_kvp_report_via_kvp.mock_calls) == 1
        assert not self.mock_kvp_report_success_to_host.mock_calls


class TestCheckAzureProxyAgent:
    @pytest.fixture(autouse=True)
    def proxy_setup(
        self,
        azure_ds,
        mock_subp_subp,
        caplog,
        mock_wrapping_report_failure,
        mock_timestamp,
    ):
        self.azure_ds = azure_ds
        self.mock_subp_subp = mock_subp_subp
        self.caplog = caplog
        self.mock_wrapping_report_failure = mock_wrapping_report_failure
        self.mock_timestamp = mock_timestamp

    def test_check_azure_proxy_agent_status(self):
        self.mock_subp_subp.side_effect = [
            subp.SubpResult("Guest Proxy Agent running", ""),
        ]
        self.azure_ds._check_azure_proxy_agent_status()
        assert (
            "Executing ['azure-proxy-agent', '--status', '--wait', '120']"
            in self.caplog.text
        )
        assert self.mock_wrapping_report_failure.mock_calls == []

    def test_check_azure_proxy_agent_status_notfound(self):
        exception = subp.ProcessExecutionError(reason=FileNotFoundError())
        self.mock_subp_subp.side_effect = [
            exception,
        ]
        self.azure_ds._check_azure_proxy_agent_status()
        assert "azure-proxy-agent not found" in self.caplog.text
        assert self.mock_wrapping_report_failure.mock_calls == [
            mock.call(
                errors.ReportableErrorProxyAgentNotFound(),
            ),
        ]

    def test_check_azure_proxy_agent_status_failure(self):
        exception = subp.ProcessExecutionError(
            cmd=["failed", "azure-proxy-agent"],
            stdout="test_stdout",
            stderr="test_stderr",
            exit_code=4,
        )
        self.mock_subp_subp.side_effect = [
            exception,
        ]
        self.azure_ds._check_azure_proxy_agent_status()
        assert "azure-proxy-agent status failure" in self.caplog.text
        assert self.mock_wrapping_report_failure.mock_calls == [
            mock.call(
                errors.ReportableErrorProxyAgentStatusFailure(
                    exception=exception
                ),
            ),
        ]


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
        mock_kvp_report_via_kvp,
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

        reported_error = mock_kvp_report_via_kvp.call_args[0][0]
        assert type(exception).__name__ in reported_error

        connection_error = isinstance(
            exception, url_helper.UrlError
        ) and isinstance(exception.cause, requests.ConnectionError)
        report_skipped = not route_configured_for_imds and connection_error
        if report_failure and not report_skipped:
            assert mock_azure_report_failure_to_fabric.mock_calls == [
                mock.call(endpoint=mock.ANY, encoded_report=reported_error)
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
        mock_kvp_report_via_kvp,
        mock_kvp_report_success_to_host,
        mock_report_dmesg_to_kvp,
    ):
        mock_kvp_report_via_kvp.return_value = kvp_enabled
        error = errors.ReportableError(reason="foo")

        assert azure_ds._report_failure(error, host_only=True) == kvp_enabled

        assert mock_kvp_report_via_kvp.mock_calls == [
            mock.call(error.as_encoded_report(vm_id=azure_ds._vm_id))
        ]
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


class TestQueryVmId:
    @mock.patch.object(
        identity, "query_system_uuid", side_effect=["test-system-uuid"]
    )
    @mock.patch.object(
        identity, "convert_system_uuid_to_vm_id", side_effect=["test-vm-id"]
    )
    def test_query_vm_id_success(
        self, mock_convert_uuid, mock_query_system_uuid, azure_ds
    ):
        azure_ds._query_vm_id()

        assert azure_ds._system_uuid == "test-system-uuid"
        assert azure_ds._vm_id == "test-vm-id"

        mock_query_system_uuid.assert_called_once()
        mock_convert_uuid.assert_called_once_with("test-system-uuid")

    @mock.patch.object(
        identity,
        "query_system_uuid",
        side_effect=[RuntimeError("test failure")],
    )
    def test_query_vm_id_system_uuid_failure(
        self, mock_query_system_uuid, azure_ds
    ):
        with pytest.raises(errors.ReportableErrorVmIdentification) as exc_info:
            azure_ds._query_vm_id()

            assert azure_ds._system_uuid is None
            assert azure_ds._vm_id is None
            assert (
                exc_info.value.reason
                == "Failed to query system UUID: test failure"
            )

        mock_query_system_uuid.assert_called_once()

    @mock.patch.object(
        identity, "query_system_uuid", side_effect=["test-system-uuid"]
    )
    @mock.patch.object(
        identity,
        "convert_system_uuid_to_vm_id",
        side_effect=[ValueError("test failure")],
    )
    def test_query_vm_id_vm_id_conversion_failure(
        self, mock_convert_uuid, mock_query_system_uuid, azure_ds
    ):
        with pytest.raises(errors.ReportableErrorVmIdentification) as excinfo:
            azure_ds._query_vm_id()

            assert azure_ds._system_uuid == "test-system-uuid"
            assert azure_ds._vm_id is None
            assert (
                excinfo.value.reason
                == "Failed to convert system UUID 'test-system-uuid' "
                "to Azure VM ID: test failure"
            )

        mock_query_system_uuid.assert_called_once()
        mock_convert_uuid.assert_called_once_with("test-system-uuid")


class TestHashPassword:
    """Tests for the hash_password function."""

    def test_dependency_fallback(self):
        """Ensure that crypt/passlib import failover gets exercised on all
        Python versions
        """
        result = dsaz.hash_password("`")
        assert result
        assert result.startswith("$6$")

    def test_crypt_working(self):
        """Test that hash_password uses crypt when available."""
        mock_crypt = mock.MagicMock()
        mock_crypt.METHOD_SHA512 = "sha512"
        mock_crypt.mksalt.return_value = "$6$saltvalue"
        mock_crypt.crypt.return_value = "$6$saltvalue$hashedpassword"

        with mock.patch.dict("sys.modules", {"crypt": mock_crypt}):
            result = dsaz.hash_password("testpassword")

        mock_crypt.mksalt.assert_called_once_with("sha512")
        mock_crypt.crypt.assert_called_once_with(
            "testpassword", "$6$saltvalue"
        )
        assert result == "$6$saltvalue$hashedpassword"

    def test_crypt_not_installed_passlib_fallback(self):
        """Test that hash_password falls back to passlib when missing crypt."""
        real_import = builtins.__import__
        passlib_available = True
        try:
            import passlib.hash as _passlib_hash
        except ImportError:
            passlib_available = False

        if passlib_available:
            # passlib is installed; block crypt and let passlib work normally
            def mock_import(name, *args, **kwargs):
                if name == "crypt":
                    raise ImportError("No module named 'crypt'")
                return real_import(name, *args, **kwargs)

            with mock.patch.object(
                builtins, "__import__", side_effect=mock_import
            ):
                result = dsaz.hash_password("testpassword")

            # Verify we got a valid SHA-512 hash from passlib
            assert result.startswith("$6$")
            assert _passlib_hash.sha512_crypt.verify("testpassword", result)
        else:
            # passlib is not installed; mock it to return a known hash
            mock_passlib_hash = mock.MagicMock()
            mock_passlib_hash.sha512_crypt.hash.return_value = (
                "$6$mocksalt$mockedhash"
            )

            def mock_import(name, *args, **kwargs):
                if name == "crypt":
                    raise ImportError("No module named 'crypt'")
                if name == "passlib.hash":
                    mod = mock.MagicMock()
                    mod.hash = mock_passlib_hash
                    sys.modules["passlib"] = mod
                    sys.modules["passlib.hash"] = mock_passlib_hash
                    return mod
                return real_import(name, *args, **kwargs)

            with mock.patch.object(
                builtins, "__import__", side_effect=mock_import
            ):
                result = dsaz.hash_password("testpassword")

            assert result == "$6$mocksalt$mockedhash"
            mock_passlib_hash.sha512_crypt.hash.assert_called_once_with(
                "testpassword"
            )

    def test_crypt_and_passlib_unavailable_raises_error(self):
        """Test that hash_password raises ReportableErrorImportError."""
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "crypt":
                raise ImportError("No module named 'crypt'")
            if name == "passlib.hash":
                raise ImportError("No module named 'passlib'", name="passlib")
            return real_import(name, *args, **kwargs)

        with mock.patch.object(
            builtins, "__import__", side_effect=mock_import
        ):
            with pytest.raises(errors.ReportableErrorImportError) as exc_info:
                dsaz.hash_password("testpassword")

            assert "passlib" in exc_info.value.reason
