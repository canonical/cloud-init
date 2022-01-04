# This file is part of cloud-init. See LICENSE file for license information.
# ./cloudinit/sources/helpers/tests/test_openstack.py
from unittest import mock

from cloudinit.sources.helpers import openstack
from tests.unittests import helpers as test_helpers


@mock.patch(
    "cloudinit.net.is_openvswitch_internal_interface",
    mock.Mock(return_value=False),
)
class TestConvertNetJson(test_helpers.CiTestCase):
    def test_phy_types(self):
        """Verify the different known physical types are handled."""
        # network_data.json example from
        # https://docs.openstack.org/nova/latest/user/metadata.html
        mac0 = "fa:16:3e:9c:bf:3d"
        net_json = {
            "links": [
                {
                    "ethernet_mac_address": mac0,
                    "id": "tapcd9f6d46-4a",
                    "mtu": None,
                    "type": "bridge",
                    "vif_id": "cd9f6d46-4a3a-43ab-a466-994af9db96fc",
                }
            ],
            "networks": [
                {
                    "id": "network0",
                    "link": "tapcd9f6d46-4a",
                    "network_id": "99e88329-f20d-4741-9593-25bf07847b16",
                    "type": "ipv4_dhcp",
                }
            ],
            "services": [{"address": "8.8.8.8", "type": "dns"}],
        }
        macs = {mac0: "eth0"}

        expected = {
            "version": 1,
            "config": [
                {
                    "mac_address": "fa:16:3e:9c:bf:3d",
                    "mtu": None,
                    "name": "eth0",
                    "subnets": [{"type": "dhcp4"}],
                    "type": "physical",
                },
                {"address": "8.8.8.8", "type": "nameserver"},
            ],
        }

        for t in openstack.KNOWN_PHYSICAL_TYPES:
            net_json["links"][0]["type"] = t
            self.assertEqual(
                expected,
                openstack.convert_net_json(
                    network_json=net_json, known_macs=macs
                ),
            )
