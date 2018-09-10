# This file is part of cloud-init. See LICENSE file for license information.

import re

from cloudinit import distros
from cloudinit import ssh_util
from cloudinit.tests.helpers import (CiTestCase, mock)


class MyBaseDistro(distros.Distro):
    # MyBaseDistro is here to test base Distro class implementations

    def __init__(self, name="basedistro", cfg=None, paths=None):
        if not cfg:
            cfg = {}
        if not paths:
            paths = {}
        super(MyBaseDistro, self).__init__(name, cfg, paths)

    def install_packages(self, pkglist):
        raise NotImplementedError()

    def _write_network(self, settings):
        raise NotImplementedError()

    def package_command(self, cmd, args=None, pkgs=None):
        raise NotImplementedError()

    def update_package_sources(self):
        raise NotImplementedError()

    def apply_locale(self, locale, out_fn=None):
        raise NotImplementedError()

    def set_timezone(self, tz):
        raise NotImplementedError()

    def _read_hostname(self, filename, default=None):
        raise NotImplementedError()

    def _write_hostname(self, hostname, filename):
        raise NotImplementedError()

    def _read_system_hostname(self):
        raise NotImplementedError()


@mock.patch("cloudinit.distros.util.system_is_snappy", return_value=False)
@mock.patch("cloudinit.distros.util.subp")
class TestCreateUser(CiTestCase):

    with_logs = True

    def setUp(self):
        super(TestCreateUser, self).setUp()
        self.dist = MyBaseDistro()

    def _useradd2call(self, args):
        # return a mock call for the useradd command in args
        # with expected 'logstring'.
        args = ['useradd'] + args
        logcmd = [a for a in args]
        for i in range(len(args)):
            if args[i] in ('--password',):
                logcmd[i + 1] = 'REDACTED'
        return mock.call(args, logstring=logcmd)

    def test_basic(self, m_subp, m_is_snappy):
        user = 'foouser'
        self.dist.create_user(user)
        self.assertEqual(
            m_subp.call_args_list,
            [self._useradd2call([user, '-m']),
             mock.call(['passwd', '-l', user])])

    def test_no_home(self, m_subp, m_is_snappy):
        user = 'foouser'
        self.dist.create_user(user, no_create_home=True)
        self.assertEqual(
            m_subp.call_args_list,
            [self._useradd2call([user, '-M']),
             mock.call(['passwd', '-l', user])])

    def test_system_user(self, m_subp, m_is_snappy):
        # system user should have no home and get --system
        user = 'foouser'
        self.dist.create_user(user, system=True)
        self.assertEqual(
            m_subp.call_args_list,
            [self._useradd2call([user, '--system', '-M']),
             mock.call(['passwd', '-l', user])])

    def test_explicit_no_home_false(self, m_subp, m_is_snappy):
        user = 'foouser'
        self.dist.create_user(user, no_create_home=False)
        self.assertEqual(
            m_subp.call_args_list,
            [self._useradd2call([user, '-m']),
             mock.call(['passwd', '-l', user])])

    def test_unlocked(self, m_subp, m_is_snappy):
        user = 'foouser'
        self.dist.create_user(user, lock_passwd=False)
        self.assertEqual(
            m_subp.call_args_list,
            [self._useradd2call([user, '-m'])])

    def test_set_password(self, m_subp, m_is_snappy):
        user = 'foouser'
        password = 'passfoo'
        self.dist.create_user(user, passwd=password)
        self.assertEqual(
            m_subp.call_args_list,
            [self._useradd2call([user, '--password', password, '-m']),
             mock.call(['passwd', '-l', user])])

    @mock.patch("cloudinit.distros.util.is_group")
    def test_group_added(self, m_is_group, m_subp, m_is_snappy):
        m_is_group.return_value = False
        user = 'foouser'
        self.dist.create_user(user, groups=['group1'])
        expected = [
            mock.call(['groupadd', 'group1']),
            self._useradd2call([user, '--groups', 'group1', '-m']),
            mock.call(['passwd', '-l', user])]
        self.assertEqual(m_subp.call_args_list, expected)

    @mock.patch("cloudinit.distros.util.is_group")
    def test_only_new_group_added(self, m_is_group, m_subp, m_is_snappy):
        ex_groups = ['existing_group']
        groups = ['group1', ex_groups[0]]
        m_is_group.side_effect = lambda m: m in ex_groups
        user = 'foouser'
        self.dist.create_user(user, groups=groups)
        expected = [
            mock.call(['groupadd', 'group1']),
            self._useradd2call([user, '--groups', ','.join(groups), '-m']),
            mock.call(['passwd', '-l', user])]
        self.assertEqual(m_subp.call_args_list, expected)

    @mock.patch("cloudinit.distros.util.is_group")
    def test_create_groups_with_whitespace_string(
            self, m_is_group, m_subp, m_is_snappy):
        # groups supported as a comma delimeted string even with white space
        m_is_group.return_value = False
        user = 'foouser'
        self.dist.create_user(user, groups='group1, group2')
        expected = [
            mock.call(['groupadd', 'group1']),
            mock.call(['groupadd', 'group2']),
            self._useradd2call([user, '--groups', 'group1,group2', '-m']),
            mock.call(['passwd', '-l', user])]
        self.assertEqual(m_subp.call_args_list, expected)

    def test_explicit_sudo_false(self, m_subp, m_is_snappy):
        user = 'foouser'
        self.dist.create_user(user, sudo=False)
        self.assertEqual(
            m_subp.call_args_list,
            [self._useradd2call([user, '-m']),
             mock.call(['passwd', '-l', user])])

    @mock.patch('cloudinit.ssh_util.setup_user_keys')
    def test_setup_ssh_authorized_keys_with_string(
            self, m_setup_user_keys, m_subp, m_is_snappy):
        """ssh_authorized_keys allows string and calls setup_user_keys."""
        user = 'foouser'
        self.dist.create_user(user, ssh_authorized_keys='mykey')
        self.assertEqual(
            m_subp.call_args_list,
            [self._useradd2call([user, '-m']),
             mock.call(['passwd', '-l', user])])
        m_setup_user_keys.assert_called_once_with(set(['mykey']), user)

    @mock.patch('cloudinit.ssh_util.setup_user_keys')
    def test_setup_ssh_authorized_keys_with_list(
            self, m_setup_user_keys, m_subp, m_is_snappy):
        """ssh_authorized_keys allows lists and calls setup_user_keys."""
        user = 'foouser'
        self.dist.create_user(user, ssh_authorized_keys=['key1', 'key2'])
        self.assertEqual(
            m_subp.call_args_list,
            [self._useradd2call([user, '-m']),
             mock.call(['passwd', '-l', user])])
        m_setup_user_keys.assert_called_once_with(set(['key1', 'key2']), user)

    @mock.patch('cloudinit.ssh_util.setup_user_keys')
    def test_setup_ssh_authorized_keys_with_integer(
            self, m_setup_user_keys, m_subp, m_is_snappy):
        """ssh_authorized_keys warns on non-iterable/string type."""
        user = 'foouser'
        self.dist.create_user(user, ssh_authorized_keys=-1)
        m_setup_user_keys.assert_called_once_with(set([]), user)
        match = re.match(
            r'.*WARNING: Invalid type \'<(type|class) \'int\'>\' detected for'
            ' \'ssh_authorized_keys\'.*',
            self.logs.getvalue(),
            re.DOTALL)
        self.assertIsNotNone(
            match, 'Missing ssh_authorized_keys invalid type warning')

    @mock.patch('cloudinit.ssh_util.setup_user_keys')
    def test_create_user_with_ssh_redirect_user_no_cloud_keys(
            self, m_setup_user_keys, m_subp, m_is_snappy):
        """Log a warning when trying to redirect a user no cloud ssh keys."""
        user = 'foouser'
        self.dist.create_user(user, ssh_redirect_user='someuser')
        self.assertIn(
            'WARNING: Unable to disable ssh logins for foouser given '
            'ssh_redirect_user: someuser. No cloud public-keys present.\n',
            self.logs.getvalue())
        m_setup_user_keys.assert_not_called()

    @mock.patch('cloudinit.ssh_util.setup_user_keys')
    def test_create_user_with_ssh_redirect_user_with_cloud_keys(
            self, m_setup_user_keys, m_subp, m_is_snappy):
        """Disable ssh when ssh_redirect_user and cloud ssh keys are set."""
        user = 'foouser'
        self.dist.create_user(
            user, ssh_redirect_user='someuser', cloud_public_ssh_keys=['key1'])
        disable_prefix = ssh_util.DISABLE_USER_OPTS
        disable_prefix = disable_prefix.replace('$USER', 'someuser')
        disable_prefix = disable_prefix.replace('$DISABLE_USER', user)
        m_setup_user_keys.assert_called_once_with(
            set(['key1']), 'foouser', options=disable_prefix)

    @mock.patch('cloudinit.ssh_util.setup_user_keys')
    def test_create_user_with_ssh_redirect_user_does_not_disable_auth_keys(
            self, m_setup_user_keys, m_subp, m_is_snappy):
        """Do not disable ssh_authorized_keys when ssh_redirect_user is set."""
        user = 'foouser'
        self.dist.create_user(
            user, ssh_authorized_keys='auth1', ssh_redirect_user='someuser',
            cloud_public_ssh_keys=['key1'])
        disable_prefix = ssh_util.DISABLE_USER_OPTS
        disable_prefix = disable_prefix.replace('$USER', 'someuser')
        disable_prefix = disable_prefix.replace('$DISABLE_USER', user)
        self.assertEqual(
            m_setup_user_keys.call_args_list,
            [mock.call(set(['auth1']), user),  # not disabled
             mock.call(set(['key1']), 'foouser', options=disable_prefix)])

# vi: ts=4 expandtab
