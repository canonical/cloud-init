# This file is part of cloud-init. See LICENSE file for license information.

import logging
import os
from types import SimpleNamespace

import pytest

from cloudinit import handlers, helpers, settings, url_helper, util
from cloudinit.cmd import main
from tests.unittests.helpers import mock


@pytest.fixture
def walker_data(tmp_path):
    data = {
        "handlercount": 0,
        "frequency": "",
        "handlerdir": str(tmp_path),
        "handlers": helpers.ContentHandlers(),
        "data": None,
    }

    expected_module_name = "part-handler-%03d" % (data["handlercount"],)
    expected_file_name = "%s.py" % expected_module_name
    expected_file_fullname = os.path.join(
        data["handlerdir"], expected_file_name
    )

    return SimpleNamespace(
        data=data,
        expected_module_name=expected_module_name,
        expected_file_fullname=expected_file_fullname,
        module_fake=FakeModule(),
        ctype=None,
        filename=None,
        payload="dummy payload",
    )


@pytest.fixture
def m_write_file():
    """Mock the write_file() function."""
    with mock.patch("cloudinit.util.write_file") as mock_write:
        yield mock_write


@pytest.fixture
def handler_data():
    return SimpleNamespace(
        data="fake data",
        ctype="fake ctype",
        filename="fake filename",
        payload="fake payload",
        frequency=settings.PER_INSTANCE,
        headers={"Content-Type": "fake ctype"},
    )


class FakeModule(handlers.Handler):
    def __init__(self):
        handlers.Handler.__init__(self, settings.PER_ALWAYS)
        self.types = []

    def list_types(self):
        return self.types

    def handle_part(self, data, ctype, filename, payload, frequency):
        pass


class TestWalkerHandleHandler:
    def test_no_errors(self, walker_data, m_write_file):
        """Payload gets written to file and added to C{pdata}."""
        with mock.patch(
            "cloudinit.importer.import_module",
            return_value=walker_data.module_fake,
        ) as mockobj:
            handlers.walker_handle_handler(
                walker_data.data,
                walker_data.ctype,
                walker_data.filename,
                walker_data.payload,
            )
            mockobj.assert_called_once_with(walker_data.expected_module_name)
        m_write_file.assert_called_once_with(
            walker_data.expected_file_fullname, walker_data.payload, 0o600
        )
        assert walker_data.data["handlercount"] == 1

    def test_import_error(self, walker_data, m_write_file):
        """Module import errors are logged. No handler added to C{pdata}."""
        with mock.patch(
            "cloudinit.importer.import_module", side_effect=ImportError
        ) as mockobj:
            handlers.walker_handle_handler(
                walker_data.data,
                walker_data.ctype,
                walker_data.filename,
                walker_data.payload,
            )
            mockobj.assert_called_once_with(walker_data.expected_module_name)
        m_write_file.assert_called_once_with(
            walker_data.expected_file_fullname, walker_data.payload, 0o600
        )
        assert walker_data.data["handlercount"] == 0

    def test_attribute_error(self, walker_data, m_write_file):
        """Attribute errors are logged. No handler added to C{pdata}."""
        with mock.patch(
            "cloudinit.importer.import_module",
            side_effect=AttributeError,
            return_value=walker_data.module_fake,
        ) as mockobj:
            handlers.walker_handle_handler(
                walker_data.data,
                walker_data.ctype,
                walker_data.filename,
                walker_data.payload,
            )
            mockobj.assert_called_once_with(walker_data.expected_module_name)
        m_write_file.assert_called_once_with(
            walker_data.expected_file_fullname, walker_data.payload, 0o600
        )
        assert walker_data.data["handlercount"] == 0


