"""Tests for handling of userdata within cloud init."""

import StringIO

import logging
import os

from email.mime.base import MIMEBase

from mocker import MockerTestCase

from cloudinit import log
from cloudinit import sources
from cloudinit import stages

INSTANCE_ID = "i-testing"


class FakeDataSource(sources.DataSource):

    def __init__(self, userdata):
        sources.DataSource.__init__(self, {}, None, None)
        self.metadata = {'instance-id': INSTANCE_ID}
        self.userdata_raw = userdata


# FIXME: these tests shouldn't be checking log output??
# Weirddddd...


class TestConsumeUserData(MockerTestCase):

    def setUp(self):
        MockerTestCase.setUp(self)
        # Replace the write so no actual files
        # get written out...
        self.mock_write = self.mocker.replace("cloudinit.util.write_file",
            passthrough=False)
        self._log = None
        self._log_file = None
        self._log_handler = None

    def tearDown(self):
        MockerTestCase.tearDown(self)
        if self._log_handler and self._log:
            self._log.removeHandler(self._log_handler)

    def capture_log(self, lvl=logging.DEBUG):
        log_file = StringIO.StringIO()
        self._log_handler = logging.StreamHandler(log_file)
        self._log_handler.setLevel(lvl)
        self._log = log.getLogger()
        self._log.addHandler(self._log_handler)
        return log_file

    def test_unhandled_type_warning(self):
        """Raw text without magic is ignored but shows warning."""
        ci = stages.Init()
        data = "arbitrary text\n"
        ci.datasource = FakeDataSource(data)

        self.mock_write(ci.paths.get_ipath("cloud_config"), "", 0600)
        self.mocker.replay()

        log_file = self.capture_log(logging.WARNING)
        ci.fetch()
        ci.consume_userdata()
        self.assertIn(
            "Unhandled non-multipart (text/x-not-multipart) userdata:",
            log_file.getvalue())

    def test_mime_text_plain(self):
        """Mime message of type text/plain is ignored but shows warning."""
        ci = stages.Init()
        message = MIMEBase("text", "plain")
        message.set_payload("Just text")
        ci.datasource = FakeDataSource(message.as_string())

        self.mock_write(ci.paths.get_ipath("cloud_config"), "", 0600)
        self.mocker.replay()

        log_file = self.capture_log(logging.WARNING)
        ci.fetch()
        ci.consume_userdata()
        self.assertIn(
            "Unhandled unknown content-type (text/plain)",
            log_file.getvalue())

    def test_shellscript(self):
        """Raw text starting #!/bin/sh is treated as script."""
        ci = stages.Init()
        script = "#!/bin/sh\necho hello\n"
        ci.datasource = FakeDataSource(script)

        outpath = os.path.join(ci.paths.get_ipath_cur("scripts"), "part-001")
        self.mock_write(ci.paths.get_ipath("cloud_config"), "", 0600)
        self.mock_write(outpath, script, 0700)
        self.mocker.replay()

        log_file = self.capture_log(logging.WARNING)
        ci.fetch()
        ci.consume_userdata()
        self.assertEqual("", log_file.getvalue())

    def test_mime_text_x_shellscript(self):
        """Mime message of type text/x-shellscript is treated as script."""
        ci = stages.Init()
        script = "#!/bin/sh\necho hello\n"
        message = MIMEBase("text", "x-shellscript")
        message.set_payload(script)
        ci.datasource = FakeDataSource(message.as_string())

        outpath = os.path.join(ci.paths.get_ipath_cur("scripts"), "part-001")
        self.mock_write(ci.paths.get_ipath("cloud_config"), "", 0600)
        self.mock_write(outpath, script, 0700)
        self.mocker.replay()

        log_file = self.capture_log(logging.WARNING)
        ci.fetch()
        ci.consume_userdata()
        self.assertEqual("", log_file.getvalue())

    def test_mime_text_plain_shell(self):
        """Mime type text/plain starting #!/bin/sh is treated as script."""
        ci = stages.Init()
        script = "#!/bin/sh\necho hello\n"
        message = MIMEBase("text", "plain")
        message.set_payload(script)
        ci.datasource = FakeDataSource(message.as_string())

        outpath = os.path.join(ci.paths.get_ipath_cur("scripts"), "part-001")
        self.mock_write(outpath, script, 0700)
        self.mock_write(ci.paths.get_ipath("cloud_config"), "", 0600)
        self.mocker.replay()

        log_file = self.capture_log(logging.WARNING)
        ci.fetch()
        ci.consume_userdata()
        self.assertEqual("", log_file.getvalue())
