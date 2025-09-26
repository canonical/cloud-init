# This file is part of cloud-init. See LICENSE file for license information.

import logging
from typing import MutableMapping

from cloudinit import net, url_helper, util
from cloudinit.sources.helpers import ec2

LOG = logging.getLogger(__name__)


def get_instance_meta_data(
    api_version="latest",
    metadata_address="http://100.100.100.200",
    ssl_details=None,
    timeout=5,
    retries=5,
    headers_cb=None,
    headers_redact=None,
    exception_cb=None,
):
    ud_url = url_helper.combine_url(metadata_address, api_version)
    ud_url = url_helper.combine_url(ud_url, "meta-data/all")
    response = url_helper.read_file_or_url(
        ud_url,
        ssl_details=ssl_details,
        timeout=timeout,
        retries=retries,
        exception_cb=exception_cb,
        headers_cb=headers_cb,
        headers_redact=headers_redact,
    )
    meta_data_raw: object = util.load_json(response.contents)

    # meta_data_raw is a json object with the following format get
    # by`meta-data/all`
    # {
    #   "sub-private-ipv4-list": "",
    #   "dns-conf": {
    #     "nameservers": "100.100.2.136\r\n100.100.2.138"
    #   },
    #   "zone-id": "cn-hangzhou-i",
    #   "instance": {
    #     "instance-name": "aliyun_vm_test",
    #     "instance-type": "ecs.g7.xlarge"
    #   },
    #   "disks": {
    #     "bp1cikh4di1xxxx": {
    #       "name": "disk_test",
    #       "id": "d-bp1cikh4di1lf7pxxxx"
    #     }
    #   },
    #   "instance-id": "i-bp123",
    #   "eipv4": "47.99.152.7",
    #   "private-ipv4": "192.168.0.9",
    #   "hibernation": {
    #     "configured": "false"
    #   },
    #   "vpc-id": "vpc-bp1yeqg123",
    #   "mac": "00:16:3e:30:3e:ca",
    #   "source-address": "http://mirrors.cloud.aliyuncs.com",
    #   "vswitch-cidr-block": "192.168.0.0/24",
    #   "network": {
    #     "interfaces": {
    #       "macs": {
    #         "00:16:3e:30:3e:ca": {
    #           "vpc-cidr-block": "192.168.0.0/16",
    #           "netmask": "255.255.255.0"
    #         }
    #       }
    #     }
    #   },
    #   "network-type": "vpc",
    #   "hostname": "aliyun_vm_test",
    #   "region-id": "cn-hangzhou",
    #   "ntp-conf": {
    #     "ntp-servers": "ntp1.aliyun.com\r\nntp2.aliyun.com"
    #   },
    # }
    # Note: For example, in the values of dns conf: the `nameservers`
    # key is a string, the format is the same as the response from the
    # `meta-data/dns-conf/nameservers` endpoint. we use the same
    # serialization method to ensure consistency between
    # the two methods (directory tree and json path).
    def _process_dict_values(d):
        if isinstance(d, dict):
            return {k: _process_dict_values(v) for k, v in d.items()}
        elif isinstance(d, list):
            return [_process_dict_values(item) for item in d]
        else:
            return ec2.MetadataLeafDecoder()("", d)

    return _process_dict_values(meta_data_raw)


def get_instance_data(
    api_version="latest",
    metadata_address="http://100.100.100.200",
    ssl_details=None,
    timeout=5,
    retries=5,
    headers_cb=None,
    headers_redact=None,
    exception_cb=None,
    item_name=None,
):
    ud_url = url_helper.combine_url(metadata_address, api_version)
    ud_url = url_helper.combine_url(ud_url, item_name)
    data = b""
    support_items_list = ["user-data", "vendor-data"]
    if item_name not in support_items_list:
        LOG.error(
            "aliyun datasource not support the item  %s",
            item_name,
        )
        return data
    try:
        response = url_helper.read_file_or_url(
            ud_url,
            ssl_details=ssl_details,
            timeout=timeout,
            retries=retries,
            exception_cb=exception_cb,
            headers_cb=headers_cb,
            headers_redact=headers_redact,
        )
        data = response.contents
    except Exception:
        util.logexc(LOG, "Failed fetching %s from url %s", item_name, ud_url)
    return data


def convert_ecs_metadata_network_config(
    network_md,
    macs_to_nics=None,
    fallback_nic=None,
    full_network_config=True,
):
    """Convert ecs metadata to network config version 2 data dict.

    @param: network_md: 'network' portion of ECS metadata.
    generally formed as {"interfaces": {"macs": {}} where
    'macs' is a dictionary with mac address as key:
    @param: macs_to_nics: Optional dict of mac addresses and nic names. If
    not provided, get_interfaces_by_mac is called to get it from the OS.
    @param: fallback_nic: Optionally provide the primary nic interface name.
    This nic will be guaranteed to minimally have a dhcp4 configuration.
    @param: full_network_config: Boolean set True to configure all networking
    presented by IMDS. This includes rendering secondary IPv4 and IPv6
    addresses on all NICs and rendering network config on secondary NICs.
    If False, only the primary nic will be configured and only with dhcp
    (IPv4/IPv6).

    @return A dict of network config version 2 based on the metadata and macs.
    """
    netcfg: MutableMapping = {"version": 2, "ethernets": {}}
    if not macs_to_nics:
        macs_to_nics = net.get_interfaces_by_mac()
    macs_metadata = network_md["interfaces"]["macs"]

    if not full_network_config:
        for mac, nic_name in macs_to_nics.items():
            if nic_name == fallback_nic:
                break
        dev_config: MutableMapping = {
            "dhcp4": True,
            "dhcp6": False,
            "match": {"macaddress": mac.lower()},
            "set-name": nic_name,
        }
        nic_metadata = macs_metadata.get(mac)
        if nic_metadata.get("ipv6s"):  # Any IPv6 addresses configured
            dev_config["dhcp6"] = True
        netcfg["ethernets"][nic_name] = dev_config
        return netcfg
    nic_name_2_mac_map = dict()
    for mac, nic_name in macs_to_nics.items():
        nic_metadata = macs_metadata.get(mac)
        if not nic_metadata:
            continue  # Not a physical nic represented in metadata
        nic_name_2_mac_map[nic_name] = mac

    # sorted by nic_name
    ordered_nic_name_list = sorted(
        nic_name_2_mac_map.keys(), key=net.natural_sort_key
    )
    for nic_idx, nic_name in enumerate(ordered_nic_name_list):
        nic_mac = nic_name_2_mac_map[nic_name]
        nic_metadata = macs_metadata.get(nic_mac)
        dhcp_override = {"route-metric": (nic_idx + 1) * 100}
        dev_config = {
            "dhcp4": True,
            "dhcp4-overrides": dhcp_override,
            "dhcp6": False,
            "match": {"macaddress": nic_mac.lower()},
            "set-name": nic_name,
        }
        if nic_metadata.get("ipv6s"):  # Any IPv6 addresses configured
            dev_config["dhcp6"] = True
            dev_config["dhcp6-overrides"] = dhcp_override

        netcfg["ethernets"][nic_name] = dev_config
    # Remove route-metric dhcp overrides and routes / routing-policy if only
    # one nic configured
    if len(netcfg["ethernets"]) == 1:
        for nic_name in netcfg["ethernets"].keys():
            netcfg["ethernets"][nic_name].pop("dhcp4-overrides")
            netcfg["ethernets"][nic_name].pop("dhcp6-overrides", None)
            netcfg["ethernets"][nic_name].pop("routes", None)
            netcfg["ethernets"][nic_name].pop("routing-policy", None)
    return netcfg
