# This file is part of cloud-init. See LICENSE file for license information.

"""Create test cases automatically given a user_data script."""

import os
import textwrap

from cloudinit import util as c_util
from tests.cloud_tests.config import VERIFY_EXT
from tests.cloud_tests import (config, util)
from tests.cloud_tests import TESTCASES_DIR


_verifier_fmt = textwrap.dedent(
    """
    \"\"\"cloud-init Integration Test Verify Script\"\"\"
    from tests.cloud_tests.testcases import base


    class {test_class}(base.CloudTestCase):
        \"\"\"
        Name: {test_name}
        Category: {test_category}
        Description: {test_description}
        \"\"\"
        pass
    """
).lstrip()
_config_fmt = textwrap.dedent(
    """
    #
    # Name: {test_name}
    # Category: {test_category}
    # Description: {test_description}
    #
    {config}
    """
).strip()


def write_testcase_config(args, fmt_args, testcase_file):
    """Write the testcase config file."""
    testcase_config = {'enabled': args.enable, 'collect_scripts': {}}
    if args.config:
        testcase_config['cloud_config'] = args.config
    fmt_args['config'] = util.yaml_format(testcase_config)
    c_util.write_file(testcase_file, _config_fmt.format(**fmt_args), omode='w')


def write_verifier(args, fmt_args, verifier_file):
    """Write the verifier script."""
    fmt_args['test_class'] = 'Test{}'.format(
        config.name_sanitize(fmt_args['test_name']).title())
    c_util.write_file(verifier_file,
                      _verifier_fmt.format(**fmt_args), omode='w')


def create(args):
    """Create a new testcase."""
    (test_category, test_name) = args.name.split('/')
    fmt_args = {'test_name': test_name, 'test_category': test_category,
                'test_description': str(args.description)}

    testcase_file = config.name_to_path(args.name)
    verifier_file = os.path.join(
        TESTCASES_DIR, test_category,
        config.name_sanitize(test_name) + VERIFY_EXT)

    write_testcase_config(args, fmt_args, testcase_file)
    write_verifier(args, fmt_args, verifier_file)

    return 0

# vi: ts=4 expandtab
