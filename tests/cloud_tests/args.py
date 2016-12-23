# This file is part of cloud-init. See LICENSE file for license information.

import os

from tests.cloud_tests import config, util
from tests.cloud_tests import LOG

ARG_SETS = {
    'COLLECT': (
        (('-p', '--platform'),
         {'help': 'platform(s) to run tests on', 'metavar': 'PLATFORM',
          'action': 'append', 'choices': config.list_enabled_platforms(),
          'default': []}),
        (('-n', '--os-name'),
         {'help': 'the name(s) of the OS(s) to test', 'metavar': 'NAME',
          'action': 'append', 'choices': config.list_enabled_distros(),
          'default': []}),
        (('-t', '--test-config'),
         {'help': 'test config file(s) to use', 'metavar': 'FILE',
          'action': 'append', 'default': []}),),
    'CREATE': (
        (('-c', '--config'),
         {'help': 'cloud-config yaml for testcase', 'metavar': 'DATA',
          'action': 'store', 'required': False, 'default': None}),
        (('-e', '--enable'),
         {'help': 'enable testcase', 'required': False, 'default': False,
          'action': 'store_true'}),
        (('name',),
         {'help': 'testcase name, in format "<category>/<test>"',
          'action': 'store'}),
        (('-d', '--description'),
         {'help': 'description of testcase', 'required': False}),
        (('-f', '--force'),
         {'help': 'overwrite already existing test', 'required': False,
          'action': 'store_true', 'default': False}),),
    'INTERFACE': (
        (('-v', '--verbose'),
         {'help': 'verbose output', 'action': 'store_true', 'default': False}),
        (('-q', '--quiet'),
         {'help': 'quiet output', 'action': 'store_true', 'default': False}),),
    'OUTPUT': (
        (('-d', '--data-dir'),
         {'help': 'directory to store test data in',
          'action': 'store', 'metavar': 'DIR', 'required': True}),),
    'RESULT': (
        (('-r', '--result'),
         {'help': 'file to write results to',
          'action': 'store', 'metavar': 'FILE'}),),
    'SETUP': (
        (('--deb',),
         {'help': 'install deb', 'metavar': 'FILE', 'action': 'store'}),
        (('--rpm',),
         {'help': 'install rpm', 'metavar': 'FILE', 'action': 'store'}),
        (('--script',),
         {'help': 'script to set up image', 'metavar': 'DATA',
          'action': 'store'}),
        (('--repo',),
         {'help': 'repo to enable (implies -u)', 'metavar': 'NAME',
          'action': 'store'}),
        (('--ppa',),
         {'help': 'ppa to enable (implies -u)', 'metavar': 'NAME',
          'action': 'store'}),
        (('-u', '--upgrade'),
         {'help': 'upgrade before starting tests', 'action': 'store_true',
          'default': False}),),
}

SUBCMDS = {
    'collect': ('collect test data',
                ('COLLECT', 'INTERFACE', 'OUTPUT', 'RESULT', 'SETUP')),
    'create': ('create new test case', ('CREATE', 'INTERFACE')),
    'run': ('run test suite', ('COLLECT', 'INTERFACE', 'RESULT', 'SETUP')),
    'verify': ('verify test data', ('INTERFACE', 'OUTPUT', 'RESULT')),
}


def _empty_normalizer(args):
    """
    do not normalize arguments
    """
    return args


def normalize_create_args(args):
    """
    normalize CREATE arguments
    args: parsed args
    return_value: updated args, or None if errors occurred
    """
    # ensure valid name for new test
    if len(args.name.split('/')) != 2:
        LOG.error('invalid test name: %s', args.name)
        return None
    if os.path.exists(config.name_to_path(args.name)):
        msg = 'test: {} already exists'.format(args.name)
        if args.force:
            LOG.warn('%s but ignoring due to --force', msg)
        else:
            LOG.error(msg)
            return None

    # ensure test config valid if specified
    if isinstance(args.config, str) and len(args.config) == 0:
        LOG.error('test config cannot be empty if specified')
        return None

    # ensure description valid if specified
    if (isinstance(args.description, str) and
            (len(args.description) > 70 or len(args.description) == 0)):
        LOG.error('test description must be between 1 and 70 characters')
        return None

    return args


def normalize_collect_args(args):
    """
    normalize COLLECT arguments
    args: parsed args
    return_value: updated args, or None if errors occurred
    """
    # platform should default to all supported
    if len(args.platform) == 0:
        args.platform = config.list_enabled_platforms()
    args.platform = util.sorted_unique(args.platform)

    # os name should default to all enabled
    # if os name is provided ensure that all provided are supported
    if len(args.os_name) == 0:
        args.os_name = config.list_enabled_distros()
    else:
        supported = config.list_enabled_distros()
        invalid = [os_name for os_name in args.os_name
                   if os_name not in supported]
        if len(invalid) != 0:
            LOG.error('invalid os name(s): %s', invalid)
            return None
    args.os_name = util.sorted_unique(args.os_name)

    # test configs should default to all enabled
    # if test configs are provided, ensure that all provided are valid
    if len(args.test_config) == 0:
        args.test_config = config.list_test_configs()
    else:
        valid = []
        invalid = []
        for name in args.test_config:
            if os.path.exists(name):
                valid.append(name)
            elif os.path.exists(config.name_to_path(name)):
                valid.append(config.name_to_path(name))
            else:
                invalid.append(name)
        if len(invalid) != 0:
            LOG.error('invalid test config(s): %s', invalid)
            return None
        else:
            args.test_config = valid
    args.test_config = util.sorted_unique(args.test_config)

    return args


def normalize_output_args(args):
    """
    normalize OUTPUT arguments
    args: parsed args
    return_value: updated args, or None if errors occurred
    """
    if not args.data_dir:
        LOG.error('--data-dir must be specified')
        return None

    # ensure clean output dir if collect
    # ensure data exists if verify
    if args.subcmd == 'collect':
        if not util.is_clean_writable_dir(args.data_dir):
            LOG.error('data_dir must be empty/new and must be writable')
            return None
    elif args.subcmd == 'verify':
        if not os.path.exists(args.data_dir):
            LOG.error('data_dir %s does not exist', args.data_dir)
            return None

    return args


def normalize_setup_args(args):
    """
    normalize SETUP arguments
    args: parsed args
    return_value: updated_args, or None if errors occurred
    """
    # ensure deb or rpm valid if specified
    for pkg in (args.deb, args.rpm):
        if pkg is not None and not os.path.exists(pkg):
            LOG.error('cannot find package: %s', pkg)
            return None

    # if repo or ppa to be enabled run upgrade
    if args.repo or args.ppa:
        args.upgrade = True

    # if ppa is specified, remove leading 'ppa:' if any
    _ppa_header = 'ppa:'
    if args.ppa and args.ppa.startswith(_ppa_header):
        args.ppa = args.ppa[len(_ppa_header):]

    return args


NORMALIZERS = {
    'COLLECT': normalize_collect_args,
    'CREATE': normalize_create_args,
    'INTERFACE': _empty_normalizer,
    'OUTPUT': normalize_output_args,
    'RESULT': _empty_normalizer,
    'SETUP': normalize_setup_args,
}

# vi: ts=4 expandtab
