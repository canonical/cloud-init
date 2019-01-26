# This file is part of cloud-init. See LICENSE file for license information.

"""Debug network config format conversions."""
import argparse
import json
import os
import sys
import yaml

from cloudinit.sources.helpers import openstack
from cloudinit.sources import DataSourceAzure as azure
from cloudinit.sources import DataSourceOVF as ovf

from cloudinit import distros
from cloudinit.net import eni, netplan, network_state, sysconfig
from cloudinit import log

NAME = 'net-convert'


def get_parser(parser=None):
    """Build or extend and arg parser for net-convert utility.

    @param parser: Optional existing ArgumentParser instance representing the
        subcommand which will be extended to support the args of this utility.

    @returns: ArgumentParser with proper argument configuration.
    """
    if not parser:
        parser = argparse.ArgumentParser(prog=NAME, description=__doc__)
    parser.add_argument("-p", "--network-data", type=open,
                        metavar="PATH", required=True)
    parser.add_argument("-k", "--kind",
                        choices=['eni', 'network_data.json', 'yaml',
                                 'azure-imds', 'vmware-imc'],
                        required=True)
    parser.add_argument("-d", "--directory",
                        metavar="PATH",
                        help="directory to place output in",
                        required=True)
    parser.add_argument("-D", "--distro",
                        choices=[item for sublist in
                                 distros.OSFAMILIES.values()
                                 for item in sublist],
                        required=True)
    parser.add_argument("-m", "--mac",
                        metavar="name,mac",
                        action='append',
                        help="interface name to mac mapping")
    parser.add_argument("--debug", action='store_true',
                        help='enable debug logging to stderr.')
    parser.add_argument("-O", "--output-kind",
                        choices=['eni', 'netplan', 'sysconfig'],
                        required=True)
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
        pre_ns = yaml.load(net_data)
        if 'network' in pre_ns:
            pre_ns = pre_ns.get('network')
        if args.debug:
            sys.stderr.write('\n'.join(
                ["Input YAML",
                 yaml.dump(pre_ns, default_flow_style=False, indent=4), ""]))
    elif args.kind == 'network_data.json':
        pre_ns = openstack.convert_net_json(
            json.loads(net_data), known_macs=known_macs)
    elif args.kind == 'azure-imds':
        pre_ns = azure.parse_network_config(json.loads(net_data))
    elif args.kind == 'vmware-imc':
        config = ovf.Config(ovf.ConfigFile(args.network_data.name))
        pre_ns = ovf.get_network_config_from_conf(config, False)

    ns = network_state.parse_net_config_data(pre_ns)
    if not ns:
        raise RuntimeError("No valid network_state object created from"
                           "input data")

    if args.debug:
        sys.stderr.write('\n'.join([
            "", "Internal State",
            yaml.dump(ns, default_flow_style=False, indent=4), ""]))
    distro_cls = distros.fetch(args.distro)
    distro = distro_cls(args.distro, {}, None)
    config = {}
    if args.output_kind == "eni":
        r_cls = eni.Renderer
        config = distro.renderer_configs.get('eni')
    elif args.output_kind == "netplan":
        r_cls = netplan.Renderer
        config = distro.renderer_configs.get('netplan')
        # don't run netplan generate/apply
        config['postcmds'] = False
        # trim leading slash
        config['netplan_path'] = config['netplan_path'][1:]
    else:
        r_cls = sysconfig.Renderer
        config = distro.renderer_configs.get('sysconfig')

    r = r_cls(config=config)
    sys.stderr.write(''.join([
        "Read input format '%s' from '%s'.\n" % (
            args.kind, args.network_data.name),
        "Wrote output format '%s' to '%s'\n" % (
            args.output_kind, args.directory)]) + "\n")
    r.render_network_state(network_state=ns, target=args.directory)


if __name__ == '__main__':
    args = get_parser().parse_args()
    handle_args(NAME, args)


# vi: ts=4 expandtab
