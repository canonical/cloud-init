# This file is part of cloud-init. See LICENSE file for license information.

"""Tests for handling of userdata within cloud init."""

import gzip
import logging
import os

try:
    from unittest import mock
except ImportError:
    import mock

from six import BytesIO, StringIO

from email import encoders
from email.mime.application import MIMEApplication
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart

from cloudinit import handlers
from cloudinit import helpers as c_helpers
from cloudinit import log
from cloudinit.settings import (PER_INSTANCE)
from cloudinit import sources
from cloudinit import stages
from cloudinit import user_data as ud
from cloudinit import util

from . import helpers


INSTANCE_ID = "i-testing"


class FakeDataSource(sources.DataSource):

    def __init__(self, userdata=None, vendordata=None):
        sources.DataSource.__init__(self, {}, None, None)
        self.metadata = {'instance-id': INSTANCE_ID}
        self.userdata_raw = userdata
        self.vendordata_raw = vendordata


def count_messages(root):
    am = 0
    for m in root.walk():
        if ud.is_skippable(m):
            continue
        am += 1
    return am


def gzip_text(text):
    contents = BytesIO()
    f = gzip.GzipFile(fileobj=contents, mode='wb')
    f.write(util.encode_text(text))
    f.flush()
    f.close()
    return contents.getvalue()


