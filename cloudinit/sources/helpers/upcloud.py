# Author: Antti Myyrä <antti.myyra@upcloud.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import json

from cloudinit import dmi
from cloudinit import log as logging
from cloudinit import net as cloudnet
from cloudinit import url_helper

LOG = logging.getLogger(__name__)


def convert_to_network_config_v1(config):
    """
    Convert the UpCloud network metadata description into
    Cloud-init's version 1 netconfig format.

    Example JSON:
    {
      "interfaces": [
        {
          "index": 1,
          "ip_addresses": [
            {
              "address": "94.237.105.53",
              "dhcp": true,
              "dns": [
                "94.237.127.9",
                "94.237.40.9"
              ],
              "family": "IPv4",
              "floating": false,
              "gateway": "94.237.104.1",
              "network": "94.237.104.0/22"
            },
            {
              "address": "94.237.105.50",
              "dhcp": false,
              "dns": [],
              "family": "IPv4",
              "floating": true,
              "gateway": "",
              "network": "94.237.105.50/32"
            }
          ],
          "mac": "32:d5:ba:4a:36:e7",
          "network_id": "031457f4-0f8c-483c-96f2-eccede02909c",
          "type": "public"
        },
        {
          "index": 2,
          "ip_addresses": [
            {
              "address": "10.6.3.27",
              "dhcp": true,
              "dns": [],
              "family": "IPv4",
              "floating": false,
              "gateway": "10.6.0.1",
              "network": "10.6.0.0/22"
            }
          ],
          "mac": "32:d5:ba:4a:84:cc",
          "network_id": "03d82553-5bea-4132-b29a-e1cf67ec2dd1",
          "type": "utility"
        },
        {
          "index": 3,
          "ip_addresses": [
            {
              "address": "2a04:3545:1000:720:38d6:baff:fe4a:63e7",
              "dhcp": true,
              "dns": [
                "2a04:3540:53::1",
                "2a04:3544:53::1"
              ],
              "family": "IPv6",
              "floating": false,
              "gateway": "2a04:3545:1000:720::1",
              "network": "2a04:3545:1000:720::/64"
            }
          ],
          "mac": "32:d5:ba:4a:63:e7",
          "network_id": "03000000-0000-4000-8046-000000000000",
          "type": "public"
        },
        {
          "index": 4,
          "ip_addresses": [
            {
              "address": "172.30.1.10",
              "dhcp": true,
              "dns": [],
              "family": "IPv4",
              "floating": false,
              "gateway": "172.30.1.1",
              "network": "172.30.1.0/24"
            }
          ],
          "mac": "32:d5:ba:4a:8a:e1",
          "network_id": "035a0a4a-77b4-4de5-820d-189fc8135714",
          "type": "private"
        }
      ],
      "dns": [
        "94.237.127.9",
        "94.237.40.9"
      ]
    }
    """

    def _get_subnet_config(ip_addr, dns):
        if ip_addr.get("dhcp"):
            dhcp_type = "dhcp"
            if ip_addr.get("family") == "IPv6":
                # UpCloud currently passes IPv6 addresses via
                # StateLess Address Auto Configuration (SLAAC)
                dhcp_type = "ipv6_dhcpv6-stateless"
            return {"type": dhcp_type}

        static_type = "static"
        if ip_addr.get("family") == "IPv6":
            static_type = "static6"
        subpart = {
            "type": static_type,
            "control": "auto",
            "address": ip_addr.get("address"),
        }

        if ip_addr.get("gateway"):
            subpart["gateway"] = ip_addr.get("gateway")

        if "/" in ip_addr.get("network"):
            subpart["netmask"] = ip_addr.get("network").split("/")[1]

        if dns != ip_addr.get("dns") and ip_addr.get("dns"):
            subpart["dns_nameservers"] = ip_addr.get("dns")

        return subpart

    nic_configs = []
    macs_to_interfaces = cloudnet.get_interfaces_by_mac()
    LOG.debug("NIC mapping: %s", macs_to_interfaces)

    for raw_iface in config.get("interfaces"):
        LOG.debug("Considering %s", raw_iface)

        mac_address = raw_iface.get("mac")
        if mac_address not in macs_to_interfaces:
            raise RuntimeError(
                "Did not find network interface on system "
                "with mac '%s'. Cannot apply configuration: %s"
                % (mac_address, raw_iface)
            )

        iface_type = raw_iface.get("type")
        sysfs_name = macs_to_interfaces.get(mac_address)

        LOG.debug(
            "Found %s interface '%s' with address '%s' (index %d)",
            iface_type,
            sysfs_name,
            mac_address,
            raw_iface.get("index"),
        )

        interface = {
            "type": "physical",
            "name": sysfs_name,
            "mac_address": mac_address,
        }

        subnets = []
        for ip_address in raw_iface.get("ip_addresses"):
            sub_part = _get_subnet_config(ip_address, config.get("dns"))
            subnets.append(sub_part)

        interface["subnets"] = subnets
        nic_configs.append(interface)

    if config.get("dns"):
        LOG.debug("Setting DNS nameservers to %s", config.get("dns"))
        nic_configs.append(
            {"type": "nameserver", "address": config.get("dns")}
        )

    return {"version": 1, "config": nic_configs}


def convert_network_config(config):
    return convert_to_network_config_v1(config)


def read_metadata(url, timeout=2, sec_between=2, retries=30):
    response = url_helper.readurl(
        url, timeout=timeout, sec_between=sec_between, retries=retries
    )
    if not response.ok():
        raise RuntimeError("unable to read metadata at %s" % url)
    return json.loads(response.contents.decode())


def read_sysinfo():
    # UpCloud embeds vendor ID and server UUID in the
    # SMBIOS information

    # Detect if we are on UpCloud and return the UUID

    vendor_name = dmi.read_dmi_data("system-manufacturer")
    if vendor_name != "UpCloud":
        return False, None

    server_uuid = dmi.read_dmi_data("system-uuid")
    if server_uuid:
        LOG.debug(
            "system identified via SMBIOS as UpCloud server: %s", server_uuid
        )
    else:
        msg = (
            "system identified via SMBIOS as a UpCloud server, but "
            "did not provide an ID. Please contact support via"
            "https://hub.upcloud.com or via email with support@upcloud.com"
        )
        LOG.critical(msg)
        raise RuntimeError(msg)

    return True, server_uuid
