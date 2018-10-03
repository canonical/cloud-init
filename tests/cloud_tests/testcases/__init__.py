# This file is part of cloud-init. See LICENSE file for license information.

"""Main init."""

import importlib
import inspect
import unittest2

from cloudinit.util import read_conf

from tests.cloud_tests import config
from tests.cloud_tests.testcases.base import CloudTestCase as base_test


def discover_test(test_name):
    """Discover tests in test file for 'testname'.

    @return_value: list of test classes
    """
    testmod_name = 'tests.cloud_tests.testcases.{}'.format(
        config.name_sanitize(test_name))
    try:
        testmod = importlib.import_module(testmod_name)
    except NameError:
        raise ValueError('no test verifier found at: {}'.format(testmod_name))

    found = [mod for name, mod in inspect.getmembers(testmod)
             if (inspect.isclass(mod)
                 and base_test in inspect.getmro(mod)
                 and getattr(mod, '__test__', True))]
    if len(found) != 1:
        raise RuntimeError(
            "Unexpected situation, multiple tests for %s: %s" % (
                test_name, found))

    return found


def get_test_class(test_name, test_data, test_conf):
    test_class = discover_test(test_name)[0]

    class DynamicTestSubclass(test_class):

        _realclass = test_class
        data = test_data
        conf = test_conf
        release_conf = read_conf(config.RELEASES_CONF)['releases']

        def __str__(self):
            return "%s (%s)" % (self._testMethodName,
                                unittest2.util.strclass(self._realclass))

        @classmethod
        def setUpClass(cls):
            cls.maybeSkipTest()

    return DynamicTestSubclass


def get_suite(test_name, data, conf):
    """Get test suite with all tests for 'testname'.

    @return_value: a test suite
    """
    suite = unittest2.TestSuite()
    suite.addTest(
        unittest2.defaultTestLoader.loadTestsFromTestCase(
            get_test_class(test_name, data, conf)))
    return suite

# vi: ts=4 expandtab
