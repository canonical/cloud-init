# This file is part of cloud-init. See LICENSE file for license information.

from collections import namedtuple
import os
import six

from cloudinit.cmd import main as cli
from cloudinit.tests import helpers as test_helpers
from cloudinit.util import load_file, load_json


mock = test_helpers.mock


class TestCLI(test_helpers.FilesystemMockingTestCase):

    with_logs = True

    def setUp(self):
        super(TestCLI, self).setUp()
        self.stderr = six.StringIO()
        self.patchStdoutAndStderr(stderr=self.stderr)

    def _call_main(self, sysv_args=None):
        if not sysv_args:
            sysv_args = ['cloud-init']
        try:
            return cli.main(sysv_args=sysv_args)
        except SystemExit as e:
            return e.code

    def test_status_wrapper_errors_on_invalid_name(self):
        """status_wrapper will error when the name parameter is not valid.

        Valid name values are only init and modules.
        """
        tmpd = self.tmp_dir()
        data_d = self.tmp_path('data', tmpd)
        link_d = self.tmp_path('link', tmpd)
        FakeArgs = namedtuple('FakeArgs', ['action', 'local', 'mode'])

        def myaction():
            raise Exception('Should not call myaction')

        myargs = FakeArgs(('doesnotmatter', myaction), False, 'bogusmode')
        with self.assertRaises(ValueError) as cm:
            cli.status_wrapper('init1', myargs, data_d, link_d)
        self.assertEqual('unknown name: init1', str(cm.exception))
        self.assertNotIn('Should not call myaction', self.logs.getvalue())

    def test_status_wrapper_errors_on_invalid_modes(self):
        """status_wrapper will error if a parameter combination is invalid."""
        tmpd = self.tmp_dir()
        data_d = self.tmp_path('data', tmpd)
        link_d = self.tmp_path('link', tmpd)
        FakeArgs = namedtuple('FakeArgs', ['action', 'local', 'mode'])

        def myaction():
            raise Exception('Should not call myaction')

        myargs = FakeArgs(('modules_name', myaction), False, 'bogusmode')
        with self.assertRaises(ValueError) as cm:
            cli.status_wrapper('modules', myargs, data_d, link_d)
        self.assertEqual(
            "Invalid cloud init mode specified 'modules-bogusmode'",
            str(cm.exception))
        self.assertNotIn('Should not call myaction', self.logs.getvalue())

    def test_status_wrapper_init_local_writes_fresh_status_info(self):
        """When running in init-local mode, status_wrapper writes status.json.

        Old status and results artifacts are also removed.
        """
        tmpd = self.tmp_dir()
        data_d = self.tmp_path('data', tmpd)
        link_d = self.tmp_path('link', tmpd)
        status_link = self.tmp_path('status.json', link_d)
        # Write old artifacts which will be removed or updated.
        for _dir in data_d, link_d:
            test_helpers.populate_dir(
                _dir, {'status.json': 'old', 'result.json': 'old'})

        FakeArgs = namedtuple('FakeArgs', ['action', 'local', 'mode'])

        def myaction(name, args):
            # Return an error to watch status capture them
            return 'SomeDatasource', ['an error']

        myargs = FakeArgs(('ignored_name', myaction), True, 'bogusmode')
        cli.status_wrapper('init', myargs, data_d, link_d)
        # No errors reported in status
        status_v1 = load_json(load_file(status_link))['v1']
        self.assertEqual(['an error'], status_v1['init-local']['errors'])
        self.assertEqual('SomeDatasource', status_v1['datasource'])
        self.assertFalse(
            os.path.exists(self.tmp_path('result.json', data_d)),
            'unexpected result.json found')
        self.assertFalse(
            os.path.exists(self.tmp_path('result.json', link_d)),
            'unexpected result.json link found')

    def test_no_arguments_shows_usage(self):
        exit_code = self._call_main()
        self.assertIn('usage: cloud-init', self.stderr.getvalue())
        self.assertEqual(2, exit_code)

    def test_no_arguments_shows_error_message(self):
        exit_code = self._call_main()
        missing_subcommand_message = [
            'too few arguments',  # python2.7 msg
            'the following arguments are required: subcommand'  # python3 msg
        ]
        error = self.stderr.getvalue()
        matches = ([msg in error for msg in missing_subcommand_message])
        self.assertTrue(
            any(matches), 'Did not find error message for missing subcommand')
        self.assertEqual(2, exit_code)

    def test_all_subcommands_represented_in_help(self):
        """All known subparsers are represented in the cloud-int help doc."""
        self._call_main()
        error = self.stderr.getvalue()
        expected_subcommands = ['analyze', 'clean', 'devel', 'dhclient-hook',
                                'features', 'init', 'modules', 'single']
        for subcommand in expected_subcommands:
            self.assertIn(subcommand, error)

    @mock.patch('cloudinit.cmd.main.status_wrapper')
    def test_init_subcommand_parser(self, m_status_wrapper):
        """The subcommand 'init' calls status_wrapper passing init."""
        self._call_main(['cloud-init', 'init'])
        (name, parseargs) = m_status_wrapper.call_args_list[0][0]
        self.assertEqual('init', name)
        self.assertEqual('init', parseargs.subcommand)
        self.assertEqual('init', parseargs.action[0])
        self.assertEqual('main_init', parseargs.action[1].__name__)

    @mock.patch('cloudinit.cmd.main.status_wrapper')
    def test_modules_subcommand_parser(self, m_status_wrapper):
        """The subcommand 'modules' calls status_wrapper passing modules."""
        self._call_main(['cloud-init', 'modules'])
        (name, parseargs) = m_status_wrapper.call_args_list[0][0]
        self.assertEqual('modules', name)
        self.assertEqual('modules', parseargs.subcommand)
        self.assertEqual('modules', parseargs.action[0])
        self.assertEqual('main_modules', parseargs.action[1].__name__)

    def test_conditional_subcommands_from_entry_point_sys_argv(self):
        """Subcommands from entry-point are properly parsed from sys.argv."""
        stdout = six.StringIO()
        self.patchStdoutAndStderr(stdout=stdout)

        expected_errors = [
            'usage: cloud-init analyze', 'usage: cloud-init clean',
            'usage: cloud-init collect-logs', 'usage: cloud-init devel',
            'usage: cloud-init status']
        conditional_subcommands = [
            'analyze', 'clean', 'collect-logs', 'devel', 'status']
        # The cloud-init entrypoint calls main without passing sys_argv
        for subcommand in conditional_subcommands:
            with mock.patch('sys.argv', ['cloud-init', subcommand, '-h']):
                try:
                    cli.main()
                except SystemExit as e:
                    self.assertEqual(0, e.code)  # exit 2 on proper -h usage
        for error_message in expected_errors:
            self.assertIn(error_message, stdout.getvalue())

    def test_analyze_subcommand_parser(self):
        """The subcommand cloud-init analyze calls the correct subparser."""
        self._call_main(['cloud-init', 'analyze'])
        # These subcommands only valid for cloud-init analyze script
        expected_subcommands = ['blame', 'show', 'dump']
        error = self.stderr.getvalue()
        for subcommand in expected_subcommands:
            self.assertIn(subcommand, error)

    def test_collect_logs_subcommand_parser(self):
        """The subcommand cloud-init collect-logs calls the subparser."""
        # Provide -h param to collect-logs to avoid having to mock behavior.
        stdout = six.StringIO()
        self.patchStdoutAndStderr(stdout=stdout)
        self._call_main(['cloud-init', 'collect-logs', '-h'])
        self.assertIn('usage: cloud-init collect-log', stdout.getvalue())

    def test_clean_subcommand_parser(self):
        """The subcommand cloud-init clean calls the subparser."""
        # Provide -h param to clean to avoid having to mock behavior.
        stdout = six.StringIO()
        self.patchStdoutAndStderr(stdout=stdout)
        self._call_main(['cloud-init', 'clean', '-h'])
        self.assertIn('usage: cloud-init clean', stdout.getvalue())

    def test_status_subcommand_parser(self):
        """The subcommand cloud-init status calls the subparser."""
        # Provide -h param to clean to avoid having to mock behavior.
        stdout = six.StringIO()
        self.patchStdoutAndStderr(stdout=stdout)
        self._call_main(['cloud-init', 'status', '-h'])
        self.assertIn('usage: cloud-init status', stdout.getvalue())

    def test_devel_subcommand_parser(self):
        """The subcommand cloud-init devel calls the correct subparser."""
        self._call_main(['cloud-init', 'devel'])
        # These subcommands only valid for cloud-init schema script
        expected_subcommands = ['schema']
        error = self.stderr.getvalue()
        for subcommand in expected_subcommands:
            self.assertIn(subcommand, error)

    def test_wb_devel_schema_subcommand_parser(self):
        """The subcommand cloud-init schema calls the correct subparser."""
        exit_code = self._call_main(['cloud-init', 'devel', 'schema'])
        self.assertEqual(1, exit_code)
        # Known whitebox output from schema subcommand
        self.assertEqual(
            'Expected either --config-file argument or --doc\n',
            self.stderr.getvalue())

    def test_wb_devel_schema_subcommand_doc_content(self):
        """Validate that doc content is sane from known examples."""
        stdout = six.StringIO()
        self.patchStdoutAndStderr(stdout=stdout)
        self._call_main(['cloud-init', 'devel', 'schema', '--doc'])
        expected_doc_sections = [
            '**Supported distros:** all',
            '**Supported distros:** centos, debian, fedora',
            '**Config schema**:\n    **resize_rootfs:** (true/false/noblock)',
            '**Examples**::\n\n    runcmd:\n        - [ ls, -l, / ]\n'
        ]
        stdout = stdout.getvalue()
        for expected in expected_doc_sections:
            self.assertIn(expected, stdout)

    @mock.patch('cloudinit.cmd.main.main_single')
    def test_single_subcommand(self, m_main_single):
        """The subcommand 'single' calls main_single with valid args."""
        self._call_main(['cloud-init', 'single', '--name', 'cc_ntp'])
        (name, parseargs) = m_main_single.call_args_list[0][0]
        self.assertEqual('single', name)
        self.assertEqual('single', parseargs.subcommand)
        self.assertEqual('single', parseargs.action[0])
        self.assertFalse(parseargs.debug)
        self.assertFalse(parseargs.force)
        self.assertIsNone(parseargs.frequency)
        self.assertEqual('cc_ntp', parseargs.name)
        self.assertFalse(parseargs.report)

    @mock.patch('cloudinit.cmd.main.dhclient_hook.handle_args')
    def test_dhclient_hook_subcommand(self, m_handle_args):
        """The subcommand 'dhclient-hook' calls dhclient_hook with args."""
        self._call_main(['cloud-init', 'dhclient-hook', 'up', 'eth0'])
        (name, parseargs) = m_handle_args.call_args_list[0][0]
        self.assertEqual('dhclient-hook', name)
        self.assertEqual('dhclient-hook', parseargs.subcommand)
        self.assertEqual('dhclient-hook', parseargs.action[0])
        self.assertFalse(parseargs.debug)
        self.assertFalse(parseargs.force)
        self.assertEqual('up', parseargs.event)
        self.assertEqual('eth0', parseargs.interface)

    @mock.patch('cloudinit.cmd.main.main_features')
    def test_features_hook_subcommand(self, m_features):
        """The subcommand 'features' calls main_features with args."""
        self._call_main(['cloud-init', 'features'])
        (name, parseargs) = m_features.call_args_list[0][0]
        self.assertEqual('features', name)
        self.assertEqual('features', parseargs.subcommand)
        self.assertEqual('features', parseargs.action[0])
        self.assertFalse(parseargs.debug)
        self.assertFalse(parseargs.force)

# : ts=4 expandtab