# FIXME: these tests shouldn't be checking log output??
# Weirddddd...
class TestConsumeUserData(helpers.FilesystemMockingTestCase):

    def setUp(self):
        super(TestConsumeUserData, self).setUp()
        self._log = None
        self._log_file = None
        self._log_handler = None

    def tearDown(self):
        if self._log_handler and self._log:
            self._log.removeHandler(self._log_handler)
        helpers.FilesystemMockingTestCase.tearDown(self)

    def _patchIn(self, root):
        self.patchOS(root)
        self.patchUtils(root)

    def capture_log(self, lvl=logging.DEBUG):
        log_file = StringIO()
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
        self.reRoot()
        ci.fetch()
        ci.consume_data()
        cc_contents = util.load_file(ci.paths.get_ipath("cloud_config"))
        cc = util.load_yaml(cc_contents)
        self.assertEqual(2, len(cc))
        self.assertEqual('qux', cc['baz'])
        self.assertEqual('qux2', cc['bar'])

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
        self.reRoot()
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
        self.assertEqual('qux', cfg['baz'])
        self.assertEqual('qux2', cfg['bar'])
        self.assertEqual('quxC', cfg['foo'])

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
        self.reRoot()
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
        self.assertEqual('qux', cfg['baz'])
        self.assertEqual('qux2', cfg['bar'])
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

        self.reRoot()
        ci = stages.Init()
        ci.datasource = FakeDataSource(str(message))
        ci.fetch()
        ci.consume_data()
        cc_contents = util.load_file(ci.paths.get_ipath("cloud_config"))
        cc = util.load_yaml(cc_contents)
        self.assertEqual(1, len(cc))
        self.assertEqual('c', cc['a'])

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
        self.reRoot()
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
        self.assertEqual('c', cfg['a'])
        self.assertEqual('user', cfg['name'])
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
        new_root = self.reRoot()
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

        self.reRoot()
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
        self.assertEqual(contents['run'], ['b', 'c', 'stuff', 'morestuff'])
        self.assertEqual(contents['a'], 'be')
        self.assertEqual(contents['e'], [1, 2, 3])
        self.assertEqual(contents['p'], 1)

    def test_unhandled_type_warning(self):
        """Raw text without magic is ignored but shows warning."""
        self.reRoot()
        ci = stages.Init()
        data = "arbitrary text\n"
        ci.datasource = FakeDataSource(data)

        with mock.patch('cloudinit.util.write_file') as mockobj:
            log_file = self.capture_log(logging.WARNING)
            ci.fetch()
            ci.consume_data()
            self.assertIn(
                "Unhandled non-multipart (text/x-not-multipart) userdata:",
                log_file.getvalue())

        mockobj.assert_called_once_with(
            ci.paths.get_ipath("cloud_config"), "", 0o600)

    def test_mime_gzip_compressed(self):
        """Tests that individual message gzip encoding works."""

        def gzip_part(text):
            return MIMEApplication(gzip_text(text), 'gzip')

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
        self.reRoot()
        ci.fetch()
        ci.consume_data()
        contents = util.load_file(ci.paths.get_ipath("cloud_config"))
        contents = util.load_yaml(contents)
        self.assertTrue(isinstance(contents, dict))
        self.assertEqual(3, len(contents))
        self.assertEqual(2, contents['a'])
        self.assertEqual(3, contents['b'])
        self.assertEqual(4, contents['c'])

    def test_mime_text_plain(self):
        """Mime message of type text/plain is ignored but shows warning."""
        self.reRoot()
        ci = stages.Init()
        message = MIMEBase("text", "plain")
        message.set_payload("Just text")
        ci.datasource = FakeDataSource(message.as_string().encode())

        with mock.patch('cloudinit.util.write_file') as mockobj:
            log_file = self.capture_log(logging.WARNING)
            ci.fetch()
            ci.consume_data()
            self.assertIn(
                "Unhandled unknown content-type (text/plain)",
                log_file.getvalue())
        mockobj.assert_called_once_with(
            ci.paths.get_ipath("cloud_config"), "", 0o600)

    def test_shellscript(self):
        """Raw text starting #!/bin/sh is treated as script."""
        self.reRoot()
        ci = stages.Init()
        script = "#!/bin/sh\necho hello\n"
        ci.datasource = FakeDataSource(script)

        outpath = os.path.join(ci.paths.get_ipath_cur("scripts"), "part-001")

        with mock.patch('cloudinit.util.write_file') as mockobj:
            log_file = self.capture_log(logging.WARNING)
            ci.fetch()
            ci.consume_data()
            self.assertEqual("", log_file.getvalue())

        mockobj.assert_has_calls([
            mock.call(outpath, script, 0o700),
            mock.call(ci.paths.get_ipath("cloud_config"), "", 0o600)])

    def test_mime_text_x_shellscript(self):
        """Mime message of type text/x-shellscript is treated as script."""
        self.reRoot()
        ci = stages.Init()
        script = "#!/bin/sh\necho hello\n"
        message = MIMEBase("text", "x-shellscript")
        message.set_payload(script)
        ci.datasource = FakeDataSource(message.as_string())

        outpath = os.path.join(ci.paths.get_ipath_cur("scripts"), "part-001")

        with mock.patch('cloudinit.util.write_file') as mockobj:
            log_file = self.capture_log(logging.WARNING)
            ci.fetch()
            ci.consume_data()
            self.assertEqual("", log_file.getvalue())

        mockobj.assert_has_calls([
            mock.call(outpath, script, 0o700),
            mock.call(ci.paths.get_ipath("cloud_config"), "", 0o600)])

    def test_mime_text_plain_shell(self):
        """Mime type text/plain starting #!/bin/sh is treated as script."""
        self.reRoot()
        ci = stages.Init()
        script = "#!/bin/sh\necho hello\n"
        message = MIMEBase("text", "plain")
        message.set_payload(script)
        ci.datasource = FakeDataSource(message.as_string())

        outpath = os.path.join(ci.paths.get_ipath_cur("scripts"), "part-001")

        with mock.patch('cloudinit.util.write_file') as mockobj:
            log_file = self.capture_log(logging.WARNING)
            ci.fetch()
            ci.consume_data()
            self.assertEqual("", log_file.getvalue())

        mockobj.assert_has_calls([
            mock.call(outpath, script, 0o700),
            mock.call(ci.paths.get_ipath("cloud_config"), "", 0o600)])

    def test_mime_application_octet_stream(self):
        """Mime type application/octet-stream is ignored but shows warning."""
        self.reRoot()
        ci = stages.Init()
        message = MIMEBase("application", "octet-stream")
        message.set_payload(b'\xbf\xe6\xb2\xc3\xd3\xba\x13\xa4\xd8\xa1\xcc')
        encoders.encode_base64(message)
        ci.datasource = FakeDataSource(message.as_string().encode())

        with mock.patch('cloudinit.util.write_file') as mockobj:
            log_file = self.capture_log(logging.WARNING)
            ci.fetch()
            ci.consume_data()
            self.assertIn(
                "Unhandled unknown content-type (application/octet-stream)",
                log_file.getvalue())
        mockobj.assert_called_once_with(
            ci.paths.get_ipath("cloud_config"), "", 0o600)

    def test_cloud_config_archive(self):
        non_decodable = b'\x11\xc9\xb4gTH\xee\x12'
        data = [{'content': '#cloud-config\npassword: gocubs\n'},
                {'content': '#cloud-config\nlocale: chicago\n'},
                {'content': non_decodable}]
        message = b'#cloud-config-archive\n' + util.yaml_dumps(data).encode()

        self.reRoot()
        ci = stages.Init()
        ci.datasource = FakeDataSource(message)

        fs = {}

        def fsstore(filename, content, mode=0o0644, omode="wb"):
            fs[filename] = content

        # consuming the user-data provided should write 'cloud_config' file
        # which will have our yaml in it.
        with mock.patch('cloudinit.util.write_file') as mockobj:
            mockobj.side_effect = fsstore
            ci.fetch()
            ci.consume_data()

        cfg = util.load_yaml(fs[ci.paths.get_ipath("cloud_config")])
        self.assertEqual(cfg.get('password'), 'gocubs')
        self.assertEqual(cfg.get('locale'), 'chicago')


