"""Tests for handling of userdata within cloud init."""

import StringIO

import logging
import os

from email.mime.base import MIMEBase

from cloudinit import handlers
from cloudinit import helpers as c_helpers
from cloudinit import log
from cloudinit import sources
from cloudinit import stages
from cloudinit import util

INSTANCE_ID = "i-testing"

from tests.unittests import helpers


class FakeDataSource(sources.DataSource):

    def __init__(self, userdata):
        sources.DataSource.__init__(self, {}, None, None)
        self.metadata = {'instance-id': INSTANCE_ID}
        self.userdata_raw = userdata


# FIXME: these tests shouldn't be checking log output??
# Weirddddd...
class TestConsumeUserData(helpers.FilesystemMockingTestCase):

    def setUp(self):
        helpers.FilesystemMockingTestCase.setUp(self)
        self._log = None
        self._log_file = None
        self._log_handler = None

    def tearDown(self):
        helpers.FilesystemMockingTestCase.tearDown(self)
        if self._log_handler and self._log:
            self._log.removeHandler(self._log_handler)

    def capture_log(self, lvl=logging.DEBUG):
        log_file = StringIO.StringIO()
        self._log_handler = logging.StreamHandler(log_file)
        self._log_handler.setLevel(lvl)
        self._log = log.getLogger()
        self._log.addHandler(self._log_handler)
        return log_file

    def test_merging_cloud_config(self):
        blob = '''
#cloud-config
a: b
e: f
run:
 - b
 - c
'''
        message1 = MIMEBase("text", "cloud-config")
        message1.set_payload(blob)

        blob2 = '''
#cloud-config
a: e
e: g
run:
 - stuff
 - morestuff
'''
        message2 = MIMEBase("text", "cloud-config")
        message2['X-Merge-Type'] = ('dict(recurse_array,'
                                    'recurse_str)+list(append)+str(append)')
        message2.set_payload(blob2)

        blob3 = '''
#cloud-config
e:
 - 1
 - 2
 - 3
p: 1
'''
        message3 = MIMEBase("text", "cloud-config")
        message3.set_payload(blob3)

        messages = [message1, message2, message3]

        paths = c_helpers.Paths({}, ds=FakeDataSource(''))
        cloud_cfg = handlers.cloud_config.CloudConfigPartHandler(paths)

        new_root = self.makeDir()
        self.patchUtils(new_root)
        self.patchOS(new_root)
        cloud_cfg.handle_part(None, handlers.CONTENT_START, None, None, None,
                              None)
        for i, m in enumerate(messages):
            headers = dict(m)
            fn = "part-%s" % (i + 1)
            payload = m.get_payload(decode=True)
            cloud_cfg.handle_part(None, headers['Content-Type'],
                                  fn, payload, None, headers)
        cloud_cfg.handle_part(None, handlers.CONTENT_END, None, None, None,
                              None)
        contents = util.load_file(paths.get_ipath('cloud_config'))
        contents = util.load_yaml(contents)
        self.assertEquals(contents['run'], ['b', 'c', 'stuff', 'morestuff'])
        self.assertEquals(contents['a'], 'be')
        self.assertEquals(contents['e'], [1, 2, 3])
        self.assertEquals(contents['p'], 1)

    def test_unhandled_type_warning(self):
        """Raw text without magic is ignored but shows warning."""
        ci = stages.Init()
        data = "arbitrary text\n"
        ci.datasource = FakeDataSource(data)

        mock_write = self.mocker.replace("cloudinit.util.write_file",
                                              passthrough=False)
        mock_write(ci.paths.get_ipath("cloud_config"), "", 0600)
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

        mock_write = self.mocker.replace("cloudinit.util.write_file",
                                              passthrough=False)
        mock_write(ci.paths.get_ipath("cloud_config"), "", 0600)
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
        mock_write = self.mocker.replace("cloudinit.util.write_file",
                                              passthrough=False)
        mock_write(ci.paths.get_ipath("cloud_config"), "", 0600)
        mock_write(outpath, script, 0700)
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
        mock_write = self.mocker.replace("cloudinit.util.write_file",
                                              passthrough=False)
        mock_write(ci.paths.get_ipath("cloud_config"), "", 0600)
        mock_write(outpath, script, 0700)
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
        mock_write = self.mocker.replace("cloudinit.util.write_file",
                                         passthrough=False)
        mock_write(outpath, script, 0700)
        mock_write(ci.paths.get_ipath("cloud_config"), "", 0600)
        self.mocker.replay()

        log_file = self.capture_log(logging.WARNING)
        ci.fetch()
        ci.consume_userdata()
        self.assertEqual("", log_file.getvalue())
