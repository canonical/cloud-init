# This file is part of cloud-init. See LICENSE file for license information.

import re
from six import StringIO

from cloudinit.config.cc_ubuntu_advantage import (
    handle, maybe_install_ua_tools, run_commands, schema)
from cloudinit.config.schema import validate_cloudconfig_schema
from cloudinit import util
from cloudinit.tests.helpers import (
    CiTestCase, mock, SchemaTestCaseMixin, skipUnlessJsonSchema)


# Module path used in mocks
MPATH = 'cloudinit.config.cc_ubuntu_advantage'


class FakeCloud(object):
    def __init__(self, distro):
        self.distro = distro


class TestRunCommands(CiTestCase):

    with_logs = True
    allowed_subp = [CiTestCase.SUBP_SHELL_TRUE]

    def setUp(self):
        super(TestRunCommands, self).setUp()
        self.tmp = self.tmp_dir()

    @mock.patch('%s.util.subp' % MPATH)
    def test_run_commands_on_empty_list(self, m_subp):
        """When provided with an empty list, run_commands does nothing."""
        run_commands([])
        self.assertEqual('', self.logs.getvalue())
        m_subp.assert_not_called()

    def test_run_commands_on_non_list_or_dict(self):
        """When provided an invalid type, run_commands raises an error."""
        with self.assertRaises(TypeError) as context_manager:
            run_commands(commands="I'm Not Valid")
        self.assertEqual(
            "commands parameter was not a list or dict: I'm Not Valid",
            str(context_manager.exception))

    def test_run_command_logs_commands_and_exit_codes_to_stderr(self):
        """All exit codes are logged to stderr."""
        outfile = self.tmp_path('output.log', dir=self.tmp)

        cmd1 = 'echo "HI" >> %s' % outfile
        cmd2 = 'bogus command'
        cmd3 = 'echo "MOM" >> %s' % outfile
        commands = [cmd1, cmd2, cmd3]

        mock_path = '%s.sys.stderr' % MPATH
        with mock.patch(mock_path, new_callable=StringIO) as m_stderr:
            with self.assertRaises(RuntimeError) as context_manager:
                run_commands(commands=commands)

        self.assertIsNotNone(
            re.search(r'bogus: (command )?not found',
                      str(context_manager.exception)),
            msg='Expected bogus command not found')
        expected_stderr_log = '\n'.join([
            'Begin run command: {cmd}'.format(cmd=cmd1),
            'End run command: exit(0)',
            'Begin run command: {cmd}'.format(cmd=cmd2),
            'ERROR: End run command: exit(127)',
            'Begin run command: {cmd}'.format(cmd=cmd3),
            'End run command: exit(0)\n'])
        self.assertEqual(expected_stderr_log, m_stderr.getvalue())

    def test_run_command_as_lists(self):
        """When commands are specified as a list, run them in order."""
        outfile = self.tmp_path('output.log', dir=self.tmp)

        cmd1 = 'echo "HI" >> %s' % outfile
        cmd2 = 'echo "MOM" >> %s' % outfile
        commands = [cmd1, cmd2]
        with mock.patch('%s.sys.stderr' % MPATH, new_callable=StringIO):
            run_commands(commands=commands)

        self.assertIn(
            'DEBUG: Running user-provided ubuntu-advantage commands',
            self.logs.getvalue())
        self.assertEqual('HI\nMOM\n', util.load_file(outfile))
        self.assertIn(
            'WARNING: Non-ubuntu-advantage commands in ubuntu-advantage'
            ' config:',
            self.logs.getvalue())

    def test_run_command_dict_sorted_as_command_script(self):
        """When commands are a dict, sort them and run."""
        outfile = self.tmp_path('output.log', dir=self.tmp)
        cmd1 = 'echo "HI" >> %s' % outfile
        cmd2 = 'echo "MOM" >> %s' % outfile
        commands = {'02': cmd1, '01': cmd2}
        with mock.patch('%s.sys.stderr' % MPATH, new_callable=StringIO):
            run_commands(commands=commands)

        expected_messages = [
            'DEBUG: Running user-provided ubuntu-advantage commands']
        for message in expected_messages:
            self.assertIn(message, self.logs.getvalue())
        self.assertEqual('MOM\nHI\n', util.load_file(outfile))


