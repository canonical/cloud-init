# This file is part of cloud-init. See LICENSE file for license information.

"""Tests of the built-in user data handlers."""

import copy
import errno
import os
import shutil
import tempfile
from textwrap import dedent


from cloudinit.tests.helpers import (
    FilesystemMockingTestCase, CiTestCase, mock, skipUnlessJinja)

from cloudinit import handlers
from cloudinit import helpers
from cloudinit import util

from cloudinit.handlers.cloud_config import CloudConfigPartHandler
from cloudinit.handlers.jinja_template import (
    JinjaTemplatePartHandler, convert_jinja_instance_data,
    render_jinja_payload)
from cloudinit.handlers.shell_script import ShellScriptPartHandler
from cloudinit.handlers.upstart_job import UpstartJobPartHandler

from cloudinit.settings import (PER_ALWAYS, PER_INSTANCE)


class TestUpstartJobPartHandler(FilesystemMockingTestCase):

    mpath = 'cloudinit.handlers.upstart_job.'

    def test_upstart_frequency_no_out(self):
        c_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, c_root)
        up_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, up_root)
        paths = helpers.Paths({
            'cloud_dir': c_root,
            'upstart_dir': up_root,
        })
        h = UpstartJobPartHandler(paths)
        # No files should be written out when
        # the frequency is ! per-instance
        h.handle_part('', handlers.CONTENT_START,
                      None, None, None)
        h.handle_part('blah', 'text/upstart-job',
                      'test.conf', 'blah', frequency=PER_ALWAYS)
        h.handle_part('', handlers.CONTENT_END,
                      None, None, None)
        self.assertEqual(0, len(os.listdir(up_root)))

    def test_upstart_frequency_single(self):
        # files should be written out when frequency is ! per-instance
        new_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, new_root)

        self.patchOS(new_root)
        self.patchUtils(new_root)
        paths = helpers.Paths({
            'upstart_dir': "/etc/upstart",
        })

        util.ensure_dir("/run")
        util.ensure_dir("/etc/upstart")

        with mock.patch(self.mpath + 'SUITABLE_UPSTART', return_value=True):
            with mock.patch.object(util, 'subp') as m_subp:
                h = UpstartJobPartHandler(paths)
                h.handle_part('', handlers.CONTENT_START,
                              None, None, None)
                h.handle_part('blah', 'text/upstart-job',
                              'test.conf', 'blah', frequency=PER_INSTANCE)
                h.handle_part('', handlers.CONTENT_END,
                              None, None, None)

        self.assertEqual(len(os.listdir('/etc/upstart')), 1)

        m_subp.assert_called_once_with(
            ['initctl', 'reload-configuration'], capture=False)