class TestHandlerHandlePart:
    def test_normal_version_1(self, handler_data):
        """
        C{handle_part} is called without C{frequency} for
        C{handler_version} == 1.
        """
        mod_mock = mock.Mock(
            frequency=settings.PER_INSTANCE, handler_version=1
        )
        handlers.run_part(
            mod_mock,
            handler_data.data,
            handler_data.filename,
            handler_data.payload,
            handler_data.frequency,
            handler_data.headers,
        )
        # Assert that the handle_part() method of the mock object got
        # called with the expected arguments.
        mod_mock.handle_part.assert_called_once_with(
            handler_data.data,
            handler_data.ctype,
            handler_data.filename,
            handler_data.payload,
        )

    def test_normal_version_2(self, handler_data):
        """
        C{handle_part} is called with C{frequency} for
        C{handler_version} == 2.
        """
        mod_mock = mock.Mock(
            frequency=settings.PER_INSTANCE, handler_version=2
        )
        handlers.run_part(
            mod_mock,
            handler_data.data,
            handler_data.filename,
            handler_data.payload,
            handler_data.frequency,
            handler_data.headers,
        )
        # Assert that the handle_part() method of the mock object got
        # called with the expected arguments.
        mod_mock.handle_part.assert_called_once_with(
            handler_data.data,
            handler_data.ctype,
            handler_data.filename,
            handler_data.payload,
            settings.PER_INSTANCE,
        )

    def test_modfreq_per_always(self, handler_data):
        """
        C{handle_part} is called regardless of frequency if nofreq is always.
        """
        handler_data.frequency = "once"
        mod_mock = mock.Mock(frequency=settings.PER_ALWAYS, handler_version=1)
        handlers.run_part(
            mod_mock,
            handler_data.data,
            handler_data.filename,
            handler_data.payload,
            handler_data.frequency,
            handler_data.headers,
        )
        # Assert that the handle_part() method of the mock object got
        # called with the expected arguments.
        mod_mock.handle_part.assert_called_once_with(
            handler_data.data,
            handler_data.ctype,
            handler_data.filename,
            handler_data.payload,
        )

    def test_no_handle_when_modfreq_once(self, handler_data):
        """C{handle_part} is not called if frequency is once."""
        handler_data.frequency = "once"
        mod_mock = mock.Mock(frequency=settings.PER_ONCE)
        handlers.run_part(
            mod_mock,
            handler_data.data,
            handler_data.filename,
            handler_data.payload,
            handler_data.frequency,
            handler_data.headers,
        )
        assert 0 == mod_mock.handle_part.call_count

    def test_exception_is_caught(self, handler_data):
        """Exceptions within C{handle_part} are caught and logged."""
        mod_mock = mock.Mock(
            frequency=settings.PER_INSTANCE, handler_version=1
        )
        mod_mock.handle_part.side_effect = Exception
        handlers.run_part(
            mod_mock,
            handler_data.data,
            handler_data.filename,
            handler_data.payload,
            handler_data.frequency,
            handler_data.headers,
        )
        mod_mock.handle_part.assert_called_once_with(
            handler_data.data,
            handler_data.ctype,
            handler_data.filename,
            handler_data.payload,
        )


class FakeResponse:
    def __init__(self, content, status_code=200):
        self._content = content
        self._remaining_content = content
        self.status_code = status_code
        self.encoding = None

    @property
    def content(self):
        return self._remaining_content

    def iter_content(self, chunk_size, *_, **__):
        iterators = [iter(self._content)] * chunk_size
        for chunk in zip(*iterators):
            self._remaining_content = self._remaining_content[chunk_size:]
            yield bytes(chunk)


