from unittest import TestCase
from mocker import MockerTestCase, ANY, ARGS, KWARGS
from tempfile import mkdtemp
from shutil import rmtree
import os
import stat
import sys

from cloudinit import partwalker_handle_handler, handler_handle_part, handler_register
from cloudinit.util import write_file, logexc


class TestPartwalkerHandleHandler(MockerTestCase):
    def setUp(self):
        self.data = {
            "handlercount": 0,
            "frequency": "?",
            "handlerdir": "?",
            "handlers": [],
            "data": None}

        self.expected_module_name = "part-handler-%03d" % self.data["handlercount"]
        expected_file_name = "%s.py" % self.expected_module_name
        expected_file_fullname = os.path.join(self.data["handlerdir"], expected_file_name)
        self.module_fake = "fake module handle"
        self.ctype = None
        self.filename = None
        self.payload = "dummy payload"

        # Mock the write_file function
        write_file_mock = self.mocker.replace(write_file, passthrough=False)
        write_file_mock(expected_file_fullname, self.payload, 0600)

    def test_no_errors(self):
        """Payload gets written to file and added to C{pdata}."""
        # Mock the __import__ builtin
        import_mock = self.mocker.replace("__builtin__.__import__")
        import_mock(self.expected_module_name)
        self.mocker.result(self.module_fake)
        # Mock the handle_register function
        handle_reg_mock = self.mocker.replace(handler_register, passthrough=False)
        handle_reg_mock(self.module_fake, self.data["handlers"], self.data["data"], self.data["frequency"])
        # Activate mocks
        self.mocker.replay()

        partwalker_handle_handler(self.data, self.ctype, self.filename, self.payload)

        self.assertEqual(1, self.data["handlercount"])

    def test_import_error(self):
        """Payload gets written to file and added to C{pdata}."""
        # Mock the __import__ builtin
        import_mock = self.mocker.replace("__builtin__.__import__")
        import_mock(self.expected_module_name)
        self.mocker.throw(ImportError())
        # Mock log function
        logexc_mock = self.mocker.replace(logexc, passthrough=False)
        logexc_mock(ANY)
        # Mock the print_exc function
        print_exc_mock = self.mocker.replace("traceback.print_exc", passthrough=False)
        print_exc_mock(ARGS, KWARGS)
        # Activate mocks
        self.mocker.replay()

        partwalker_handle_handler(self.data, self.ctype, self.filename, self.payload)

    def test_attribute_error(self):
        """Payload gets written to file and added to C{pdata}."""
        # Mock the __import__ builtin
        import_mock = self.mocker.replace("__builtin__.__import__")
        import_mock(self.expected_module_name)
        self.mocker.result(self.module_fake)
        # Mock the handle_register function
        handle_reg_mock = self.mocker.replace(handler_register, passthrough=False)
        handle_reg_mock(self.module_fake, self.data["handlers"], self.data["data"], self.data["frequency"])
        self.mocker.throw(AttributeError())
        # Mock log function
        logexc_mock = self.mocker.replace(logexc, passthrough=False)
        logexc_mock(ANY)
        # Mock the print_exc function
        print_exc_mock = self.mocker.replace("traceback.print_exc", passthrough=False)
        print_exc_mock(ARGS, KWARGS)
        # Activate mocks
        self.mocker.replay()

        partwalker_handle_handler(self.data, self.ctype, self.filename, self.payload)


class TestHandlerHandlePart(TestCase):
    def test_dummy(self):
        self.assertTrue(False)
