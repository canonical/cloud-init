# This file is part of cloud-init. See LICENSE file for license information.

from collections import namedtuple
import copy
import os
from six import StringIO

from cloudinit.cmd import main
from cloudinit.util import (
    ensure_dir, load_file, write_file, yaml_dumps)
from cloudinit.tests.helpers import (
    FilesystemMockingTestCase, wrap_and_call)

mypaths = namedtuple('MyPaths', 'run_dir')
myargs = namedtuple('MyArgs', 'debug files force local reporter subcommand')


class TestMain(FilesystemMockingTestCase):

    with_logs = True

    def setUp(self):
        super(TestMain, self).setUp()
        self.new_root = self.tmp_dir()
        self.cloud_dir = self.tmp_path('var/lib/cloud/', dir=self.new_root)
        os.makedirs(self.cloud_dir)
        self.replicateTestRoot('simple_ubuntu', self.new_root)
        self.cfg = {
            'datasource_list': ['None'],
            'runcmd': ['ls /etc'],  # test ALL_DISTROS
            'system_info': {'paths': {'cloud_dir': self.cloud_dir,
                                      'run_dir': self.new_root}},
            'write_files': [
                {
                    'path': '/etc/blah.ini',
                    'content': 'blah',
                    'permissions': 0o755,
                },
            ],
            'cloud_init_modules': ['write-files', 'runcmd'],
        }
        cloud_cfg = yaml_dumps(self.cfg)
        ensure_dir(os.path.join(self.new_root, 'etc', 'cloud'))
        self.cloud_cfg_file = os.path.join(
            self.new_root, 'etc', 'cloud', 'cloud.cfg')
        write_file(self.cloud_cfg_file, cloud_cfg)
        self.patchOS(self.new_root)
        self.patchUtils(self.new_root)
        self.stderr = StringIO()
        self.patchStdoutAndStderr(stderr=self.stderr)

    def test_main_init_run_net_stops_on_file_no_net(self):
        """When no-net file is present, main_init does not process modules."""
        stop_file = os.path.join(self.cloud_dir, 'data', 'no-net')  # stop file
        write_file(stop_file, '')
        cmdargs = myargs(
            debug=False, files=None, force=False, local=False, reporter=None,
            subcommand='init')
        (_item1, item2) = wrap_and_call(
            'cloudinit.cmd.main',
            {'util.close_stdin': True,
             'netinfo.debug_info': 'my net debug info',
             'util.fixup_output': ('outfmt', 'errfmt')},
            main.main_init, 'init', cmdargs)
        # We should not run write_files module
        self.assertFalse(
            os.path.exists(os.path.join(self.new_root, 'etc/blah.ini')),
            'Unexpected run of write_files module produced blah.ini')
        self.assertEqual([], item2)
        # Instancify is called
        instance_id_path = 'var/lib/cloud/data/instance-id'
        self.assertFalse(
            os.path.exists(os.path.join(self.new_root, instance_id_path)),
            'Unexpected call to datasource.instancify produced instance-id')
        expected_logs = [
            "Exiting. stop file ['{stop_file}'] existed\n".format(
                stop_file=stop_file),
            'my net debug info'  # netinfo.debug_info
        ]
        for log in expected_logs:
            self.assertIn(log, self.stderr.getvalue())

    def test_main_init_run_net_runs_modules(self):
        """Modules like write_files are run in 'net' mode."""
        cmdargs = myargs(
            debug=False, files=None, force=False, local=False, reporter=None,
            subcommand='init')
        (_item1, item2) = wrap_and_call(
            'cloudinit.cmd.main',
            {'util.close_stdin': True,
             'netinfo.debug_info': 'my net debug info',
             'util.fixup_output': ('outfmt', 'errfmt')},
            main.main_init, 'init', cmdargs)
        self.assertEqual([], item2)
        # Instancify is called
        instance_id_path = 'var/lib/cloud/data/instance-id'
        self.assertEqual(
            'iid-datasource-none\n',
            os.path.join(load_file(
                os.path.join(self.new_root, instance_id_path))))
        # modules are run (including write_files)
        self.assertEqual(
            'blah', load_file(os.path.join(self.new_root, 'etc/blah.ini')))
        expected_logs = [
            'network config is disabled by fallback',  # apply_network_config
            'my net debug info',  # netinfo.debug_info
            'no previous run detected'
        ]
        for log in expected_logs:
            self.assertIn(log, self.stderr.getvalue())

    def test_main_init_run_net_calls_set_hostname_when_metadata_present(self):
        """When local-hostname metadata is present, call cc_set_hostname."""
        self.cfg['datasource'] = {
            'None': {'metadata': {'local-hostname': 'md-hostname'}}}
        cloud_cfg = yaml_dumps(self.cfg)
        write_file(self.cloud_cfg_file, cloud_cfg)
        cmdargs = myargs(
            debug=False, files=None, force=False, local=False, reporter=None,
            subcommand='init')

        def set_hostname(name, cfg, cloud, log, args):
            self.assertEqual('set-hostname', name)
            updated_cfg = copy.deepcopy(self.cfg)
            updated_cfg.update(
                {'def_log_file': '/var/log/cloud-init.log',
                 'log_cfgs': [],
                 'syslog_fix_perms': [
                     'syslog:adm', 'root:adm', 'root:wheel', 'root:root'
                 ],
                 'vendor_data': {'enabled': True, 'prefix': []}})
            updated_cfg.pop('system_info')

            self.assertEqual(updated_cfg, cfg)
            self.assertEqual(main.LOG, log)
            self.assertIsNone(args)

        (_item1, item2) = wrap_and_call(
            'cloudinit.cmd.main',
            {'util.close_stdin': True,
             'netinfo.debug_info': 'my net debug info',
             'cc_set_hostname.handle': {'side_effect': set_hostname},
             'util.fixup_output': ('outfmt', 'errfmt')},
            main.main_init, 'init', cmdargs)
        self.assertEqual([], item2)
        # Instancify is called
        instance_id_path = 'var/lib/cloud/data/instance-id'
        self.assertEqual(
            'iid-datasource-none\n',
            os.path.join(load_file(
                os.path.join(self.new_root, instance_id_path))))
        # modules are run (including write_files)
        self.assertEqual(
            'blah', load_file(os.path.join(self.new_root, 'etc/blah.ini')))
        expected_logs = [
            'network config is disabled by fallback',  # apply_network_config
            'my net debug info',  # netinfo.debug_info
            'no previous run detected'
        ]
        for log in expected_logs:
            self.assertIn(log, self.stderr.getvalue())

# vi: ts=4 expandtab
