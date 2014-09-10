import os

from mocker import MockerTestCase, ARGS, KWARGS

from cloudinit import handlers
from cloudinit import helpers
from cloudinit import importer
from cloudinit import settings
from cloudinit import url_helper
from cloudinit import util


class FakeModule(handlers.Handler):
    def __init__(self):
        handlers.Handler.__init__(self, settings.PER_ALWAYS)
        self.types = []

    def list_types(self):
        return self.types

    def handle_part(self, data, ctype, filename, payload, frequency):
        pass


class TestWalkerHandleHandler(MockerTestCase):

    def setUp(self):

        MockerTestCase.setUp(self)

        self.data = {
            "handlercount": 0,
            "frequency": "",
            "handlerdir": self.makeDir(),
            "handlers": helpers.ContentHandlers(),
            "data": None}

        self.expected_module_name = "part-handler-%03d" % (
            self.data["handlercount"],)
        expected_file_name = "%s.py" % self.expected_module_name
        expected_file_fullname = os.path.join(self.data["handlerdir"],
                                              expected_file_name)
        self.module_fake = FakeModule()
        self.ctype = None
        self.filename = None
        self.payload = "dummy payload"

        # Mock the write_file function
        write_file_mock = self.mocker.replace(util.write_file,
                                              passthrough=False)
        write_file_mock(expected_file_fullname, self.payload, 0600)

    def test_no_errors(self):
        """Payload gets written to file and added to C{pdata}."""
        import_mock = self.mocker.replace(importer.import_module,
                                          passthrough=False)
        import_mock(self.expected_module_name)
        self.mocker.result(self.module_fake)
        self.mocker.replay()

        handlers.walker_handle_handler(self.data, self.ctype, self.filename,
                                       self.payload)

        self.assertEqual(1, self.data["handlercount"])

    def test_import_error(self):
        """Module import errors are logged. No handler added to C{pdata}."""
        import_mock = self.mocker.replace(importer.import_module,
                                          passthrough=False)
        import_mock(self.expected_module_name)
        self.mocker.throw(ImportError())
        self.mocker.replay()

        handlers.walker_handle_handler(self.data, self.ctype, self.filename,
                                       self.payload)

        self.assertEqual(0, self.data["handlercount"])

    def test_attribute_error(self):
        """Attribute errors are logged. No handler added to C{pdata}."""
        import_mock = self.mocker.replace(importer.import_module,
                                          passthrough=False)
        import_mock(self.expected_module_name)
        self.mocker.result(self.module_fake)
        self.mocker.throw(AttributeError())
        self.mocker.replay()

        handlers.walker_handle_handler(self.data, self.ctype, self.filename,
                                       self.payload)

        self.assertEqual(0, self.data["handlercount"])


class TestHandlerHandlePart(MockerTestCase):

    def setUp(self):
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
        mod_mock = self.mocker.mock()
        getattr(mod_mock, "frequency")
        self.mocker.result(settings.PER_INSTANCE)
        getattr(mod_mock, "handler_version")
        self.mocker.result(1)
        mod_mock.handle_part(self.data, self.ctype, self.filename,
                             self.payload)
        self.mocker.replay()

        handlers.run_part(mod_mock, self.data, self.filename,
                          self.payload, self.frequency, self.headers)

    def test_normal_version_2(self):
        """
        C{handle_part} is called with C{frequency} for
        C{handler_version} == 2.
        """
        mod_mock = self.mocker.mock()
        getattr(mod_mock, "frequency")
        self.mocker.result(settings.PER_INSTANCE)
        getattr(mod_mock, "handler_version")
        self.mocker.result(2)
        mod_mock.handle_part(self.data, self.ctype, self.filename,
                             self.payload, self.frequency)
        self.mocker.replay()

        handlers.run_part(mod_mock, self.data, self.filename,
                          self.payload, self.frequency, self.headers)

    def test_modfreq_per_always(self):
        """
        C{handle_part} is called regardless of frequency if nofreq is always.
        """
        self.frequency = "once"
        mod_mock = self.mocker.mock()
        getattr(mod_mock, "frequency")
        self.mocker.result(settings.PER_ALWAYS)
        getattr(mod_mock, "handler_version")
        self.mocker.result(1)
        mod_mock.handle_part(self.data, self.ctype, self.filename,
                             self.payload)
        self.mocker.replay()

        handlers.run_part(mod_mock, self.data, self.filename,
                          self.payload, self.frequency, self.headers)

    def test_no_handle_when_modfreq_once(self):
        """C{handle_part} is not called if frequency is once."""
        self.frequency = "once"
        mod_mock = self.mocker.mock()
        getattr(mod_mock, "frequency")
        self.mocker.result(settings.PER_ONCE)
        self.mocker.replay()

        handlers.run_part(mod_mock, self.data, self.filename,
                          self.payload, self.frequency, self.headers)

    def test_exception_is_caught(self):
        """Exceptions within C{handle_part} are caught and logged."""
        mod_mock = self.mocker.mock()
        getattr(mod_mock, "frequency")
        self.mocker.result(settings.PER_INSTANCE)
        getattr(mod_mock, "handler_version")
        self.mocker.result(1)
        mod_mock.handle_part(self.data, self.ctype, self.filename,
                             self.payload)
        self.mocker.throw(Exception())
        self.mocker.replay()

        handlers.run_part(mod_mock, self.data, self.filename,
                          self.payload, self.frequency, self.headers)


class TestCmdlineUrl(MockerTestCase):
    def test_invalid_content(self):
        url = "http://example.com/foo"
        key = "mykey"
        payload = "0"
        cmdline = "ro %s=%s bar=1" % (key, url)

        mock_readurl = self.mocker.replace(url_helper.readurl,
                                           passthrough=False)
        mock_readurl(url, ARGS, KWARGS)
        self.mocker.result(url_helper.StringResponse(payload))
        self.mocker.replay()

        self.assertEqual((key, url, None),
            util.get_cmdline_url(names=[key], starts="xxxxxx",
                                 cmdline=cmdline))

    def test_valid_content(self):
        url = "http://example.com/foo"
        key = "mykey"
        payload = "xcloud-config\nmydata: foo\nbar: wark\n"
        cmdline = "ro %s=%s bar=1" % (key, url)

        mock_readurl = self.mocker.replace(url_helper.readurl,
                                           passthrough=False)
        mock_readurl(url, ARGS, KWARGS)
        self.mocker.result(url_helper.StringResponse(payload))
        self.mocker.replay()

        self.assertEqual((key, url, payload),
            util.get_cmdline_url(names=[key], starts="xcloud-config",
                            cmdline=cmdline))

    def test_no_key_found(self):
        url = "http://example.com/foo"
        key = "mykey"
        cmdline = "ro %s=%s bar=1" % (key, url)

        self.mocker.replace(url_helper.readurl, passthrough=False)
        self.mocker.result(url_helper.StringResponse(""))
        self.mocker.replay()

        self.assertEqual((None, None, None),
            util.get_cmdline_url(names=["does-not-appear"],
                starts="#cloud-config", cmdline=cmdline))

# vi: ts=4 expandtab