@skipUnlessJsonSchema()
class TestSchema(CiTestCase, SchemaTestCaseMixin):

    with_logs = True
    schema = schema

    def test_schema_warns_on_ubuntu_advantage_not_as_dict(self):
        """If ubuntu-advantage configuration is not a dict, emit a warning."""
        validate_cloudconfig_schema({'ubuntu-advantage': 'wrong type'}, schema)
        self.assertEqual(
            "WARNING: Invalid config:\nubuntu-advantage: 'wrong type' is not"
            " of type 'object'\n",
            self.logs.getvalue())

    @mock.patch('%s.run_commands' % MPATH)
    def test_schema_disallows_unknown_keys(self, _):
        """Unknown keys in ubuntu-advantage configuration emit warnings."""
        validate_cloudconfig_schema(
            {'ubuntu-advantage': {'commands': ['ls'], 'invalid-key': ''}},
            schema)
        self.assertIn(
            'WARNING: Invalid config:\nubuntu-advantage: Additional properties'
            " are not allowed ('invalid-key' was unexpected)",
            self.logs.getvalue())

    def test_warn_schema_requires_commands(self):
        """Warn when ubuntu-advantage configuration lacks commands."""
        validate_cloudconfig_schema(
            {'ubuntu-advantage': {}}, schema)
        self.assertEqual(
            "WARNING: Invalid config:\nubuntu-advantage: 'commands' is a"
            " required property\n",
            self.logs.getvalue())

    @mock.patch('%s.run_commands' % MPATH)
    def test_warn_schema_commands_is_not_list_or_dict(self, _):
        """Warn when ubuntu-advantage:commands config is not a list or dict."""
        validate_cloudconfig_schema(
            {'ubuntu-advantage': {'commands': 'broken'}}, schema)
        self.assertEqual(
            "WARNING: Invalid config:\nubuntu-advantage.commands: 'broken' is"
            " not of type 'object', 'array'\n",
            self.logs.getvalue())

    @mock.patch('%s.run_commands' % MPATH)
    def test_warn_schema_when_commands_is_empty(self, _):
        """Emit warnings when ubuntu-advantage:commands is empty."""
        validate_cloudconfig_schema(
            {'ubuntu-advantage': {'commands': []}}, schema)
        validate_cloudconfig_schema(
            {'ubuntu-advantage': {'commands': {}}}, schema)
        self.assertEqual(
            "WARNING: Invalid config:\nubuntu-advantage.commands: [] is too"
            " short\nWARNING: Invalid config:\nubuntu-advantage.commands: {}"
            " does not have enough properties\n",
            self.logs.getvalue())

    @mock.patch('%s.run_commands' % MPATH)
    def test_schema_when_commands_are_list_or_dict(self, _):
        """No warnings when ubuntu-advantage:commands are a list or dict."""
        validate_cloudconfig_schema(
            {'ubuntu-advantage': {'commands': ['valid']}}, schema)
        validate_cloudconfig_schema(
            {'ubuntu-advantage': {'commands': {'01': 'also valid'}}}, schema)
        self.assertEqual('', self.logs.getvalue())

    def test_duplicates_are_fine_array_array(self):
        """Duplicated commands array/array entries are allowed."""
        self.assertSchemaValid(
            {'commands': [["echo", "bye"], ["echo" "bye"]]},
            "command entries can be duplicate.")

    def test_duplicates_are_fine_array_string(self):
        """Duplicated commands array/string entries are allowed."""
        self.assertSchemaValid(
            {'commands': ["echo bye", "echo bye"]},
            "command entries can be duplicate.")

    def test_duplicates_are_fine_dict_array(self):
        """Duplicated commands dict/array entries are allowed."""
        self.assertSchemaValid(
            {'commands': {'00': ["echo", "bye"], '01': ["echo", "bye"]}},
            "command entries can be duplicate.")

    def test_duplicates_are_fine_dict_string(self):
        """Duplicated commands dict/string entries are allowed."""
        self.assertSchemaValid(
            {'commands': {'00': "echo bye", '01': "echo bye"}},
            "command entries can be duplicate.")


