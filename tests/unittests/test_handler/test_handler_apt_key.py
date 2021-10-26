import os
import shutil
import tempfile
from unittest import mock

from cloudinit.tests import helpers
from cloudinit.config import cc_apt_configure
from cloudinit import subp
from cloudinit import util

TEST_KEY_HUMAN = '''
/etc/apt/cloud-init.gpg.d/my_key.gpg
--------------------------------------------
pub   rsa4096 2021-10-22 [SC]
      3A3E F34D FDED B3B7 F3FD  F603 F83F 7712 9A5E BD85
uid           [ unknown] Brett Holman <brett.holman@canonical.com>
sub   rsa4096 2021-10-22 [A]
sub   rsa4096 2021-10-22 [E]
'''

TEST_KEY_MACHINE = '''
tru::1:1635129362:0:3:1:5
pub:-:4096:1:F83F77129A5EBD85:1634912922:::-:::scESCA::::::23::0:
fpr:::::::::3A3EF34DFDEDB3B7F3FDF603F83F77129A5EBD85:
uid:-::::1634912922::64F1F1D6FA96316752D635D7C6406C52C40713C7::Brett Holman \
<brett.holman@canonical.com>::::::::::0:
sub:-:4096:1:544B39C9A9141F04:1634912922::::::a::::::23:
fpr:::::::::8BD901490D6EC986D03D6F0D544B39C9A9141F04:
sub:-:4096:1:F45D9443F0A87092:1634912922::::::e::::::23:
fpr:::::::::8CCCB332317324F030A45B19F45D9443F0A87092:
'''

TEST_KEY_FINGERPRINT_HUMAN = \
    '3A3E F34D FDED B3B7 F3FD  F603 F83F 7712 9A5E BD85'

TEST_KEY_FINGERPRINT_MACHINE = \
    '3A3EF34DFDEDB3B7F3FDF603F83F77129A5EBD85'


class TestAptKey(helpers.FilesystemMockingTestCase):
    """TestAptKey
    Class to test apt-key commands
    """
    def setUp(self):
        super(TestAptKey, self).setUp()
        self.tmp = tempfile.mkdtemp()
        self.new_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.addCleanup(shutil.rmtree, self.new_root)

    def _apt_key_add_success_helper(self, directory, hardened=False):
        with mock.patch.object(
                subp,
                'subp',
                return_value=('fakekey', '')):
            with mock.patch.object(
                    util,
                    'write_file'):
                file = cc_apt_configure.apt_key(
                    'add',
                    output_file='my-key',
                    data='fakekey',
                    hardened=hardened)
        assert file == directory + '/my-key.gpg'

    def test_apt_key_add_success(self):
        self._apt_key_add_success_helper('/etc/apt/trusted.gpg.d')

    def test_apt_key_add_success_hardened(self):
        self._apt_key_add_success_helper(
            '/etc/apt/cloud-init.gpg.d',
            hardened=True)

    def test_apt_key_add_fail_no_file_name(self):
        file = cc_apt_configure.apt_key(
            'add',
            output_file=None,
            data='')
        assert '/dev/null' == file

    def _apt_key_fail_helper(self, exception):
        with mock.patch.object(
                subp,
                'subp',
                side_effect=exception):
            file = cc_apt_configure.apt_key(
                'add',
                output_file='my-key',
                data='fakekey')
        assert file == '/dev/null'

    def test_apt_key_add_fail_no_file_name_subproc(self):
        self._apt_key_fail_helper(subp.ProcessExecutionError)

    def test_apt_key_add_fail_no_file_name_unicode(self):
        self._apt_key_fail_helper(UnicodeDecodeError('test', b'', 1, 1, ''))

    def _apt_key_list_success_helper(self, finger, key, human_output=True):
        with mock.patch.object(
                subp,
                'subp',
                return_value=(key, '')):

            with mock.patch.object(
                    os,
                    'listdir',
                    return_value=('/fake/dir/key.gpg',)):
                keys = cc_apt_configure.apt_key('list', human_output)
                assert finger in keys

    def test_apt_key_list_success_human(self):
        self._apt_key_list_success_helper(
            TEST_KEY_FINGERPRINT_HUMAN,
            TEST_KEY_HUMAN)

    def test_apt_key_list_success_machine(self):
        self._apt_key_list_success_helper(
            TEST_KEY_FINGERPRINT_MACHINE,
            TEST_KEY_MACHINE, human_output=False)

    def test_apt_key_list_fail_no_keys(self):
        with mock.patch.object(
                os,
                'listdir',
                return_value=()):
            with mock.patch.object(
                    subp,
                    'subp',
                    return_value=('', '')):
                keys = cc_apt_configure.apt_key('list')
        assert not keys

    def test_apt_key_list_fail_no_keys_file(self):
        with mock.patch.object(
                os,
                'listdir',
                return_value=('file_not_gpg_key.txt')):
            with mock.patch.object(
                    subp,
                    'subp',
                    return_value=('', '')):
                keys = cc_apt_configure.apt_key('list')
        assert not keys

    def test_apt_key_list_fail_bad_key_file(self):
        with mock.patch.object(
                subp,
                'subp',
                side_effect=subp.ProcessExecutionError):
            with mock.patch.object(
                    os,
                    'listdir',
                    return_value=('bad_gpg_key.gpg')):
                keys = cc_apt_configure.apt_key('list')
        assert not keys
