from mocker import MockerTestCase, ANY, ARGS, KWARGS
import os

from cloudinit import (partwalker_handle_handler, handler_handle_part,
                       handler_register, get_cmdline_url)
from cloudinit.util import write_file, logexc, readurl


class TestPartwalkerHandleHandler(MockerTestCase):
    def setUp(self):
        self.data = {
            "handlercount": 0,
            "frequency": "?",
            "handlerdir": "?",
            "handlers": [],
            "data": None}

        self.expected_module_name = "part-handler-%03d" % (
            self.data["handlercount"],)
        expected_file_name = "%s.py" % self.expected_module_name
        expected_file_fullname = os.path.join(self.data["handlerdir"],
                                              expected_file_name)
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
        handle_reg_mock = self.mocker.replace(handler_register,
                                              passthrough=False)
        handle_reg_mock(self.module_fake, self.data["handlers"],
                        self.data["data"], self.data["frequency"])
        # Activate mocks
        self.mocker.replay()

        partwalker_handle_handler(self.data, self.ctype, self.filename,
                                  self.payload)

        self.assertEqual(1, self.data["handlercount"])

    def test_import_error(self):
        """Module import errors are logged. No handler added to C{pdata}"""
        # Mock the __import__ builtin
        import_mock = self.mocker.replace("__builtin__.__import__")
        import_mock(self.expected_module_name)
        self.mocker.throw(ImportError())
        # Mock log function
        logexc_mock = self.mocker.replace(logexc, passthrough=False)
        logexc_mock(ANY)
        # Mock the print_exc function
        print_exc_mock = self.mocker.replace("traceback.print_exc",
                                             passthrough=False)
        print_exc_mock(ARGS, KWARGS)
        # Activate mocks
        self.mocker.replay()

        partwalker_handle_handler(self.data, self.ctype, self.filename,
                                  self.payload)

        self.assertEqual(0, self.data["handlercount"])

    def test_attribute_error(self):
        """Attribute errors are logged. No handler added to C{pdata}"""
        # Mock the __import__ builtin
        import_mock = self.mocker.replace("__builtin__.__import__")
        import_mock(self.expected_module_name)
        self.mocker.result(self.module_fake)
        # Mock the handle_register function
        handle_reg_mock = self.mocker.replace(handler_register,
                                              passthrough=False)
        handle_reg_mock(self.module_fake, self.data["handlers"],
                        self.data["data"], self.data["frequency"])
        self.mocker.throw(AttributeError())
        # Mock log function
        logexc_mock = self.mocker.replace(logexc, passthrough=False)
        logexc_mock(ANY)
        # Mock the print_exc function
        print_exc_mock = self.mocker.replace("traceback.print_exc",
                                             passthrough=False)
        print_exc_mock(ARGS, KWARGS)
        # Activate mocks
        self.mocker.replay()

        partwalker_handle_handler(self.data, self.ctype, self.filename,
                                  self.payload)

        self.assertEqual(0, self.data["handlercount"])


