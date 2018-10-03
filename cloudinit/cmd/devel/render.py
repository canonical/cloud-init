# This file is part of cloud-init. See LICENSE file for license information.

"""Debug jinja template rendering of user-data."""

import argparse
import os
import sys

from cloudinit.handlers.jinja_template import render_jinja_payload_from_file
from cloudinit import log
from cloudinit.sources import INSTANCE_JSON_FILE
from . import addLogHandlerCLI, read_cfg_paths

NAME = 'render'
DEFAULT_INSTANCE_DATA = '/run/cloud-init/instance-data.json'

LOG = log.getLogger(NAME)


def get_parser(parser=None):
    """Build or extend and arg parser for jinja render utility.

    @param parser: Optional existing ArgumentParser instance representing the
        subcommand which will be extended to support the args of this utility.

    @returns: ArgumentParser with proper argument configuration.
    """
    if not parser:
        parser = argparse.ArgumentParser(prog=NAME, description=__doc__)
    parser.add_argument(
        'user_data', type=str, help='Path to the user-data file to render')
    parser.add_argument(
        '-i', '--instance-data', type=str,
        help=('Optional path to instance-data.json file. Defaults to'
              ' /run/cloud-init/instance-data.json'))
    parser.add_argument('-d', '--debug', action='store_true', default=False,
                        help='Add verbose messages during template render')
    return parser


def handle_args(name, args):
    """Render the provided user-data template file using instance-data values.

    Also setup CLI log handlers to report to stderr since this is a development
    utility which should be run by a human on the CLI.

    @return 0 on success, 1 on failure.
    """
    addLogHandlerCLI(LOG, log.DEBUG if args.debug else log.WARNING)
    if not args.instance_data:
        paths = read_cfg_paths()
        instance_data_fn = os.path.join(
            paths.run_dir, INSTANCE_JSON_FILE)
    else:
        instance_data_fn = args.instance_data
    if not os.path.exists(instance_data_fn):
        LOG.error('Missing instance-data.json file: %s', instance_data_fn)
        return 1
    try:
        with open(args.user_data) as stream:
            user_data = stream.read()
    except IOError:
        LOG.error('Missing user-data file: %s', args.user_data)
        return 1
    rendered_payload = render_jinja_payload_from_file(
        payload=user_data, payload_fn=args.user_data,
        instance_data_file=instance_data_fn,
        debug=True if args.debug else False)
    if not rendered_payload:
        LOG.error('Unable to render user-data file: %s', args.user_data)
        return 1
    sys.stdout.write(rendered_payload)
    return 0


def main():
    args = get_parser().parse_args()
    return(handle_args(NAME, args))


if __name__ == '__main__':
    sys.exit(main())


# vi: ts=4 expandtab
