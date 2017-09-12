# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.cmd.devel import logs
from cloudinit.util import ensure_dir, load_file, subp, write_file
from cloudinit.tests.helpers import FilesystemMockingTestCase, wrap_and_call
from datetime import datetime
import os


class TestCollectLogs(FilesystemMockingTestCase):

    def setUp(self):
        super(TestCollectLogs, self).setUp()
        self.new_root = self.tmp_dir()
        self.run_dir = self.tmp_path('run', self.new_root)

    def test_collect_logs_creates_tarfile(self):
        """collect-logs creates a tarfile with all related cloud-init info."""
        log1 = self.tmp_path('cloud-init.log', self.new_root)
        write_file(log1, 'cloud-init-log')
        log2 = self.tmp_path('cloud-init-output.log', self.new_root)
        write_file(log2, 'cloud-init-output-log')
        ensure_dir(self.run_dir)
        write_file(self.tmp_path('results.json', self.run_dir), 'results')
        output_tarfile = self.tmp_path('logs.tgz')

        date = datetime.utcnow().date().strftime('%Y-%m-%d')
        date_logdir = 'cloud-init-logs-{0}'.format(date)

        expected_subp = {
            ('dpkg-query', '--show', "-f=${Version}\n", 'cloud-init'):
                '0.7fake\n',
            ('dmesg',): 'dmesg-out\n',
            ('journalctl', '-o', 'short-precise'): 'journal-out\n',
            ('tar', 'czvf', output_tarfile, date_logdir): ''
        }

        def fake_subp(cmd):
            cmd_tuple = tuple(cmd)
            if cmd_tuple not in expected_subp:
                raise AssertionError(
                    'Unexpected command provided to subp: {0}'.format(cmd))
            if cmd == ['tar', 'czvf', output_tarfile, date_logdir]:
                subp(cmd)  # Pass through tar cmd so we can check output
            return expected_subp[cmd_tuple], ''

        wrap_and_call(
            'cloudinit.cmd.devel.logs',
            {'subp': {'side_effect': fake_subp},
             'CLOUDINIT_LOGS': {'new': [log1, log2]},
             'CLOUDINIT_RUN_DIR': {'new': self.run_dir}},
            logs.collect_logs, output_tarfile, include_userdata=False)
        # unpack the tarfile and check file contents
        subp(['tar', 'zxvf', output_tarfile, '-C', self.new_root])
        out_logdir = self.tmp_path(date_logdir, self.new_root)
        self.assertEqual(
            '0.7fake\n',
            load_file(os.path.join(out_logdir, 'version')))
        self.assertEqual(
            'cloud-init-log',
            load_file(os.path.join(out_logdir, 'cloud-init.log')))
        self.assertEqual(
            'cloud-init-output-log',
            load_file(os.path.join(out_logdir, 'cloud-init-output.log')))
        self.assertEqual(
            'dmesg-out\n',
            load_file(os.path.join(out_logdir, 'dmesg.txt')))
        self.assertEqual(
            'journal-out\n',
            load_file(os.path.join(out_logdir, 'journal.txt')))
        self.assertEqual(
            'results',
            load_file(
                os.path.join(out_logdir, 'run', 'cloud-init', 'results.json')))

    def test_collect_logs_includes_optional_userdata(self):
        """collect-logs include userdata when --include-userdata is set."""
        log1 = self.tmp_path('cloud-init.log', self.new_root)
        write_file(log1, 'cloud-init-log')
        log2 = self.tmp_path('cloud-init-output.log', self.new_root)
        write_file(log2, 'cloud-init-output-log')
        userdata = self.tmp_path('user-data.txt', self.new_root)
        write_file(userdata, 'user-data')
        ensure_dir(self.run_dir)
        write_file(self.tmp_path('results.json', self.run_dir), 'results')
        output_tarfile = self.tmp_path('logs.tgz')

        date = datetime.utcnow().date().strftime('%Y-%m-%d')
        date_logdir = 'cloud-init-logs-{0}'.format(date)

        expected_subp = {
            ('dpkg-query', '--show', "-f=${Version}\n", 'cloud-init'):
                '0.7fake',
            ('dmesg',): 'dmesg-out\n',
            ('journalctl', '-o', 'short-precise'): 'journal-out\n',
            ('tar', 'czvf', output_tarfile, date_logdir): ''
        }

        def fake_subp(cmd):
            cmd_tuple = tuple(cmd)
            if cmd_tuple not in expected_subp:
                raise AssertionError(
                    'Unexpected command provided to subp: {0}'.format(cmd))
            if cmd == ['tar', 'czvf', output_tarfile, date_logdir]:
                subp(cmd)  # Pass through tar cmd so we can check output
            return expected_subp[cmd_tuple], ''

        wrap_and_call(
            'cloudinit.cmd.devel.logs',
            {'subp': {'side_effect': fake_subp},
             'CLOUDINIT_LOGS': {'new': [log1, log2]},
             'CLOUDINIT_RUN_DIR': {'new': self.run_dir},
             'USER_DATA_FILE': {'new': userdata}},
            logs.collect_logs, output_tarfile, include_userdata=True)
        # unpack the tarfile and check file contents
        subp(['tar', 'zxvf', output_tarfile, '-C', self.new_root])
        out_logdir = self.tmp_path(date_logdir, self.new_root)
        self.assertEqual(
            'user-data',
            load_file(os.path.join(out_logdir, 'user-data.txt')))
