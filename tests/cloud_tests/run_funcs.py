# This file is part of cloud-init. See LICENSE file for license information.

"""Run functions."""

import os

from tests.cloud_tests import bddeb, collect, util, verify


def tree_collect(args):
    """Collect data using deb build from current tree.

    @param args: cmdline args
    @return_value: fail count
    """
    failed = 0
    tmpdir = util.TempDir(tmpdir=args.data_dir, preserve=args.preserve_data)

    with tmpdir as data_dir:
        args.data_dir = data_dir
        args.deb = os.path.join(tmpdir.tmpdir, 'cloud-init_all.deb')
        try:
            failed += bddeb.bddeb(args)
            failed += collect.collect(args)
        except Exception:
            failed += 1
            raise

    return failed


def tree_run(args):
    """Run test suite using deb build from current tree.

    @param args: cmdline args
    @return_value: fail count
    """
    failed = 0
    tmpdir = util.TempDir(tmpdir=args.data_dir, preserve=args.preserve_data)

    with tmpdir as data_dir:
        args.data_dir = data_dir
        args.deb = os.path.join(tmpdir.tmpdir, 'cloud-init_all.deb')
        try:
            failed += bddeb.bddeb(args)
            failed += collect.collect(args)
            failed += verify.verify(args)
        except Exception:
            failed += 1
            raise

    return failed


def run(args):
    """Run test suite.

    @param args: cmdline args
    @return_value: fail count
    """
    failed = 0
    tmpdir = util.TempDir(tmpdir=args.data_dir, preserve=args.preserve_data)

    with tmpdir as data_dir:
        args.data_dir = data_dir
        try:
            failed += collect.collect(args)
            failed += verify.verify(args)
        except Exception:
            failed += 1
            raise

    return failed

# vi: ts=4 expandtab