class TestUDProcess(helpers.ResourceUsingTestCase):

    def test_bytes_in_userdata(self):
        msg = b'#cloud-config\napt_update: True\n'
        ud_proc = ud.UserDataProcessor(self.getCloudPaths())
        message = ud_proc.process(msg)
        self.assertTrue(count_messages(message) == 1)

    def test_string_in_userdata(self):
        msg = '#cloud-config\napt_update: True\n'

        ud_proc = ud.UserDataProcessor(self.getCloudPaths())
        message = ud_proc.process(msg)
        self.assertTrue(count_messages(message) == 1)

    def test_compressed_in_userdata(self):
        msg = gzip_text('#cloud-config\napt_update: True\n')

        ud_proc = ud.UserDataProcessor(self.getCloudPaths())
        message = ud_proc.process(msg)
        self.assertTrue(count_messages(message) == 1)


class TestConvertString(helpers.TestCase):
    def test_handles_binary_non_utf8_decodable(self):
        blob = b'\x32\x99'
        msg = ud.convert_string(blob)
        self.assertEqual(blob, msg.get_payload(decode=True))

    def test_handles_binary_utf8_decodable(self):
        blob = b'\x32\x32'
        msg = ud.convert_string(blob)
        self.assertEqual(blob, msg.get_payload(decode=True))

    def test_handle_headers(self):
        text = "hi mom"
        msg = ud.convert_string(text)
        self.assertEqual(text, msg.get_payload(decode=False))


class TestFetchBaseConfig(helpers.TestCase):

    def test_only_builtin_gets_builtin2(self):
        ret = helpers.wrap_and_call(
            'cloudinit.stages.util',
            {'read_conf_with_confd': None,
             'read_conf_from_cmdline': None},
            stages.fetch_base_config)
        self.assertEqual(util.get_builtin_cfg(), ret)

    def test_conf_d_overrides_defaults(self):
        builtin = util.get_builtin_cfg()
        test_key = sorted(builtin)[0]
        test_value = 'test'
        ret = helpers.wrap_and_call(
            'cloudinit.stages.util',
            {'read_conf_with_confd': {'return_value': {test_key: test_value}},
             'read_conf_from_cmdline': None},
            stages.fetch_base_config)
        self.assertEqual(ret.get(test_key), test_value)
        builtin[test_key] = test_value
        self.assertEqual(ret, builtin)

    def test_cmdline_overrides_defaults(self):
        builtin = util.get_builtin_cfg()
        test_key = sorted(builtin)[0]
        test_value = 'test'
        cmdline = {test_key: test_value}
        ret = helpers.wrap_and_call(
            'cloudinit.stages.util',
            {'read_conf_from_cmdline': {'return_value': cmdline},
             'read_conf_with_confd': None},
            stages.fetch_base_config)
        self.assertEqual(ret.get(test_key), test_value)
        builtin[test_key] = test_value
        self.assertEqual(ret, builtin)

    def test_cmdline_overrides_conf_d_and_defaults(self):
        builtin = {'key1': 'value0', 'key3': 'other2'}
        conf_d = {'key1': 'value1', 'key2': 'other1'}
        cmdline = {'key3': 'other3', 'key2': 'other2'}
        ret = helpers.wrap_and_call(
            'cloudinit.stages.util',
            {'read_conf_with_confd': {'return_value': conf_d},
             'get_builtin_cfg': {'return_value': builtin},
             'read_conf_from_cmdline': {'return_value': cmdline}},
            stages.fetch_base_config)
        self.assertEqual(ret, {'key1': 'value1', 'key2': 'other2',
                               'key3': 'other3'})

# vi: ts=4 expandtab
