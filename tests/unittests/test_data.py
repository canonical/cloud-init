"""Tests for handling of userdata within cloud init."""

import StringIO

import gzip
import logging
import os

from email.mime.application import MIMEApplication
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart

from cloudinit import handlers
from cloudinit import helpers as c_helpers
from cloudinit import log
from cloudinit.settings import (PER_INSTANCE)
from cloudinit import sources
from cloudinit import stages
from cloudinit import util

INSTANCE_ID = "i-testing"

from . import helpers


class FakeDataSource(sources.DataSource):

    def __init__(self, userdata=None, vendordata=None):
        sources.DataSource.__init__(self, {}, None, None)
        self.metadata = {'instance-id': INSTANCE_ID}
        self.userdata_raw = userdata
        self.vendordata_raw = vendordata


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

    def _patchIn(self, root):
        self.restore()
        self.patchOS(root)
        self.patchUtils(root)

    def capture_log(self, lvl=logging.DEBUG):
        log_file = StringIO.StringIO()
        self._log_handler = logging.StreamHandler(log_file)
        self._log_handler.setLevel(lvl)
        self._log = log.getLogger()
        self._log.addHandler(self._log_handler)
        return log_file

    def test_simple_jsonp(self):
        blob = '''
#cloud-config-jsonp
[
     { "op": "add", "path": "/baz", "value": "qux" },
     { "op": "add", "path": "/bar", "value": "qux2" }
]
'''

        ci = stages.Init()
        ci.datasource = FakeDataSource(blob)
        new_root = self.makeDir()
        self.patchUtils(new_root)
        self.patchOS(new_root)
        ci.fetch()
        ci.consume_data()
        cc_contents = util.load_file(ci.paths.get_ipath("cloud_config"))
        cc = util.load_yaml(cc_contents)
        self.assertEquals(2, len(cc))
        self.assertEquals('qux', cc['baz'])
        self.assertEquals('qux2', cc['bar'])

    def test_simple_jsonp_vendor_and_user(self):
        # test that user-data wins over vendor
        user_blob = '''
#cloud-config-jsonp
[
     { "op": "add", "path": "/baz", "value": "qux" },
     { "op": "add", "path": "/bar", "value": "qux2" }
]
'''
        vendor_blob = '''
#cloud-config-jsonp
[
     { "op": "add", "path": "/baz", "value": "quxA" },
     { "op": "add", "path": "/bar", "value": "quxB" },
     { "op": "add", "path": "/foo", "value": "quxC" }
]
'''
        new_root = self.makeDir()
        self._patchIn(new_root)
        initer = stages.Init()
        initer.datasource = FakeDataSource(user_blob, vendordata=vendor_blob)
        initer.read_cfg()
        initer.initialize()
        initer.fetch()
        initer.instancify()
        initer.update()
        initer.cloudify().run('consume_data',
                              initer.consume_data,
                              args=[PER_INSTANCE],
                              freq=PER_INSTANCE)
        mods = stages.Modules(initer)
        (_which_ran, _failures) = mods.run_section('cloud_init_modules')
        cfg = mods.cfg
        self.assertIn('vendor_data', cfg)
        self.assertEquals('qux', cfg['baz'])
        self.assertEquals('qux2', cfg['bar'])
        self.assertEquals('quxC', cfg['foo'])

    def test_simple_jsonp_no_vendor_consumed(self):
        # make sure that vendor data is not consumed
        user_blob = '''
#cloud-config-jsonp
[
     { "op": "add", "path": "/baz", "value": "qux" },
     { "op": "add", "path": "/bar", "value": "qux2" },
     { "op": "add", "path": "/vendor_data", "value": {"enabled": "false"}}
]
'''
        vendor_blob = '''
#cloud-config-jsonp
[
     { "op": "add", "path": "/baz", "value": "quxA" },
     { "op": "add", "path": "/bar", "value": "quxB" },
     { "op": "add", "path": "/foo", "value": "quxC" }
]
'''
        new_root = self.makeDir()
        self._patchIn(new_root)
        initer = stages.Init()
        initer.datasource = FakeDataSource(user_blob, vendordata=vendor_blob)
        initer.read_cfg()
        initer.initialize()
        initer.fetch()
        initer.instancify()
        initer.update()
        initer.cloudify().run('consume_data',
                              initer.consume_data,
                              args=[PER_INSTANCE],
                              freq=PER_INSTANCE)
        mods = stages.Modules(initer)
        (_which_ran, _failures) = mods.run_section('cloud_init_modules')
        cfg = mods.cfg
        self.assertEquals('qux', cfg['baz'])
        self.assertEquals('qux2', cfg['bar'])
        self.assertNotIn('foo', cfg)

    def test_mixed_cloud_config(self):
        blob_cc = '''
#cloud-config
a: b
c: d
'''
        message_cc = MIMEBase("text", "cloud-config")
        message_cc.set_payload(blob_cc)

        blob_jp = '''
#cloud-config-jsonp
[
     { "op": "replace", "path": "/a", "value": "c" },
     { "op": "remove", "path": "/c" }
]
'''

        message_jp = MIMEBase('text', "cloud-config-jsonp")
        message_jp.set_payload(blob_jp)

        message = MIMEMultipart()
        message.attach(message_cc)
        message.attach(message_jp)

        ci = stages.Init()
        ci.datasource = FakeDataSource(str(message))
        new_root = self.makeDir()
        self.patchUtils(new_root)
        self.patchOS(new_root)
        ci.fetch()
        ci.consume_data()
        cc_contents = util.load_file(ci.paths.get_ipath("cloud_config"))
        cc = util.load_yaml(cc_contents)
        self.assertEquals(1, len(cc))
        self.assertEquals('c', cc['a'])

    def test_vendor_user_yaml_cloud_config(self):
        vendor_blob = '''
#cloud-config
a: b
name: vendor
run:
 - x
 - y
'''

        user_blob = '''
#cloud-config
a: c
vendor_data:
  enabled: True
  prefix: /bin/true
name: user
run:
 - z
'''
        new_root = self.makeDir()
        self._patchIn(new_root)
        initer = stages.Init()
        initer.datasource = FakeDataSource(user_blob, vendordata=vendor_blob)
        initer.read_cfg()
        initer.initialize()
        initer.fetch()
        initer.instancify()
        initer.update()
        initer.cloudify().run('consume_data',
                              initer.consume_data,
                              args=[PER_INSTANCE],
                              freq=PER_INSTANCE)
        mods = stages.Modules(initer)
        (_which_ran, _failures) = mods.run_section('cloud_init_modules')
        cfg = mods.cfg
        self.assertIn('vendor_data', cfg)
        self.assertEquals('c', cfg['a'])
        self.assertEquals('user', cfg['name'])
        self.assertNotIn('x', cfg['run'])
        self.assertNotIn('y', cfg['run'])
        self.assertIn('z', cfg['run'])

    def test_vendordata_script(self):
        vendor_blob = '''
#!/bin/bash
echo "test"
'''

        user_blob = '''
#cloud-config
vendor_data:
  enabled: True
  prefix: /bin/true
'''
        new_root = self.makeDir()
        self._patchIn(new_root)
        initer = stages.Init()
        initer.datasource = FakeDataSource(user_blob, vendordata=vendor_blob)
        initer.read_cfg()
        initer.initialize()
        initer.fetch()
        initer.instancify()
        initer.update()
        initer.cloudify().run('consume_data',
                              initer.consume_data,
                              args=[PER_INSTANCE],
                              freq=PER_INSTANCE)
        mods = stages.Modules(initer)
        (_which_ran, _failures) = mods.run_section('cloud_init_modules')
        vendor_script = initer.paths.get_ipath_cur('vendor_scripts')
        vendor_script_fns = "%s%s/part-001" % (new_root, vendor_script)
        self.assertTrue(os.path.exists(vendor_script_fns))

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
        ci.consume_data()
        self.assertIn(
            "Unhandled non-multipart (text/x-not-multipart) userdata:",
            log_file.getvalue())

    def test_mime_gzip_compressed(self):
        """Tests that individual message gzip encoding works."""

        def gzip_part(text):
            contents = StringIO.StringIO()
            f = gzip.GzipFile(fileobj=contents, mode='w')
            f.write(str(text))
            f.flush()
            f.close()
            return MIMEApplication(contents.getvalue(), 'gzip')

        base_content1 = '''
#cloud-config
a: 2
'''

        base_content2 = '''
#cloud-config
b: 3
c: 4
'''

        message = MIMEMultipart('test')
        message.attach(gzip_part(base_content1))
        message.attach(gzip_part(base_content2))
        ci = stages.Init()
        ci.datasource = FakeDataSource(str(message))
        new_root = self.makeDir()
        self.patchUtils(new_root)
        self.patchOS(new_root)
        ci.fetch()
        ci.consume_data()
        contents = util.load_file(ci.paths.get_ipath("cloud_config"))
        contents = util.load_yaml(contents)
        self.assertTrue(isinstance(contents, dict))
        self.assertEquals(3, len(contents))
        self.assertEquals(2, contents['a'])
        self.assertEquals(3, contents['b'])
        self.assertEquals(4, contents['c'])

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
        ci.consume_data()
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
        ci.consume_data()
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
        ci.consume_data()
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
        ci.consume_data()
        self.assertEqual("", log_file.getvalue())