class TestJinjaTemplatePartHandler(CiTestCase):

    with_logs = True

    mpath = 'cloudinit.handlers.jinja_template.'

    def setUp(self):
        super(TestJinjaTemplatePartHandler, self).setUp()
        self.tmp = self.tmp_dir()
        self.run_dir = os.path.join(self.tmp, 'run_dir')
        util.ensure_dir(self.run_dir)
        self.paths = helpers.Paths({
            'cloud_dir': self.tmp, 'run_dir': self.run_dir})

    def test_jinja_template_part_handler_defaults(self):
        """On init, paths are saved and subhandler types are empty."""
        h = JinjaTemplatePartHandler(self.paths)
        self.assertEqual(['## template: jinja'], h.prefixes)
        self.assertEqual(3, h.handler_version)
        self.assertEqual(self.paths, h.paths)
        self.assertEqual({}, h.sub_handlers)

    def test_jinja_template_part_handler_looks_up_sub_handler_types(self):
        """When sub_handlers are passed, init lists types of subhandlers."""
        script_handler = ShellScriptPartHandler(self.paths)
        cloudconfig_handler = CloudConfigPartHandler(self.paths)
        h = JinjaTemplatePartHandler(
            self.paths, sub_handlers=[script_handler, cloudconfig_handler])
        self.assertItemsEqual(
            ['text/cloud-config', 'text/cloud-config-jsonp',
             'text/x-shellscript'],
            h.sub_handlers)

    def test_jinja_template_part_handler_looks_up_subhandler_types(self):
        """When sub_handlers are passed, init lists types of subhandlers."""
        script_handler = ShellScriptPartHandler(self.paths)
        cloudconfig_handler = CloudConfigPartHandler(self.paths)
        h = JinjaTemplatePartHandler(
            self.paths, sub_handlers=[script_handler, cloudconfig_handler])
        self.assertItemsEqual(
            ['text/cloud-config', 'text/cloud-config-jsonp',
             'text/x-shellscript'],
            h.sub_handlers)

    def test_jinja_template_handle_noop_on_content_signals(self):
        """Perform no part handling when content type is CONTENT_SIGNALS."""
        script_handler = ShellScriptPartHandler(self.paths)

        h = JinjaTemplatePartHandler(
            self.paths, sub_handlers=[script_handler])
        with mock.patch.object(script_handler, 'handle_part') as m_handle_part:
            h.handle_part(
                data='data', ctype=handlers.CONTENT_START, filename='part-1',
                payload='## template: jinja\n#!/bin/bash\necho himom',
                frequency='freq', headers='headers')
        m_handle_part.assert_not_called()

    @skipUnlessJinja()
    def test_jinja_template_handle_subhandler_v2_with_clean_payload(self):
        """Call version 2 subhandler.handle_part with stripped payload."""
        script_handler = ShellScriptPartHandler(self.paths)
        self.assertEqual(2, script_handler.handler_version)

        # Create required instance-data.json file
        instance_json = os.path.join(self.run_dir, 'instance-data.json')
        instance_data = {'topkey': 'echo himom'}
        util.write_file(instance_json, util.json_dumps(instance_data))
        h = JinjaTemplatePartHandler(
            self.paths, sub_handlers=[script_handler])
        with mock.patch.object(script_handler, 'handle_part') as m_part:
            # ctype with leading '!' not in handlers.CONTENT_SIGNALS
            h.handle_part(
                data='data', ctype="!" + handlers.CONTENT_START,
                filename='part01',
                payload='## template: jinja   \t \n#!/bin/bash\n{{ topkey }}',
                frequency='freq', headers='headers')
        m_part.assert_called_once_with(
            'data', '!__begin__', 'part01', '#!/bin/bash\necho himom', 'freq')

    @skipUnlessJinja()
    def test_jinja_template_handle_subhandler_v3_with_clean_payload(self):
        """Call version 3 subhandler.handle_part with stripped payload."""
        cloudcfg_handler = CloudConfigPartHandler(self.paths)
        self.assertEqual(3, cloudcfg_handler.handler_version)

        # Create required instance-data.json file
        instance_json = os.path.join(self.run_dir, 'instance-data.json')
        instance_data = {'topkey': {'sub': 'runcmd: [echo hi]'}}
        util.write_file(instance_json, util.json_dumps(instance_data))
        h = JinjaTemplatePartHandler(
            self.paths, sub_handlers=[cloudcfg_handler])
        with mock.patch.object(cloudcfg_handler, 'handle_part') as m_part:
            # ctype with leading '!' not in handlers.CONTENT_SIGNALS
            h.handle_part(
                data='data', ctype="!" + handlers.CONTENT_END,
                filename='part01',
                payload='## template: jinja\n#cloud-config\n{{ topkey.sub }}',
                frequency='freq', headers='headers')
        m_part.assert_called_once_with(
            'data', '!__end__', 'part01', '#cloud-config\nruncmd: [echo hi]',
            'freq', 'headers')

    def test_jinja_template_handle_errors_on_missing_instance_data_json(self):
        """If instance-data is absent, raise an error from handle_part."""
        script_handler = ShellScriptPartHandler(self.paths)
        h = JinjaTemplatePartHandler(
            self.paths, sub_handlers=[script_handler])
        with self.assertRaises(RuntimeError) as context_manager:
            h.handle_part(
                data='data', ctype="!" + handlers.CONTENT_START,
                filename='part01',
                payload='## template: jinja  \n#!/bin/bash\necho himom',
                frequency='freq', headers='headers')
        script_file = os.path.join(script_handler.script_dir, 'part01')
        self.assertEqual(
            'Cannot render jinja template vars. Instance data not yet present'
            ' at {}/instance-data.json'.format(
                self.run_dir), str(context_manager.exception))
        self.assertFalse(
            os.path.exists(script_file),
            'Unexpected file created %s' % script_file)

    def test_jinja_template_handle_errors_on_unreadable_instance_data(self):
        """If instance-data is unreadable, raise an error from handle_part."""
        script_handler = ShellScriptPartHandler(self.paths)
        instance_json = os.path.join(self.run_dir, 'instance-data.json')
        util.write_file(instance_json, util.json_dumps({}))
        h = JinjaTemplatePartHandler(
            self.paths, sub_handlers=[script_handler])
        with mock.patch(self.mpath + 'load_file') as m_load:
            with self.assertRaises(RuntimeError) as context_manager:
                m_load.side_effect = OSError(errno.EACCES, 'Not allowed')
                h.handle_part(
                    data='data', ctype="!" + handlers.CONTENT_START,
                    filename='part01',
                    payload='## template: jinja  \n#!/bin/bash\necho himom',
                    frequency='freq', headers='headers')
        script_file = os.path.join(script_handler.script_dir, 'part01')
        self.assertEqual(
            'Cannot render jinja template vars. No read permission on'
            " '{rdir}/instance-data.json'. Try sudo".format(rdir=self.run_dir),
            str(context_manager.exception))
        self.assertFalse(
            os.path.exists(script_file),
            'Unexpected file created %s' % script_file)

    @skipUnlessJinja()
    def test_jinja_template_handle_renders_jinja_content(self):
        """When present, render jinja variables from instance-data.json."""
        script_handler = ShellScriptPartHandler(self.paths)
        instance_json = os.path.join(self.run_dir, 'instance-data.json')
        instance_data = {'topkey': {'subkey': 'echo himom'}}
        util.write_file(instance_json, util.json_dumps(instance_data))
        h = JinjaTemplatePartHandler(
            self.paths, sub_handlers=[script_handler])
        h.handle_part(
            data='data', ctype="!" + handlers.CONTENT_START,
            filename='part01',
            payload=(
                '## template: jinja  \n'
                '#!/bin/bash\n'
                '{{ topkey.subkey|default("nosubkey") }}'),
            frequency='freq', headers='headers')
        script_file = os.path.join(script_handler.script_dir, 'part01')
        self.assertNotIn(
            'Instance data not yet present at {}/instance-data.json'.format(
                self.run_dir),
            self.logs.getvalue())
        self.assertEqual(
            '#!/bin/bash\necho himom', util.load_file(script_file))

    @skipUnlessJinja()
    def test_jinja_template_handle_renders_jinja_content_missing_keys(self):
        """When specified jinja variable is undefined, log a warning."""
        script_handler = ShellScriptPartHandler(self.paths)
        instance_json = os.path.join(self.run_dir, 'instance-data.json')
        instance_data = {'topkey': {'subkey': 'echo himom'}}
        util.write_file(instance_json, util.json_dumps(instance_data))
        h = JinjaTemplatePartHandler(
            self.paths, sub_handlers=[script_handler])
        h.handle_part(
            data='data', ctype="!" + handlers.CONTENT_START,
            filename='part01',
            payload='## template: jinja  \n#!/bin/bash\n{{ goodtry }}',
            frequency='freq', headers='headers')
        script_file = os.path.join(script_handler.script_dir, 'part01')
        self.assertTrue(
            os.path.exists(script_file),
            'Missing expected file %s' % script_file)
        self.assertIn(
            "WARNING: Could not render jinja template variables in file"
            " 'part01': 'goodtry'\n",
            self.logs.getvalue())


