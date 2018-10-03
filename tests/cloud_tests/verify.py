# This file is part of cloud-init. See LICENSE file for license information.

"""Verify test results."""

import os
import unittest2

from tests.cloud_tests import (config, LOG, util, testcases)


def verify_data(data_dir, platform, os_name, tests):
    """Verify test data is correct.

    @param data_dir: top level directory for all tests
    @param platform: The platform name we for this test data (e.g. lxd)
    @param os_name: The operating system under test (xenial, artful, etc.).
    @param tests: list of test names
    @return_value: {<test_name>: {passed: True/False, failures: []}}
    """
    base_dir = os.sep.join((data_dir, platform, os_name))
    runner = unittest2.TextTestRunner(verbosity=util.current_verbosity())
    res = {}
    for test_name in tests:
        LOG.debug('verifying test data for %s', test_name)

        # get cloudconfig for test
        test_conf = config.load_test_config(test_name)
        test_module = config.name_to_module(test_name)
        cloud_conf = test_conf['cloud_config']

        # load script outputs
        data = {'platform': platform, 'os_name': os_name}
        test_dir = os.path.join(base_dir, test_name)
        for script_name in os.listdir(test_dir):
            with open(os.path.join(test_dir, script_name), 'rb') as fp:
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
            LOG.warning('test case: %s failed %s.%s with: %s',
                        test_name, failure['class'], failure['function'],
                        failure['error'])

    return res


def format_test_failures(test_result):
    """Return a human-readable printable format of test failures."""
    if not test_result['failures']:
        return ''
    failure_hdr = '    test failures:'
    failure_fmt = '    * {module}.{class}.{function}\n          {error}'
    output = []
    for failure in test_result['failures']:
        if not output:
            output = [failure_hdr]
        output.append(failure_fmt.format(**failure))
    return '\n'.join(output)


def format_results(res):
    """Return human-readable results as a string"""
    platform_hdr = 'Platform: {platform}'
    distro_hdr = '  Distro: {distro}'
    distro_summary_fmt = (
        '    test modules passed:{passed} tests failed:{failed}')
    output = ['']
    counts = {}
    for platform, platform_data in res.items():
        output.append(platform_hdr.format(platform=platform))
        counts[platform] = {}
        for distro, distro_data in platform_data.items():
            distro_failure_output = []
            output.append(distro_hdr.format(distro=distro))
            counts[platform][distro] = {'passed': 0, 'failed': 0}
            for _, test_result in distro_data.items():
                if test_result['passed']:
                    counts[platform][distro]['passed'] += 1
                else:
                    counts[platform][distro]['failed'] += len(
                        test_result['failures'])
                    failure_output = format_test_failures(test_result)
                    if failure_output:
                        distro_failure_output.append(failure_output)
            output.append(
                distro_summary_fmt.format(**counts[platform][distro]))
            if distro_failure_output:
                output.extend(distro_failure_output)
    return '\n'.join(output)


def verify(args):
    """Verify test data.

    @param args: directory of test data
    @return_value: 0 for success, or number of failed tests
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
                args.data_dir, platform, os_name,
                tests[platform][os_name])

            # handle results
            fail_list = [k for k, v in res[platform][os_name].items()
                         if not v.get('passed')]
            if len(fail_list) == 0:
                LOG.info('test: %s passed all tests', test_name)
            else:
                LOG.warning('test: %s failed %s tests', test_name,
                            len(fail_list))
            failed += len(fail_list)

    # dump results
    LOG.debug('\n---- Verify summarized results:\n%s', format_results(res))
    if args.result:
        util.merge_results({'verify': res}, args.result)

    return failed

# vi: ts=4 expandtab