class TestHandlerHandlePart(MockerTestCase):
    def setUp(self):
        self.data = "fake data"
        self.ctype = "fake ctype"
        self.filename = "fake filename"
        self.payload = "fake payload"
        self.frequency = "once-per-instance"

    def test_normal_version_1(self):
        """
        C{handle_part} is called without C{frequency} for
        C{handler_version} == 1.
        """
        # Build a mock part-handler module
        mod_mock = self.mocker.mock()
        getattr(mod_mock, "frequency")
        self.mocker.result("once-per-instance")
        getattr(mod_mock, "handler_version")
        self.mocker.result(1)
        mod_mock.handle_part(self.data, self.ctype, self.filename,
                             self.payload)
        self.mocker.replay()

        handler_handle_part(mod_mock, self.data, self.ctype, self.filename,
                            self.payload, self.frequency)

    def test_normal_version_2(self):
        """
        C{handle_part} is called with C{frequency} for
        C{handler_version} == 2.
        """
        # Build a mock part-handler module
        mod_mock = self.mocker.mock()
        getattr(mod_mock, "frequency")
        self.mocker.result("once-per-instance")
        getattr(mod_mock, "handler_version")
        self.mocker.result(2)
        mod_mock.handle_part(self.data, self.ctype, self.filename,
                             self.payload, self.frequency)
        self.mocker.replay()

        handler_handle_part(mod_mock, self.data, self.ctype, self.filename,
                            self.payload, self.frequency)

    def test_modfreq_per_always(self):
        """
        C{handle_part} is called regardless of frequency if nofreq is always.
        """
        self.frequency = "once"
        # Build a mock part-handler module
        mod_mock = self.mocker.mock()
        getattr(mod_mock, "frequency")
        self.mocker.result("always")
        getattr(mod_mock, "handler_version")
        self.mocker.result(1)
        mod_mock.handle_part(self.data, self.ctype, self.filename,
                             self.payload)
        self.mocker.replay()

        handler_handle_part(mod_mock, self.data, self.ctype, self.filename,
                            self.payload, self.frequency)

    def test_no_handle_when_modfreq_once(self):
        """C{handle_part} is not called if frequency is once"""
        self.frequency = "once"
        # Build a mock part-handler module
        mod_mock = self.mocker.mock()
        getattr(mod_mock, "frequency")
        self.mocker.result("once-per-instance")
        self.mocker.replay()

        handler_handle_part(mod_mock, self.data, self.ctype, self.filename,
                            self.payload, self.frequency)

    def test_exception_is_caught(self):
        """Exceptions within C{handle_part} are caught and logged."""
        # Build a mock part-handler module
        mod_mock = self.mocker.mock()
        getattr(mod_mock, "frequency")
        self.mocker.result("once-per-instance")
        getattr(mod_mock, "handler_version")
        self.mocker.result(1)
        mod_mock.handle_part(self.data, self.ctype, self.filename,
                             self.payload)
        self.mocker.throw(Exception())
        # Mock log function
        logexc_mock = self.mocker.replace(logexc, passthrough=False)
        logexc_mock(ANY)
        # Mock the print_exc function
        print_exc_mock = self.mocker.replace("traceback.print_exc",
                                             passthrough=False)
        print_exc_mock(ARGS, KWARGS)
        self.mocker.replay()

        handler_handle_part(mod_mock, self.data, self.ctype, self.filename,
                            self.payload, self.frequency)


class TestCmdlineUrl(MockerTestCase):
    def test_invalid_content(self):
        url = "http://example.com/foo"
        key = "mykey"
        payload = "0"
        cmdline = "ro %s=%s bar=1" % (key, url)

        mock_readurl = self.mocker.replace(readurl, passthrough=False)
        mock_readurl(url)
        self.mocker.result(payload)

        self.mocker.replay()

        self.assertEqual((key, url, None),
            get_cmdline_url(names=[key], starts="xxxxxx", cmdline=cmdline))

    def test_valid_content(self):
        url = "http://example.com/foo"
        key = "mykey"
        payload = "xcloud-config\nmydata: foo\nbar: wark\n"
        cmdline = "ro %s=%s bar=1" % (key, url)

        mock_readurl = self.mocker.replace(readurl, passthrough=False)
        mock_readurl(url)
        self.mocker.result(payload)

        self.mocker.replay()

        self.assertEqual((key, url, payload),
            get_cmdline_url(names=[key], starts="xcloud-config",
                            cmdline=cmdline))

    def test_no_key_found(self):
        url = "http://example.com/foo"
        key = "mykey"
        cmdline = "ro %s=%s bar=1" % (key, url)

        self.mocker.replace(readurl, passthrough=False)
        self.mocker.replay()

        self.assertEqual((None, None, None),
            get_cmdline_url(names=["does-not-appear"],
                starts="#cloud-config", cmdline=cmdline))

# vi: ts=4 expandtab
