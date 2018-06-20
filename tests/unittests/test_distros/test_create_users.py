# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import distros
from cloudinit.tests.helpers import (TestCase, mock)


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
class TestCreateUser(TestCase):
    def setUp(self):
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

# vi: ts=4 expandtab
