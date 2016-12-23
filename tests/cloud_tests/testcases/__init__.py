# This file is part of cloud-init. See LICENSE file for license information.

import importlib
import inspect
import unittest

from tests.cloud_tests import config
from tests.cloud_tests.testcases.base import CloudTestCase as base_test


def discover_tests(test_name):
    """
    discover tests in test file for 'testname'
    return_value: list of test classes
    """
    testmod_name = 'tests.cloud_tests.testcases.{}'.format(
        config.name_sanatize(test_name))
    try:
        testmod = importlib.import_module(testmod_name)
    except NameError:
        raise ValueError('no test verifier found at: {}'.format(testmod_name))

    return [mod for name, mod in inspect.getmembers(testmod)
            if inspect.isclass(mod) and base_test in mod.__bases__ and
            getattr(mod, '__test__', True)]


def get_suite(test_name, data, conf):
    """
    get test suite with all tests for 'testname'
    return_value: a test suite
    """
    suite = unittest.TestSuite()
    for test_class in discover_tests(test_name):

        class tmp(test_class):

            @classmethod
            def setUpClass(cls):
                cls.data = data
                cls.conf = conf

        suite.addTest(unittest.defaultTestLoader.loadTestsFromTestCase(tmp))

    return suite

# vi: ts=4 expandtab
