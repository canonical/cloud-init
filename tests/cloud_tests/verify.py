# This file is part of cloud-init. See LICENSE file for license information.

from tests.cloud_tests import (config, LOG, util, testcases)

import os
import unittest


def verify_data(base_dir, tests):
    """
    verify test data is correct,
    base_dir: base directory for data
    test_config: dict of all test config, from util.load_test_config()
    tests: list of test names
    return_value: {<test_name>: {passed: True/False, failures: []}}
    """
    runner = unittest.TextTestRunner(verbosity=util.current_verbosity())
    res = {}
    for test_name in tests:
        LOG.debug('verifying test data for %s', test_name)

        # get cloudconfig for test
        test_conf = config.load_test_config(test_name)
        test_module = config.name_to_module(test_name)
        cloud_conf = test_conf['cloud_config']

        # load script outputs
        data = {}
        test_dir = os.path.join(base_dir, test_name)
        for script_name in os.listdir(test_dir):
            with open(os.path.join(test_dir, script_name), 'r') as fp:
                data[script_name] = fp.read()

        # get test suite and launch tests
        suite = testcases.get_suite(test_module, data, cloud_conf)
        suite_results = runner.run(suite)
        res[test_name] = {
            'passed': suite_results.wasSuccessful(),
            'failures': [{'module': type(test_class).__base__.__module__,
                          'class': type(test_class).__base__.__name__,
                          'function': str(test_class).split()[0],
                          'error': trace.splitlines()[-1],
                          'traceback': trace, }
                         for test_class, trace in suite_results.failures]
        }

        for failure in res[test_name]['failures']:
            LOG.warn('test case: %s failed %s.%s with: %s',
                     test_name, failure['class'], failure['function'],
                     failure['error'])

    return res


def verify(args):
    """
    verify test data
    return_value: 0 for success, or number of failed tests
    """
    failed = 0
    res = {}

    # find test data
    tests = util.list_test_data(args.data_dir)

    for platform in tests.keys():
        res[platform] = {}
        for os_name in tests[platform].keys():
            test_name = "platform='{}', os='{}'".format(platform, os_name)
            LOG.info('test: %s verifying test data', test_name)

            # run test
            res[platform][os_name] = verify_data(
                os.sep.join((args.data_dir, platform, os_name)),
                tests[platform][os_name])

            # handle results
            fail_list = [k for k, v in res[platform][os_name].items()
                         if not v.get('passed')]
            if len(fail_list) == 0:
                LOG.info('test: %s passed all tests', test_name)
            else:
                LOG.warn('test: %s failed %s tests', test_name, len(fail_list))
            failed += len(fail_list)

    # dump results
    LOG.debug('verify results: %s', res)
    if args.result:
        util.merge_results({'verify': res}, args.result)

    return failed

# vi: ts=4 expandtab
