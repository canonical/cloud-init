# This file is part of cloud-init. See LICENSE file for license information.

"""Main entry point."""

import argparse
import logging
import os
import sys

from tests.cloud_tests import args, bddeb, collect, manage, run_funcs, verify
from tests.cloud_tests import LOG


def configure_log(args):
    """Configure logging."""
    level = logging.INFO
    if args.verbose:
        level = logging.DEBUG
    elif args.quiet:
        level = logging.WARN
    LOG.setLevel(level)


def main():
    """Entry point for cloud test suite."""
    # configure parser
    parser = argparse.ArgumentParser(prog='cloud_tests')
    subparsers = parser.add_subparsers(dest="subcmd")
    subparsers.required = True

    def add_subparser(name, description, arg_sets):
        """Add arguments to subparser."""
        subparser = subparsers.add_parser(name, help=description)
        for (_args, _kwargs) in (a for arg_set in arg_sets for a in arg_set):
            subparser.add_argument(*_args, **_kwargs)

    # configure subparsers
    for (name, (description, arg_sets)) in args.SUBCMDS.items():
        add_subparser(name, description,
                      [args.ARG_SETS[arg_set] for arg_set in arg_sets])

    # parse arguments
    parsed = parser.parse_args()

    # process arguments
    configure_log(parsed)
    (_, arg_sets) = args.SUBCMDS[parsed.subcmd]
    for normalizer in [args.NORMALIZERS[arg_set] for arg_set in arg_sets]:
        parsed = normalizer(parsed)
        if not parsed:
            return -1

    # run handler
    LOG.debug('running with args: %s', parsed)
    return {
        'bddeb': bddeb.bddeb,
        'collect': collect.collect,
        'create': manage.create,
        'run': run_funcs.run,
        'tree_collect': run_funcs.tree_collect,
        'tree_run': run_funcs.tree_run,
        'verify': verify.verify,
    }[parsed.subcmd](parsed)


if __name__ == "__main__":
    if os.geteuid() == 0:
        sys.exit('Do not run as root')
    sys.exit(main())

# vi: ts=4 expandtab
