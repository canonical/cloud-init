# This file is part of cloud-init. See LICENSE file for license information.

"""Commandline utility to list the canonical cloud-id for an instance."""

import argparse
import json
import sys

from cloudinit.sources import (
    INSTANCE_JSON_FILE, METADATA_UNKNOWN, canonical_cloud_id)

DEFAULT_INSTANCE_JSON = '/run/cloud-init/%s' % INSTANCE_JSON_FILE

NAME = 'cloud-id'


def get_parser(parser=None):
    """Build or extend an arg parser for the cloud-id utility.

    @param parser: Optional existing ArgumentParser instance representing the
        query subcommand which will be extended to support the args of
        this utility.

    @returns: ArgumentParser with proper argument configuration.
    """
    if not parser:
        parser = argparse.ArgumentParser(
            prog=NAME,
            description='Report the canonical cloud-id for this instance')
    parser.add_argument(
        '-j', '--json', action='store_true', default=False,
        help='Report all standardized cloud-id information as json.')
    parser.add_argument(
        '-l', '--long', action='store_true', default=False,
        help='Report extended cloud-id information as tab-delimited string.')
    parser.add_argument(
        '-i', '--instance-data', type=str, default=DEFAULT_INSTANCE_JSON,
        help=('Path to instance-data.json file. Default is %s' %
              DEFAULT_INSTANCE_JSON))
    return parser


def error(msg):
    sys.stderr.write('ERROR: %s\n' % msg)
    return 1


def handle_args(name, args):
    """Handle calls to 'cloud-id' cli.

    Print the canonical cloud-id on which the instance is running.

    @return: 0 on success, 1 otherwise.
    """
    try:
        instance_data = json.load(open(args.instance_data))
    except IOError:
        return error(
            "File not found '%s'. Provide a path to instance data json file"
            ' using --instance-data' % args.instance_data)
    except ValueError as e:
        return error(
            "File '%s' is not valid json. %s" % (args.instance_data, e))
    v1 = instance_data.get('v1', {})
    cloud_id = canonical_cloud_id(
        v1.get('cloud_name', METADATA_UNKNOWN),
        v1.get('region', METADATA_UNKNOWN),
        v1.get('platform', METADATA_UNKNOWN))
    if args.json:
        v1['cloud_id'] = cloud_id
        response = json.dumps(   # Pretty, sorted json
            v1, indent=1, sort_keys=True, separators=(',', ': '))
    elif args.long:
        response = '%s\t%s' % (cloud_id, v1.get('region', METADATA_UNKNOWN))
    else:
        response = cloud_id
    sys.stdout.write('%s\n' % response)
    return 0


def main():
    """Tool to query specific instance-data values."""
    parser = get_parser()
    sys.exit(handle_args(NAME, parser.parse_args()))


if __name__ == '__main__':
    main()

# vi: ts=4 expandtab
