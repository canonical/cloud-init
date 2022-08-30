#!/usr/bin/env python3
# This file is part of cloud-init. See LICENSE file for license information.

"""Debug network config format conversions."""
import argparse
import json
import os
import sys

import yaml

from cloudinit import distros, log, safeyaml
from cloudinit.net import (
    eni,
    netplan,
    network_manager,
    network_state,
    networkd,
    sysconfig,
)
from cloudinit.sources import DataSourceAzure as azure
from cloudinit.sources import DataSourceOVF as ovf
from cloudinit.sources.helpers import openstack

NAME = "net-convert"


def get_parser(parser=None):
    """Build or extend and arg parser for net-convert utility.

    @param parser: Optional existing ArgumentParser instance representing the
        subcommand which will be extended to support the args of this utility.

    @returns: ArgumentParser with proper argument configuration.
    """
    if not parser:
        parser = argparse.ArgumentParser(prog=NAME, description=__doc__)
    parser.add_argument(
        "-p",
        "--network-data",
        type=open,
        metavar="PATH",
        required=True,
        help="The network configuration to read",
    )
    parser.add_argument(
        "-k",
        "--kind",
        choices=[
            "eni",
            "network_data.json",
            "yaml",
            "azure-imds",
            "vmware-imc",
        ],
        required=True,
        help="The format of the given network config",
    )
    parser.add_argument(
        "-d",
        "--directory",
        metavar="PATH",
        help="directory to place output in",
        required=True,
    )
    parser.add_argument(
        "-D",
        "--distro",
        choices=[
            item for sublist in distros.OSFAMILIES.values() for item in sublist
        ],
        required=True,
    )
    parser.add_argument(
        "-m",
        "--mac",
        metavar="name,mac",
        action="append",
        help="interface name to mac mapping",
    )
    parser.add_argument(
        "--debug", action="store_true", help="enable debug logging to stderr."
    )
    parser.add_argument(
        "-O",
        "--output-kind",
        choices=["eni", "netplan", "networkd", "sysconfig", "network-manager"],
        required=True,
        help="The network config format to emit",
    )
    return parser


def handle_args(name, args):
    if not args.directory.endswith("/"):
        args.directory += "/"

    if not os.path.isdir(args.directory):
        os.makedirs(args.directory)

    if args.debug:
        log.setupBasicLogging(level=log.DEBUG)
    else:
        log.setupBasicLogging(level=log.WARN)
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
    elif args.kind == "yaml":
        pre_ns = safeyaml.load(net_data)
        if "network" in pre_ns:
            pre_ns = pre_ns.get("network")
        if args.debug:
            sys.stderr.write(
                "\n".join(["Input YAML", safeyaml.dumps(pre_ns), ""])
            )
    elif args.kind == "network_data.json":
        pre_ns = openstack.convert_net_json(
            json.loads(net_data), known_macs=known_macs
        )
    elif args.kind == "azure-imds":
        pre_ns = azure.generate_network_config_from_instance_network_metadata(
            json.loads(net_data)["network"]
        )
    elif args.kind == "vmware-imc":
        config = ovf.Config(ovf.ConfigFile(args.network_data.name))
        pre_ns = ovf.get_network_config_from_conf(config, False)

    distro_cls = distros.fetch(args.distro)
    distro = distro_cls(args.distro, {}, None)
    if args.output_kind == "eni":
        r_cls = eni.Renderer
        config = distro.renderer_configs.get("eni")
    elif args.output_kind == "netplan":
        r_cls = netplan.Renderer
        config = distro.renderer_configs.get("netplan", {})
        # don't run netplan generate/apply
        config["postcmds"] = False
        # trim leading slash
        config["netplan_path"] = config["netplan_path"][1:]
        # enable some netplan features
        config["features"] = ["dhcp-use-domains", "ipv6-mtu"]
    elif args.output_kind == "networkd":
        r_cls = networkd.Renderer
        config = distro.renderer_configs.get("networkd")
    elif args.output_kind == "sysconfig":
        r_cls = sysconfig.Renderer
        config = distro.renderer_configs.get("sysconfig")
    elif args.output_kind == "network-manager":
        r_cls = network_manager.Renderer
        config = distro.renderer_configs.get("network-manager")
    else:
        raise RuntimeError("Invalid output_kind")

    r = r_cls(config=config)
    ns = network_state.parse_net_config_data(pre_ns, renderer=r)

    if args.debug:
        sys.stderr.write("\n".join(["", "Internal State", yaml.dump(ns), ""]))

    sys.stderr.write(
        "".join(
            [
                "Read input format '%s' from '%s'.\n"
                % (args.kind, args.network_data.name),
                "Wrote output format '%s' to '%s'\n"
                % (args.output_kind, args.directory),
            ]
        )
        + "\n"
    )
    r.render_network_state(network_state=ns, target=args.directory)


if __name__ == "__main__":
    args = get_parser().parse_args()
    handle_args(NAME, args)
