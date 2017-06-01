#!/usr/bin/python3
# This file is part of cloud-init. See LICENSE file for license information.

import argparse
import json
import os
import yaml

from cloudinit.sources.helpers import openstack

from cloudinit.net import eni
from cloudinit.net import netplan
from cloudinit.net import network_state
from cloudinit.net import sysconfig


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--network-data", "-p", type=open,
                        metavar="PATH", required=True)
    parser.add_argument("--kind", "-k",
                        choices=['eni', 'network_data.json', 'yaml'],
                        required=True)
    parser.add_argument("-d", "--directory",
                        metavar="PATH",
                        help="directory to place output in",
                        required=True)
    parser.add_argument("-m", "--mac",
                        metavar="name,mac",
                        action='append',
                        help="interface name to mac mapping")
    parser.add_argument("--output-kind", "-ok",
                        choices=['eni', 'netplan', 'sysconfig'],
                        required=True)
    args = parser.parse_args()

    if not os.path.isdir(args.directory):
        os.makedirs(args.directory)

    if args.mac:
        known_macs = {}
        for item in args.mac:
            iface_name, iface_mac = item.split(",", 1)
            known_macs[iface_mac] = iface_name
    else:
        known_macs = None

    net_data = args.network_data.read()
    if args.kind == "eni":
        pre_ns = eni.convert_eni_data(net_data)
        ns = network_state.parse_net_config_data(pre_ns)
    elif args.kind == "yaml":
        pre_ns = yaml.load(net_data)
        if 'network' in pre_ns:
            pre_ns = pre_ns.get('network')
        print("Input YAML")
        print(yaml.dump(pre_ns, default_flow_style=False, indent=4))
        ns = network_state.parse_net_config_data(pre_ns)
    else:
        pre_ns = openstack.convert_net_json(
            json.loads(net_data), known_macs=known_macs)
        ns = network_state.parse_net_config_data(pre_ns)

    if not ns:
        raise RuntimeError("No valid network_state object created from"
                           "input data")

    print("\nInternal State")
    print(yaml.dump(ns, default_flow_style=False, indent=4))
    if args.output_kind == "eni":
        r_cls = eni.Renderer
    elif args.output_kind == "netplan":
        r_cls = netplan.Renderer
    else:
        r_cls = sysconfig.Renderer

    r = r_cls()
    r.render_network_state(network_state=ns, target=args.directory)


if __name__ == '__main__':
    main()

# vi: ts=4 expandtab
