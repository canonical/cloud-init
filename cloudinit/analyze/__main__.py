# Copyright (C) 2017 Canonical Ltd.
#
# This file is part of cloud-init. See LICENSE file for license information.

import argparse
import re
import sys

from cloudinit.util import json_dumps

from . import dump
from . import show


def get_parser(parser=None):
    if not parser:
        parser = argparse.ArgumentParser(
            prog='cloudinit-analyze',
            description='Devel tool: Analyze cloud-init logs and data')
    subparsers = parser.add_subparsers(title='Subcommands', dest='subcommand')
    subparsers.required = True

    parser_blame = subparsers.add_parser(
        'blame', help='Print list of executed stages ordered by time to init')
    parser_blame.add_argument(
        '-i', '--infile', action='store', dest='infile',
        default='/var/log/cloud-init.log',
        help='specify where to read input.')
    parser_blame.add_argument(
        '-o', '--outfile', action='store', dest='outfile', default='-',
        help='specify where to write output. ')
    parser_blame.set_defaults(action=('blame', analyze_blame))

    parser_show = subparsers.add_parser(
        'show', help='Print list of in-order events during execution')
    parser_show.add_argument('-f', '--format', action='store',
                             dest='print_format', default='%I%D @%Es +%ds',
                             help='specify formatting of output.')
    parser_show.add_argument('-i', '--infile', action='store',
                             dest='infile', default='/var/log/cloud-init.log',
                             help='specify where to read input.')
    parser_show.add_argument('-o', '--outfile', action='store',
                             dest='outfile', default='-',
                             help='specify where to write output.')
    parser_show.set_defaults(action=('show', analyze_show))
    parser_dump = subparsers.add_parser(
        'dump', help='Dump cloud-init events in JSON format')
    parser_dump.add_argument('-i', '--infile', action='store',
                             dest='infile', default='/var/log/cloud-init.log',
                             help='specify where to read input. ')
    parser_dump.add_argument('-o', '--outfile', action='store',
                             dest='outfile', default='-',
                             help='specify where to write output. ')
    parser_dump.set_defaults(action=('dump', analyze_dump))
    return parser


def analyze_blame(name, args):
    """Report a list of records sorted by largest time delta.

    For example:
      30.210s (init-local) searching for datasource
       8.706s (init-network) reading and applying user-data
        166ms (modules-config) ....
        807us (modules-final) ...

    We generate event records parsing cloud-init logs, formatting the output
    and sorting by record data ('delta')
    """
    (infh, outfh) = configure_io(args)
    blame_format = '     %ds (%n)'
    r = re.compile(r'(^\s+\d+\.\d+)', re.MULTILINE)
    for idx, record in enumerate(show.show_events(_get_events(infh),
                                                  blame_format)):
        srecs = sorted(filter(r.match, record), reverse=True)
        outfh.write('-- Boot Record %02d --\n' % (idx + 1))
        outfh.write('\n'.join(srecs) + '\n')
        outfh.write('\n')
    outfh.write('%d boot records analyzed\n' % (idx + 1))


def analyze_show(name, args):
    """Generate output records using the 'standard' format to printing events.

    Example output follows:
        Starting stage: (init-local)
          ...
        Finished stage: (init-local) 0.105195 seconds

        Starting stage: (init-network)
          ...
        Finished stage: (init-network) 0.339024 seconds

        Starting stage: (modules-config)
          ...
        Finished stage: (modules-config) 0.NNN seconds

        Starting stage: (modules-final)
          ...
        Finished stage: (modules-final) 0.NNN seconds
    """
    (infh, outfh) = configure_io(args)
    for idx, record in enumerate(show.show_events(_get_events(infh),
                                                  args.print_format)):
        outfh.write('-- Boot Record %02d --\n' % (idx + 1))
        outfh.write('The total time elapsed since completing an event is'
                    ' printed after the "@" character.\n')
        outfh.write('The time the event takes is printed after the "+" '
                    'character.\n\n')
        outfh.write('\n'.join(record) + '\n')
    outfh.write('%d boot records analyzed\n' % (idx + 1))


def analyze_dump(name, args):
    """Dump cloud-init events in json format"""
    (infh, outfh) = configure_io(args)
    outfh.write(json_dumps(_get_events(infh)) + '\n')


def _get_events(infile):
    rawdata = None
    events, rawdata = show.load_events(infile, None)
    if not events:
        events, _ = dump.dump_events(rawdata=rawdata)
    return events


def configure_io(args):
    """Common parsing and setup of input/output files"""
    if args.infile == '-':
        infh = sys.stdin
    else:
        try:
            infh = open(args.infile, 'r')
        except OSError:
            sys.stderr.write('Cannot open file %s\n' % args.infile)
            sys.exit(1)

    if args.outfile == '-':
        outfh = sys.stdout
    else:
        try:
            outfh = open(args.outfile, 'w')
        except OSError:
            sys.stderr.write('Cannot open file %s\n' % args.outfile)
            sys.exit(1)

    return (infh, outfh)


if __name__ == '__main__':
    parser = get_parser()
    args = parser.parse_args()
    (name, action_functor) = args.action
    action_functor(name, args)

# vi: ts=4 expandtab