class TestConvertJinjaInstanceData(CiTestCase):

    def test_convert_instance_data_hyphens_to_underscores(self):
        """Replace hyphenated keys with underscores in instance-data."""
        data = {'hyphenated-key': 'hyphenated-val',
                'underscore_delim_key': 'underscore_delimited_val'}
        expected_data = {'hyphenated_key': 'hyphenated-val',
                         'underscore_delim_key': 'underscore_delimited_val'}
        self.assertEqual(
            expected_data,
            convert_jinja_instance_data(data=data))

    def test_convert_instance_data_promotes_versioned_keys_to_top_level(self):
        """Any versioned keys are promoted as top-level keys

        This provides any cloud-init standardized keys up at a top-level to
        allow ease of reference for users. Intsead of v1.availability_zone,
        the name availability_zone can be used in templates.
        """
        data = {'ds': {'dskey1': 1, 'dskey2': 2},
                'v1': {'v1key1': 'v1.1'},
                'v2': {'v2key1': 'v2.1'}}
        expected_data = copy.deepcopy(data)
        expected_data.update({'v1key1': 'v1.1', 'v2key1': 'v2.1'})

        converted_data = convert_jinja_instance_data(data=data)
        self.assertItemsEqual(
            ['ds', 'v1', 'v2', 'v1key1', 'v2key1'], converted_data.keys())
        self.assertEqual(
            expected_data,
            converted_data)

    def test_convert_instance_data_most_recent_version_of_promoted_keys(self):
        """The most-recent versioned key value is promoted to top-level."""
        data = {'v1': {'key1': 'old v1 key1', 'key2': 'old v1 key2'},
                'v2': {'key1': 'newer v2 key1', 'key3': 'newer v2 key3'},
                'v3': {'key1': 'newest v3 key1'}}
        expected_data = copy.deepcopy(data)
        expected_data.update(
            {'key1': 'newest v3 key1', 'key2': 'old v1 key2',
             'key3': 'newer v2 key3'})

        converted_data = convert_jinja_instance_data(data=data)
        self.assertEqual(
            expected_data,
            converted_data)

    def test_convert_instance_data_decodes_decode_paths(self):
        """Any decode_paths provided are decoded by convert_instance_data."""
        data = {'key1': {'subkey1': 'aGkgbW9t'}, 'key2': 'aGkgZGFk'}
        expected_data = copy.deepcopy(data)
        expected_data['key1']['subkey1'] = 'hi mom'

        converted_data = convert_jinja_instance_data(
            data=data, decode_paths=('key1/subkey1',))
        self.assertEqual(
            expected_data,
            converted_data)