class TestHandle(CiTestCase):

    with_logs = True

    def setUp(self):
        super(TestHandle, self).setUp()
        self.tmp = self.tmp_dir()

    @mock.patch('%s.run_commands' % MPATH)
    @mock.patch('%s.validate_cloudconfig_schema' % MPATH)
    def test_handle_no_config(self, m_schema, m_run):
        """When no ua-related configuration is provided, nothing happens."""
        cfg = {}
        handle('ua-test', cfg=cfg, cloud=None, log=self.logger, args=None)
        self.assertIn(
            "DEBUG: Skipping module named ua-test, no 'ubuntu-advantage' key"
            " in config",
            self.logs.getvalue())
        m_schema.assert_not_called()
        m_run.assert_not_called()

    @mock.patch('%s.maybe_install_ua_tools' % MPATH)
    def test_handle_tries_to_install_ubuntu_advantage_tools(self, m_install):
        """If ubuntu_advantage is provided, try installing ua-tools package."""
        cfg = {'ubuntu-advantage': {}}
        mycloud = FakeCloud(None)
        handle('nomatter', cfg=cfg, cloud=mycloud, log=self.logger, args=None)
        m_install.assert_called_once_with(mycloud)

    @mock.patch('%s.maybe_install_ua_tools' % MPATH)
    def test_handle_runs_commands_provided(self, m_install):
        """When commands are specified as a list, run them."""
        outfile = self.tmp_path('output.log', dir=self.tmp)

        cfg = {
            'ubuntu-advantage': {'commands': ['echo "HI" >> %s' % outfile,
                                              'echo "MOM" >> %s' % outfile]}}
        mock_path = '%s.sys.stderr' % MPATH
        with self.allow_subp([CiTestCase.SUBP_SHELL_TRUE]):
            with mock.patch(mock_path, new_callable=StringIO):
                handle('nomatter', cfg=cfg, cloud=None, log=self.logger,
                       args=None)
        self.assertEqual('HI\nMOM\n', util.load_file(outfile))


class TestMaybeInstallUATools(CiTestCase):

    with_logs = True

    def setUp(self):
        super(TestMaybeInstallUATools, self).setUp()
        self.tmp = self.tmp_dir()

    @mock.patch('%s.util.which' % MPATH)
    def test_maybe_install_ua_tools_noop_when_ua_tools_present(self, m_which):
        """Do nothing if ubuntu-advantage-tools already exists."""
        m_which.return_value = '/usr/bin/ubuntu-advantage'  # already installed
        distro = mock.MagicMock()
        distro.update_package_sources.side_effect = RuntimeError(
            'Some apt error')
        maybe_install_ua_tools(cloud=FakeCloud(distro))  # No RuntimeError

    @mock.patch('%s.util.which' % MPATH)
    def test_maybe_install_ua_tools_raises_update_errors(self, m_which):
        """maybe_install_ua_tools logs and raises apt update errors."""
        m_which.return_value = None
        distro = mock.MagicMock()
        distro.update_package_sources.side_effect = RuntimeError(
            'Some apt error')
        with self.assertRaises(RuntimeError) as context_manager:
            maybe_install_ua_tools(cloud=FakeCloud(distro))
        self.assertEqual('Some apt error', str(context_manager.exception))
        self.assertIn('Package update failed\nTraceback', self.logs.getvalue())

    @mock.patch('%s.util.which' % MPATH)
    def test_maybe_install_ua_raises_install_errors(self, m_which):
        """maybe_install_ua_tools logs and raises package install errors."""
        m_which.return_value = None
        distro = mock.MagicMock()
        distro.update_package_sources.return_value = None
        distro.install_packages.side_effect = RuntimeError(
            'Some install error')
        with self.assertRaises(RuntimeError) as context_manager:
            maybe_install_ua_tools(cloud=FakeCloud(distro))
        self.assertEqual('Some install error', str(context_manager.exception))
        self.assertIn(
            'Failed to install ubuntu-advantage-tools\n', self.logs.getvalue())

    @mock.patch('%s.util.which' % MPATH)
    def test_maybe_install_ua_tools_happy_path(self, m_which):
        """maybe_install_ua_tools installs ubuntu-advantage-tools."""
        m_which.return_value = None
        distro = mock.MagicMock()  # No errors raised
        maybe_install_ua_tools(cloud=FakeCloud(distro))
        distro.update_package_sources.assert_called_once_with()
        distro.install_packages.assert_called_once_with(
            ['ubuntu-advantage-tools'])

# vi: ts=4 expandtab
