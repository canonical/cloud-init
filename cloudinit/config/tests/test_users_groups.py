# This file is part of cloud-init. See LICENSE file for license information.


from cloudinit.config import cc_users_groups
from cloudinit.tests.helpers import CiTestCase, mock

MODPATH = "cloudinit.config.cc_users_groups"


@mock.patch('cloudinit.distros.ubuntu.Distro.create_group')
@mock.patch('cloudinit.distros.ubuntu.Distro.create_user')
class TestHandleUsersGroups(CiTestCase):
    """Test cc_users_groups handling of config."""

    with_logs = True

    def test_handle_no_cfg_creates_no_users_or_groups(self, m_user, m_group):
        """Test handle with no config will not create users or groups."""
        cfg = {}  # merged cloud-config
        # System config defines a default user for the distro.
        sys_cfg = {'default_user': {'name': 'ubuntu', 'lock_passwd': True,
                                    'groups': ['lxd', 'sudo'],
                                    'shell': '/bin/bash'}}
        metadata = {}
        cloud = self.tmp_cloud(
            distro='ubuntu', sys_cfg=sys_cfg, metadata=metadata)
        cc_users_groups.handle('modulename', cfg, cloud, None, None)
        m_user.assert_not_called()
        m_group.assert_not_called()

    def test_handle_users_in_cfg_calls_create_users(self, m_user, m_group):
        """When users in config, create users with distro.create_user."""
        cfg = {'users': ['default', {'name': 'me2'}]}  # merged cloud-config
        # System config defines a default user for the distro.
        sys_cfg = {'default_user': {'name': 'ubuntu', 'lock_passwd': True,
                                    'groups': ['lxd', 'sudo'],
                                    'shell': '/bin/bash'}}
        metadata = {}
        cloud = self.tmp_cloud(
            distro='ubuntu', sys_cfg=sys_cfg, metadata=metadata)
        cc_users_groups.handle('modulename', cfg, cloud, None, None)
        self.assertItemsEqual(
            m_user.call_args_list,
            [mock.call('ubuntu', groups='lxd,sudo', lock_passwd=True,
                       shell='/bin/bash'),
             mock.call('me2', default=False)])
        m_group.assert_not_called()

    def test_users_with_ssh_redirect_user_passes_keys(self, m_user, m_group):
        """When ssh_redirect_user is True pass default user and cloud keys."""
        cfg = {
            'users': ['default', {'name': 'me2', 'ssh_redirect_user': True}]}
        # System config defines a default user for the distro.
        sys_cfg = {'default_user': {'name': 'ubuntu', 'lock_passwd': True,
                                    'groups': ['lxd', 'sudo'],
                                    'shell': '/bin/bash'}}
        metadata = {'public-keys': ['key1']}
        cloud = self.tmp_cloud(
            distro='ubuntu', sys_cfg=sys_cfg, metadata=metadata)
        cc_users_groups.handle('modulename', cfg, cloud, None, None)
        self.assertItemsEqual(
            m_user.call_args_list,
            [mock.call('ubuntu', groups='lxd,sudo', lock_passwd=True,
                       shell='/bin/bash'),
             mock.call('me2', cloud_public_ssh_keys=['key1'], default=False,
                       ssh_redirect_user='ubuntu')])
        m_group.assert_not_called()

    def test_users_with_ssh_redirect_user_default_str(self, m_user, m_group):
        """When ssh_redirect_user is 'default' pass default username."""
        cfg = {
            'users': ['default', {'name': 'me2',
                                  'ssh_redirect_user': 'default'}]}
        # System config defines a default user for the distro.
        sys_cfg = {'default_user': {'name': 'ubuntu', 'lock_passwd': True,
                                    'groups': ['lxd', 'sudo'],
                                    'shell': '/bin/bash'}}
        metadata = {'public-keys': ['key1']}
        cloud = self.tmp_cloud(
            distro='ubuntu', sys_cfg=sys_cfg, metadata=metadata)
        cc_users_groups.handle('modulename', cfg, cloud, None, None)
        self.assertItemsEqual(
            m_user.call_args_list,
            [mock.call('ubuntu', groups='lxd,sudo', lock_passwd=True,
                       shell='/bin/bash'),
             mock.call('me2', cloud_public_ssh_keys=['key1'], default=False,
                       ssh_redirect_user='ubuntu')])
        m_group.assert_not_called()

    def test_users_with_ssh_redirect_user_non_default(self, m_user, m_group):
        """Warn when ssh_redirect_user is not 'default'."""
        cfg = {
            'users': ['default', {'name': 'me2',
                                  'ssh_redirect_user': 'snowflake'}]}
        # System config defines a default user for the distro.
        sys_cfg = {'default_user': {'name': 'ubuntu', 'lock_passwd': True,
                                    'groups': ['lxd', 'sudo'],
                                    'shell': '/bin/bash'}}
        metadata = {'public-keys': ['key1']}
        cloud = self.tmp_cloud(
            distro='ubuntu', sys_cfg=sys_cfg, metadata=metadata)
        with self.assertRaises(ValueError) as context_manager:
            cc_users_groups.handle('modulename', cfg, cloud, None, None)
        m_group.assert_not_called()
        self.assertEqual(
            'Not creating user me2. Invalid value of ssh_redirect_user:'
            ' snowflake. Expected values: true, default or false.',
            str(context_manager.exception))

    def test_users_with_ssh_redirect_user_default_false(self, m_user, m_group):
        """When unspecified ssh_redirect_user is false and not set up."""
        cfg = {'users': ['default', {'name': 'me2'}]}
        # System config defines a default user for the distro.
        sys_cfg = {'default_user': {'name': 'ubuntu', 'lock_passwd': True,
                                    'groups': ['lxd', 'sudo'],
                                    'shell': '/bin/bash'}}
        metadata = {'public-keys': ['key1']}
        cloud = self.tmp_cloud(
            distro='ubuntu', sys_cfg=sys_cfg, metadata=metadata)
        cc_users_groups.handle('modulename', cfg, cloud, None, None)
        self.assertItemsEqual(
            m_user.call_args_list,
            [mock.call('ubuntu', groups='lxd,sudo', lock_passwd=True,
                       shell='/bin/bash'),
             mock.call('me2', default=False)])
        m_group.assert_not_called()

    def test_users_ssh_redirect_user_and_no_default(self, m_user, m_group):
        """Warn when ssh_redirect_user is True and no default user present."""
        cfg = {
            'users': ['default', {'name': 'me2', 'ssh_redirect_user': True}]}
        # System config defines *no* default user for the distro.
        sys_cfg = {}
        metadata = {}  # no public-keys defined
        cloud = self.tmp_cloud(
            distro='ubuntu', sys_cfg=sys_cfg, metadata=metadata)
        cc_users_groups.handle('modulename', cfg, cloud, None, None)
        m_user.assert_called_once_with('me2', default=False)
        m_group.assert_not_called()
        self.assertEqual(
            'WARNING: Ignoring ssh_redirect_user: True for me2. No'
            ' default_user defined. Perhaps missing'
            ' cloud configuration users:  [default, ..].\n',
            self.logs.getvalue())