class TestRenderJinjaPayload(CiTestCase):

    with_logs = True

    @skipUnlessJinja()
    def test_render_jinja_payload_logs_jinja_vars_on_debug(self):
        """When debug is True, log jinja varables available."""
        payload = (
            '## template: jinja\n#!/bin/sh\necho hi from {{ v1.hostname }}')
        instance_data = {'v1': {'hostname': 'foo'}, 'instance-id': 'iid'}
        expected_log = dedent("""\
            DEBUG: Converted jinja variables
            {
             "hostname": "foo",
             "instance_id": "iid",
             "v1": {
              "hostname": "foo"
             }
            }
            """)
        self.assertEqual(
            render_jinja_payload(
                payload=payload, payload_fn='myfile',
                instance_data=instance_data, debug=True),
            '#!/bin/sh\necho hi from foo')
        self.assertEqual(expected_log, self.logs.getvalue())

    @skipUnlessJinja()
    def test_render_jinja_payload_replaces_missing_variables_and_warns(self):
        """Warn on missing jinja variables and replace the absent variable."""
        payload = (
            '## template: jinja\n#!/bin/sh\necho hi from {{ NOTHERE }}')
        instance_data = {'v1': {'hostname': 'foo'}, 'instance-id': 'iid'}
        self.assertEqual(
            render_jinja_payload(
                payload=payload, payload_fn='myfile',
                instance_data=instance_data),
            '#!/bin/sh\necho hi from CI_MISSING_JINJA_VAR/NOTHERE')
        expected_log = (
            'WARNING: Could not render jinja template variables in file'
            " 'myfile': 'NOTHERE'")
        self.assertIn(expected_log, self.logs.getvalue())

# vi: ts=4 expandtab
