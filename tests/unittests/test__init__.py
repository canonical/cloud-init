# This file is part of cloud-init. See LICENSE file for license information.

import os
import shutil
import tempfile

from cloudinit import handlers
from cloudinit import helpers
from cloudinit import settings
from cloudinit import url_helper
from cloudinit import util

from .helpers import TestCase, ExitStack, mock


class FakeModule(handlers.Handler):
    def __init__(self):
        handlers.Handler.__init__(self, settings.PER_ALWAYS)
        self.types = []

    def list_types(self):
        return self.types

    def handle_part(self, data, ctype, filename, payload, frequency):
        pass


class TestWalkerHandleHandler(TestCase):

    def setUp(self):
        super(TestWalkerHandleHandler, self).setUp()
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir)

        self.data = {
            "handlercount": 0,
            "frequency": "",
            "handlerdir": tmpdir,
            "handlers": helpers.ContentHandlers(),
            "data": None}

        self.expected_module_name = "part-handler-%03d" % (
            self.data["handlercount"],)
        expected_file_name = "%s.py" % self.expected_module_name
        self.expected_file_fullname = os.path.join(
            self.data["handlerdir"], expected_file_name)
        self.module_fake = FakeModule()
        self.ctype = None
        self.filename = None
        self.payload = "dummy payload"

        # Mock the write_file() function.  We'll assert that it got called as
        # expected in each of the individual tests.
        resources = ExitStack()
        self.addCleanup(resources.close)
        self.write_file_mock = resources.enter_context(
            mock.patch('cloudinit.util.write_file'))

    def test_no_errors(self):
        """Payload gets written to file and added to C{pdata}."""
        with mock.patch('cloudinit.importer.import_module',
                        return_value=self.module_fake) as mockobj:
            handlers.walker_handle_handler(self.data, self.ctype,
                                           self.filename, self.payload)
            mockobj.assert_called_once_with(self.expected_module_name)
        self.write_file_mock.assert_called_once_with(
            self.expected_file_fullname, self.payload, 0o600)
        self.assertEqual(self.data['handlercount'], 1)

    def test_import_error(self):
        """Module import errors are logged. No handler added to C{pdata}."""
        with mock.patch('cloudinit.importer.import_module',
                        side_effect=ImportError) as mockobj:
            handlers.walker_handle_handler(self.data, self.ctype,
                                           self.filename, self.payload)
            mockobj.assert_called_once_with(self.expected_module_name)
        self.write_file_mock.assert_called_once_with(
            self.expected_file_fullname, self.payload, 0o600)
        self.assertEqual(self.data['handlercount'], 0)

    def test_attribute_error(self):
        """Attribute errors are logged. No handler added to C{pdata}."""
        with mock.patch('cloudinit.importer.import_module',
                        side_effect=AttributeError,
                        return_value=self.module_fake) as mockobj:
            handlers.walker_handle_handler(self.data, self.ctype,
                                           self.filename, self.payload)
            mockobj.assert_called_once_with(self.expected_module_name)
        self.write_file_mock.assert_called_once_with(
            self.expected_file_fullname, self.payload, 0o600)
        self.assertEqual(self.data['handlercount'], 0)


class TestHandlerHandlePart(TestCase):

    def setUp(self):
        super(TestHandlerHandlePart, self).setUp()
        self.data = "fake data"
        self.ctype = "fake ctype"
        self.filename = "fake filename"
        self.payload = "fake payload"
        self.frequency = settings.PER_INSTANCE
        self.headers = {
            'Content-Type': self.ctype,
        }

    def test_normal_version_1(self):
        """
        C{handle_part} is called without C{frequency} for
        C{handler_version} == 1.
        """
        mod_mock = mock.Mock(frequency=settings.PER_INSTANCE,
                             handler_version=1)
        handlers.run_part(mod_mock, self.data, self.filename, self.payload,
                          self.frequency, self.headers)
        # Assert that the handle_part() method of the mock object got
        # called with the expected arguments.
        mod_mock.handle_part.assert_called_once_with(
            self.data, self.ctype, self.filename, self.payload)

    def test_normal_version_2(self):
        """
        C{handle_part} is called with C{frequency} for
        C{handler_version} == 2.
        """
        mod_mock = mock.Mock(frequency=settings.PER_INSTANCE,
                             handler_version=2)
        handlers.run_part(mod_mock, self.data, self.filename, self.payload,
                          self.frequency, self.headers)
        # Assert that the handle_part() method of the mock object got
        # called with the expected arguments.
        mod_mock.handle_part.assert_called_once_with(
            self.data, self.ctype, self.filename, self.payload,
            settings.PER_INSTANCE)

    def test_modfreq_per_always(self):
        """
        C{handle_part} is called regardless of frequency if nofreq is always.
        """
        self.frequency = "once"
        mod_mock = mock.Mock(frequency=settings.PER_ALWAYS,
                             handler_version=1)
        handlers.run_part(mod_mock, self.data, self.filename, self.payload,
                          self.frequency, self.headers)
        # Assert that the handle_part() method of the mock object got
        # called with the expected arguments.
        mod_mock.handle_part.assert_called_once_with(
            self.data, self.ctype, self.filename, self.payload)

    def test_no_handle_when_modfreq_once(self):
        """C{handle_part} is not called if frequency is once."""
        self.frequency = "once"
        mod_mock = mock.Mock(frequency=settings.PER_ONCE)
        handlers.run_part(mod_mock, self.data, self.filename, self.payload,
                          self.frequency, self.headers)
        self.assertEqual(0, mod_mock.handle_part.call_count)

    def test_exception_is_caught(self):
        """Exceptions within C{handle_part} are caught and logged."""
        mod_mock = mock.Mock(frequency=settings.PER_INSTANCE,
                             handler_version=1)
        mod_mock.handle_part.side_effect = Exception
        try:
            handlers.run_part(mod_mock, self.data, self.filename,
                              self.payload, self.frequency, self.headers)
        except Exception:
            self.fail("Exception was not caught in handle_part")

        mod_mock.handle_part.assert_called_once_with(
            self.data, self.ctype, self.filename, self.payload)


class TestCmdlineUrl(TestCase):
    def test_invalid_content(self):
        url = "http://example.com/foo"
        key = "mykey"
        payload = b"0"
        cmdline = "ro %s=%s bar=1" % (key, url)

        with mock.patch('cloudinit.url_helper.readurl',
                        return_value=url_helper.StringResponse(payload)):
            self.assertEqual(
                util.get_cmdline_url(names=[key], starts="xxxxxx",
                                     cmdline=cmdline),
                (key, url, None))

    def test_valid_content(self):
        url = "http://example.com/foo"
        key = "mykey"
        payload = b"xcloud-config\nmydata: foo\nbar: wark\n"
        cmdline = "ro %s=%s bar=1" % (key, url)

        with mock.patch('cloudinit.url_helper.readurl',
                        return_value=url_helper.StringResponse(payload)):
            self.assertEqual(
                util.get_cmdline_url(names=[key], starts=b"xcloud-config",
                                     cmdline=cmdline),
                (key, url, payload))

    def test_no_key_found(self):
        url = "http://example.com/foo"
        key = "mykey"
        cmdline = "ro %s=%s bar=1" % (key, url)

        with mock.patch('cloudinit.url_helper.readurl',
                        return_value=url_helper.StringResponse(b'')):
            self.assertEqual(
                util.get_cmdline_url(names=["does-not-appear"],
                                     starts="#cloud-config", cmdline=cmdline),
                (None, None, None))


# vi: ts=4 expandtab
