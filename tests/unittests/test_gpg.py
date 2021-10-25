from unittest import mock

from cloudinit.tests import helpers
from cloudinit import gpg
from cloudinit import subp

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


class TestGPGCommands(helpers.CiTestCase):
    def test_dearmor_empty_value(self):
        with self.assertRaises(ValueError):
            gpg.dearmor(None)

    def test_dearmor_bad_value(self):
        with mock.patch.object(
                subp,
                'subp',
                side_effect=subp.ProcessExecutionError):
            with self.assertRaises(subp.ProcessExecutionError):
                gpg.dearmor('garbage key value')

    def list_output_helper(self, fingerprint, key):
        with mock.patch.object(subp, 'subp', return_value=(key, '')):
            assert fingerprint in gpg.list('/path/to/key.gpg')

    def test_list_human_output(self):
        self.list_output_helper(TEST_KEY_FINGERPRINT_HUMAN, TEST_KEY_HUMAN)

    def test_list_machine_output(self):
        self.list_output_helper(TEST_KEY_FINGERPRINT_MACHINE, TEST_KEY_MACHINE)

    def test_list_bad_value(self):
        with mock.patch.object(
                subp,
                'subp',
                side_effect=subp.ProcessExecutionError):
            with self.assertRaises(subp.ProcessExecutionError):
                gpg.list('/path/to/bad/key.gpg')
