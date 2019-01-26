# This file is part of cloud-init. See LICENSE file for license information.

"""Query standardized instance metadata from the command line."""

import argparse
from errno import EACCES
import os
import six
import sys

from cloudinit.handlers.jinja_template import (
    convert_jinja_instance_data, render_jinja_payload)
from cloudinit.cmd.devel import addLogHandlerCLI, read_cfg_paths
from cloudinit import log
from cloudinit.sources import (
    INSTANCE_JSON_FILE, INSTANCE_JSON_SENSITIVE_FILE, REDACT_SENSITIVE_VALUE)
from cloudinit import util

NAME = 'query'
LOG = log.getLogger(NAME)


def get_parser(parser=None):
    """Build or extend an arg parser for query utility.

    @param parser: Optional existing ArgumentParser instance representing the
        query subcommand which will be extended to support the args of
        this utility.

    @returns: ArgumentParser with proper argument configuration.
    """
    if not parser:
        parser = argparse.ArgumentParser(
            prog=NAME, description='Query cloud-init instance data')
    parser.add_argument(
        '-d', '--debug', action='store_true', default=False,
        help='Add verbose messages during template render')
    parser.add_argument(
        '-i', '--instance-data', type=str,
        help=('Path to instance-data.json file. Default is /run/cloud-init/%s'
              % INSTANCE_JSON_FILE))
    parser.add_argument(
        '-l', '--list-keys', action='store_true', default=False,
        help=('List query keys available at the provided instance-data'
              ' <varname>.'))
    parser.add_argument(
        '-u', '--user-data', type=str,
        help=('Path to user-data file. Default is'
              ' /var/lib/cloud/instance/user-data.txt'))
    parser.add_argument(
        '-v', '--vendor-data', type=str,
        help=('Path to vendor-data file. Default is'
              ' /var/lib/cloud/instance/vendor-data.txt'))
    parser.add_argument(
        'varname', type=str, nargs='?',
        help=('A dot-delimited instance data variable to query from'
              ' instance-data query. For example: v2.local_hostname'))
    parser.add_argument(
        '-a', '--all', action='store_true', default=False, dest='dump_all',
        help='Dump all available instance-data')
    parser.add_argument(
        '-f', '--format', type=str, dest='format',
        help=('Optionally specify a custom output format string. Any'
              ' instance-data variable can be specified between double-curly'
              ' braces. For example -f "{{ v2.cloud_name }}"'))
    return parser


def handle_args(name, args):
    """Handle calls to 'cloud-init query' as a subcommand."""
    paths = None
    addLogHandlerCLI(LOG, log.DEBUG if args.debug else log.WARNING)
    if not any([args.list_keys, args.varname, args.format, args.dump_all]):
        LOG.error(
            'Expected one of the options: --all, --format,'
            ' --list-keys or varname')
        get_parser().print_help()
        return 1

    uid = os.getuid()
    if not all([args.instance_data, args.user_data, args.vendor_data]):
        paths = read_cfg_paths()
    if args.instance_data:
        instance_data_fn = args.instance_data
    else:
        redacted_data_fn = os.path.join(paths.run_dir, INSTANCE_JSON_FILE)
        if uid == 0:
            sensitive_data_fn = os.path.join(
                paths.run_dir, INSTANCE_JSON_SENSITIVE_FILE)
            if os.path.exists(sensitive_data_fn):
                instance_data_fn = sensitive_data_fn
            else:
                LOG.warning(
                     'Missing root-readable %s. Using redacted %s instead.',
                     sensitive_data_fn, redacted_data_fn)
                instance_data_fn = redacted_data_fn
        else:
            instance_data_fn = redacted_data_fn
    if args.user_data:
        user_data_fn = args.user_data
    else:
        user_data_fn = os.path.join(paths.instance_link, 'user-data.txt')
    if args.vendor_data:
        vendor_data_fn = args.vendor_data
    else:
        vendor_data_fn = os.path.join(paths.instance_link, 'vendor-data.txt')

    try:
        instance_json = util.load_file(instance_data_fn)
    except (IOError, OSError) as e:
        if e.errno == EACCES:
            LOG.error("No read permission on '%s'. Try sudo", instance_data_fn)
        else:
            LOG.error('Missing instance-data file: %s', instance_data_fn)
        return 1

    instance_data = util.load_json(instance_json)
    if uid != 0:
        instance_data['userdata'] = (
            '<%s> file:%s' % (REDACT_SENSITIVE_VALUE, user_data_fn))
        instance_data['vendordata'] = (
            '<%s> file:%s' % (REDACT_SENSITIVE_VALUE, vendor_data_fn))
    else:
        instance_data['userdata'] = util.load_file(user_data_fn)
        instance_data['vendordata'] = util.load_file(vendor_data_fn)
    if args.format:
        payload = '## template: jinja\n{fmt}'.format(fmt=args.format)
        rendered_payload = render_jinja_payload(
            payload=payload, payload_fn='query commandline',
            instance_data=instance_data,
            debug=True if args.debug else False)
        if rendered_payload:
            print(rendered_payload)
            return 0
        return 1

    response = convert_jinja_instance_data(instance_data)
    if args.varname:
        try:
            for var in args.varname.split('.'):
                response = response[var]
        except KeyError:
            LOG.error('Undefined instance-data key %s', args.varname)
            return 1
        if args.list_keys:
            if not isinstance(response, dict):
                LOG.error("--list-keys provided but '%s' is not a dict", var)
                return 1
            response = '\n'.join(sorted(response.keys()))
    elif args.list_keys:
        response = '\n'.join(sorted(response.keys()))
    if not isinstance(response, six.string_types):
        response = util.json_dumps(response)
    print(response)
    return 0


def main():
    """Tool to query specific instance-data values."""
    parser = get_parser()
    sys.exit(handle_args(NAME, parser.parse_args()))


if __name__ == '__main__':
    main()

# vi: ts=4 expandtab
