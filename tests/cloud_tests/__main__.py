# This file is part of cloud-init. See LICENSE file for license information.

import argparse
import logging
import shutil
import sys
import tempfile

from tests.cloud_tests import (args, collect, manage, verify)
from tests.cloud_tests import LOG


def configure_log(args):
    """
    configure logging
    """
    level = logging.INFO
    if args.verbose:
        level = logging.DEBUG
    elif args.quiet:
        level = logging.WARN
    LOG.setLevel(level)


def run(args):
    """
    run full test suite
    """
    failed = 0
    args.data_dir = tempfile.mkdtemp(prefix='cloud_test_data_')
    LOG.debug('using tmpdir %s', args.data_dir)
    try:
        failed += collect.collect(args)
        failed += verify.verify(args)
    except Exception:
        failed += 1
        raise
    finally:
        # TODO: make this configurable via environ or cmdline
        if failed:
            LOG.warn('some tests failed, leaving data in %s', args.data_dir)
        else:
            shutil.rmtree(args.data_dir)
    return failed


def main():
    """
    entry point for cloud test suite
    """
    # configure parser
    parser = argparse.ArgumentParser(prog='cloud_tests')
    subparsers = parser.add_subparsers(dest="subcmd")
    subparsers.required = True

    def add_subparser(name, description, arg_sets):
        """
        add arguments to subparser
        """
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
    LOG.debug('running with args: %s\n', parsed)
    return {
        'collect': collect.collect,
        'create': manage.create,
        'run': run,
        'verify': verify.verify,
    }[parsed.subcmd](parsed)


if __name__ == "__main__":
    sys.exit(main())

# vi: ts=4 expandtab
