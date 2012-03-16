"""Tests for handling of userdata within cloud init"""

import logging
import StringIO

from email.mime.base import MIMEBase

from mocker import MockerTestCase

import cloudinit
from cloudinit.DataSource import DataSource


instance_id = "i-testing"


class FakeDataSource(DataSource):

    def __init__(self, userdata):
        DataSource.__init__(self)
        self.metadata = {'instance-id': instance_id}
        self.userdata_raw = userdata


class TestConsumeUserData(MockerTestCase):

    _log_handler = None
    _log = None
    log_file = None

    def setUp(self):
        self.mock_write = self.mocker.replace("cloudinit.util.write_file",
            passthrough=False)
        self.mock_write(self.get_ipath("cloud_config"), "", 0600)
        self.capture_log()

    def tearDown(self):
        self._log.removeHandler(self._log_handler)

    @staticmethod
    def get_ipath(name):
        return "%s/instances/%s%s" % (cloudinit.varlibdir, instance_id,
            cloudinit.pathmap[name])

    def capture_log(self):
        self.log_file = StringIO.StringIO()
        self._log_handler = logging.StreamHandler(self.log_file)
        self._log_handler.setLevel(logging.DEBUG)
        self._log = logging.getLogger(cloudinit.logger_name)
        self._log.addHandler(self._log_handler)

    def test_unhandled_type_warning(self):
        """Raw text without magic is ignored but shows warning"""
        self.mocker.replay()
        ci = cloudinit.CloudInit()
        ci.datasource = FakeDataSource("arbitrary text\n")
        ci.consume_userdata()
        self.assertEqual(
            "Unhandled non-multipart userdata starting 'arbitrary text...'\n",
            self.log_file.getvalue())

    def test_mime_text_plain(self):
        """Mime message of type text/plain is ignored without warning"""
        self.mocker.replay()
        ci = cloudinit.CloudInit()
        message = MIMEBase("text", "plain")
        message.set_payload("Just text")
        ci.datasource = FakeDataSource(message.as_string())
        ci.consume_userdata()
        self.assertEqual("", self.log_file.getvalue())

    def test_shellscript(self):
        """Raw text starting #!/bin/sh is treated as script"""
        script = "#!/bin/sh\necho hello\n"
        outpath = cloudinit.get_ipath_cur("scripts") + "/part-001"
        self.mock_write(outpath, script, 0700)
        self.mocker.replay()
        ci = cloudinit.CloudInit()
        ci.datasource = FakeDataSource(script)
        ci.consume_userdata()
        self.assertEqual("", self.log_file.getvalue())

    def test_mime_text_x_shellscript(self):
        """Mime message of type text/x-shellscript is treated as script"""
        script = "#!/bin/sh\necho hello\n"
        outpath = cloudinit.get_ipath_cur("scripts") + "/part-001"
        self.mock_write(outpath, script, 0700)
        self.mocker.replay()
        ci = cloudinit.CloudInit()
        message = MIMEBase("text", "x-shellscript")
        message.set_payload(script)
        ci.datasource = FakeDataSource(message.as_string())
        ci.consume_userdata()
        self.assertEqual("", self.log_file.getvalue())

    def test_mime_text_plain_shell(self):
        """Mime type text/plain starting #!/bin/sh is treated as script"""
        script = "#!/bin/sh\necho hello\n"
        outpath = cloudinit.get_ipath_cur("scripts") + "/part-001"
        self.mock_write(outpath, script, 0700)
        self.mocker.replay()
        ci = cloudinit.CloudInit()
        message = MIMEBase("text", "plain")
        message.set_payload(script)
        ci.datasource = FakeDataSource(message.as_string())
        ci.consume_userdata()
        self.assertEqual("", self.log_file.getvalue())
