# This file is part of cloud-init. See LICENSE file for license information.


from cloudinit.config import cc_ssh
from cloudinit import ssh_util
from cloudinit.tests.helpers import CiTestCase, mock

MODPATH = "cloudinit.config.cc_ssh."


@mock.patch(MODPATH + "ssh_util.setup_user_keys")
class TestHandleSsh(CiTestCase):
    """Test cc_ssh handling of ssh config."""

    def test_apply_credentials_with_user(self, m_setup_keys):
        """Apply keys for the given user and root."""
        keys = ["key1"]
        user = "clouduser"
        cc_ssh.apply_credentials(keys, user, False, ssh_util.DISABLE_USER_OPTS)
        self.assertEqual([mock.call(set(keys), user),
                          mock.call(set(keys), "root", options="")],
                         m_setup_keys.call_args_list)

    def test_apply_credentials_with_no_user(self, m_setup_keys):
        """Apply keys for root only."""
        keys = ["key1"]
        user = None
        cc_ssh.apply_credentials(keys, user, False, ssh_util.DISABLE_USER_OPTS)
        self.assertEqual([mock.call(set(keys), "root", options="")],
                         m_setup_keys.call_args_list)

    def test_apply_credentials_with_user_disable_root(self, m_setup_keys):
        """Apply keys for the given user and disable root ssh."""
        keys = ["key1"]
        user = "clouduser"
        options = ssh_util.DISABLE_USER_OPTS
        cc_ssh.apply_credentials(keys, user, True, options)
        options = options.replace("$USER", user)
        options = options.replace("$DISABLE_USER", "root")
        self.assertEqual([mock.call(set(keys), user),
                          mock.call(set(keys), "root", options=options)],
                         m_setup_keys.call_args_list)

    def test_apply_credentials_with_no_user_disable_root(self, m_setup_keys):
        """Apply keys no user and disable root ssh."""
        keys = ["key1"]
        user = None
        options = ssh_util.DISABLE_USER_OPTS
        cc_ssh.apply_credentials(keys, user, True, options)
        options = options.replace("$USER", "NONE")
        options = options.replace("$DISABLE_USER", "root")
        self.assertEqual([mock.call(set(keys), "root", options=options)],
                         m_setup_keys.call_args_list)

    @mock.patch(MODPATH + "glob.glob")
    @mock.patch(MODPATH + "ug_util.normalize_users_groups")
    @mock.patch(MODPATH + "os.path.exists")
    def test_handle_no_cfg(self, m_path_exists, m_nug,
                           m_glob, m_setup_keys):
        """Test handle with no config ignores generating existing keyfiles."""
        cfg = {}
        keys = ["key1"]
        m_glob.return_value = []  # Return no matching keys to prevent removal
        # Mock os.path.exits to True to short-circuit the key writing logic
        m_path_exists.return_value = True
        m_nug.return_value = ([], {})
        cloud = self.tmp_cloud(
            distro='ubuntu', metadata={'public-keys': keys})
        cc_ssh.handle("name", cfg, cloud, None, None)
        options = ssh_util.DISABLE_USER_OPTS.replace("$USER", "NONE")
        options = options.replace("$DISABLE_USER", "root")
        m_glob.assert_called_once_with('/etc/ssh/ssh_host_*key*')
        self.assertIn(
            [mock.call('/etc/ssh/ssh_host_rsa_key'),
             mock.call('/etc/ssh/ssh_host_dsa_key'),
             mock.call('/etc/ssh/ssh_host_ecdsa_key'),
             mock.call('/etc/ssh/ssh_host_ed25519_key')],
            m_path_exists.call_args_list)
        self.assertEqual([mock.call(set(keys), "root", options=options)],
                         m_setup_keys.call_args_list)

    @mock.patch(MODPATH + "glob.glob")
    @mock.patch(MODPATH + "ug_util.normalize_users_groups")
    @mock.patch(MODPATH + "os.path.exists")
    def test_handle_no_cfg_and_default_root(self, m_path_exists, m_nug,
                                            m_glob, m_setup_keys):
        """Test handle with no config and a default distro user."""
        cfg = {}
        keys = ["key1"]
        user = "clouduser"
        m_glob.return_value = []  # Return no matching keys to prevent removal
        # Mock os.path.exits to True to short-circuit the key writing logic
        m_path_exists.return_value = True
        m_nug.return_value = ({user: {"default": user}}, {})
        cloud = self.tmp_cloud(
            distro='ubuntu', metadata={'public-keys': keys})
        cc_ssh.handle("name", cfg, cloud, None, None)

        options = ssh_util.DISABLE_USER_OPTS.replace("$USER", user)
        options = options.replace("$DISABLE_USER", "root")
        self.assertEqual([mock.call(set(keys), user),
                          mock.call(set(keys), "root", options=options)],
                         m_setup_keys.call_args_list)

    @mock.patch(MODPATH + "glob.glob")
    @mock.patch(MODPATH + "ug_util.normalize_users_groups")
    @mock.patch(MODPATH + "os.path.exists")
    def test_handle_cfg_with_explicit_disable_root(self, m_path_exists, m_nug,
                                                   m_glob, m_setup_keys):
        """Test handle with explicit disable_root and a default distro user."""
        # This test is identical to test_handle_no_cfg_and_default_root,
        # except this uses an explicit cfg value
        cfg = {"disable_root": True}
        keys = ["key1"]
        user = "clouduser"
        m_glob.return_value = []  # Return no matching keys to prevent removal
        # Mock os.path.exits to True to short-circuit the key writing logic
        m_path_exists.return_value = True
        m_nug.return_value = ({user: {"default": user}}, {})
        cloud = self.tmp_cloud(
            distro='ubuntu', metadata={'public-keys': keys})
        cc_ssh.handle("name", cfg, cloud, None, None)

        options = ssh_util.DISABLE_USER_OPTS.replace("$USER", user)
        options = options.replace("$DISABLE_USER", "root")
        self.assertEqual([mock.call(set(keys), user),
                          mock.call(set(keys), "root", options=options)],
                         m_setup_keys.call_args_list)

    @mock.patch(MODPATH + "glob.glob")
    @mock.patch(MODPATH + "ug_util.normalize_users_groups")
    @mock.patch(MODPATH + "os.path.exists")
    def test_handle_cfg_without_disable_root(self, m_path_exists, m_nug,
                                             m_glob, m_setup_keys):
        """Test handle with disable_root == False."""
        # When disable_root == False, the ssh redirect for root is skipped
        cfg = {"disable_root": False}
        keys = ["key1"]
        user = "clouduser"
        m_glob.return_value = []  # Return no matching keys to prevent removal
        # Mock os.path.exits to True to short-circuit the key writing logic
        m_path_exists.return_value = True
        m_nug.return_value = ({user: {"default": user}}, {})
        cloud = self.tmp_cloud(
            distro='ubuntu', metadata={'public-keys': keys})
        cloud.get_public_ssh_keys = mock.Mock(return_value=keys)
        cc_ssh.handle("name", cfg, cloud, None, None)

        self.assertEqual([mock.call(set(keys), user),
                          mock.call(set(keys), "root", options="")],
                         m_setup_keys.call_args_list)