class TestCmdlineUrl:
    def test_parse_cmdline_url_nokey_raises_keyerror(self):
        with pytest.raises(KeyError):
            main.parse_cmdline_url("root=foo bar single")

    def test_parse_cmdline_url_found(self):
        cmdline = "root=foo bar single url=http://example.com arg1 -v"
        assert ("url", "http://example.com") == main.parse_cmdline_url(cmdline)

    @mock.patch("cloudinit.cmd.main.url_helper.read_file_or_url")
    def test_invalid_content(self, m_read, tmpdir):
        key = "cloud-config-url"
        url = "http://example.com/foo"
        cmdline = "ro %s=%s bar=1" % (key, url)
        m_read.return_value = url_helper.StringResponse(
            b"unexpected blob", "http://example.com/"
        )

        fpath = tmpdir.join("ccfile")
        lvl, msg = main.attempt_cmdline_url(
            fpath, network=True, cmdline=cmdline
        )
        assert logging.WARN == lvl
        assert url in msg
        assert False is os.path.exists(fpath)

    @mock.patch("cloudinit.cmd.main.url_helper.read_file_or_url")
    def test_invalid_content_url(self, m_read, tmpdir):
        key = "cloud-config-url"
        url = "http://example.com/foo"
        cmdline = "ro %s=%s bar=1" % (key, url)
        response = mock.Mock()
        response.iter_content.return_value = iter(
            (b"unexpected blob", StopIteration)
        )
        response.status_code = 200
        m_read.return_value = url_helper.UrlResponse(response)

        fpath = tmpdir.join("ccfile")
        lvl, msg = main.attempt_cmdline_url(
            fpath, network=True, cmdline=cmdline
        )
        assert logging.WARN == lvl
        assert url in msg
        assert False is os.path.exists(fpath)

    @mock.patch("cloudinit.cmd.main.url_helper.read_file_or_url")
    def test_valid_content(self, m_read, tmpdir):
        url = "http://example.com/foo"
        payload = b"#cloud-config\nmydata: foo\nbar: wark\n"
        cmdline = "ro %s=%s bar=1" % ("cloud-config-url", url)

        m_read.return_value = url_helper.StringResponse(
            payload, "http://example.com"
        )
        fpath = tmpdir.join("ccfile")
        lvl, msg = main.attempt_cmdline_url(
            fpath, network=True, cmdline=cmdline
        )
        assert util.load_binary_file(fpath) == payload
        assert logging.INFO == lvl
        assert url in msg

    @mock.patch("cloudinit.cmd.main.url_helper.read_file_or_url")
    def test_valid_content_url(self, m_read, tmpdir):
        url = "http://example.com/foo"
        payload = b"#cloud-config\nmydata: foo\nbar: wark\n"
        cmdline = "ro %s=%s bar=1" % ("cloud-config-url", url)

        response = FakeResponse(payload)
        m_read.return_value = url_helper.UrlResponse(response)

        fpath = tmpdir.join("ccfile")
        lvl, msg = main.attempt_cmdline_url(
            fpath, network=True, cmdline=cmdline
        )
        assert util.load_binary_file(fpath) == payload
        assert logging.INFO == lvl
        assert url in msg

    @mock.patch("cloudinit.cmd.main.url_helper.read_file_or_url")
    def test_no_key_found(self, m_read, tmpdir):
        cmdline = "ro mykey=http://example.com/foo root=foo"
        fpath = tmpdir.join("ccfile")
        lvl, _msg = main.attempt_cmdline_url(
            fpath, network=True, cmdline=cmdline
        )

        m_read.assert_not_called()
        assert False is os.path.exists(fpath)
        assert logging.DEBUG == lvl

    @mock.patch("cloudinit.cmd.main.url_helper.read_file_or_url")
    def test_exception_warns(self, m_read, tmpdir):
        url = "http://example.com/foo"
        cmdline = "ro cloud-config-url=%s root=LABEL=bar" % url
        fpath = tmpdir.join("ccfile")
        m_read.side_effect = url_helper.UrlError(
            cause="Unexpected Error", url="http://example.com/foo"
        )

        lvl, msg = main.attempt_cmdline_url(
            fpath, network=True, cmdline=cmdline
        )
        assert logging.WARN == lvl
        assert url in msg
        assert False is os.path.exists(fpath)
