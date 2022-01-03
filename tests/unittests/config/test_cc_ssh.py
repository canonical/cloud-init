# This file is part of cloud-init. See LICENSE file for license information.

import logging
import os.path

from cloudinit import ssh_util
from cloudinit.config import cc_ssh
from tests.unittests.helpers import CiTestCase, mock

LOG = logging.getLogger(__name__)

MODPATH = "cloudinit.config.cc_ssh."
KEY_NAMES_NO_DSA = [
    name for name in cc_ssh.GENERATE_KEY_NAMES if name not in "dsa"
]


@mock.patch(MODPATH + "ssh_util.setup_user_keys")
class TestHandleSsh(CiTestCase):
    """Test cc_ssh handling of ssh config."""

    def _publish_hostkey_test_setup(self):
        self.test_hostkeys = {
            "dsa": ("ssh-dss", "AAAAB3NzaC1kc3MAAACB"),
            "ecdsa": ("ecdsa-sha2-nistp256", "AAAAE2VjZ"),
            "ed25519": ("ssh-ed25519", "AAAAC3NzaC1lZDI"),
            "rsa": ("ssh-rsa", "AAAAB3NzaC1yc2EAAA"),
        }
        self.test_hostkey_files = []
        hostkey_tmpdir = self.tmp_dir()
        for key_type in cc_ssh.GENERATE_KEY_NAMES:
            key_data = self.test_hostkeys[key_type]
            filename = "ssh_host_%s_key.pub" % key_type
            filepath = os.path.join(hostkey_tmpdir, filename)
            self.test_hostkey_files.append(filepath)
            with open(filepath, "w") as f:
                f.write(" ".join(key_data))

        cc_ssh.KEY_FILE_TPL = os.path.join(hostkey_tmpdir, "ssh_host_%s_key")

    def test_apply_credentials_with_user(self, m_setup_keys):
        """Apply keys for the given user and root."""
        keys = ["key1"]
        user = "clouduser"
        cc_ssh.apply_credentials(keys, user, False, ssh_util.DISABLE_USER_OPTS)
        self.assertEqual(
            [
                mock.call(set(keys), user),
                mock.call(set(keys), "root", options=""),
            ],
            m_setup_keys.call_args_list,
        )

    def test_apply_credentials_with_no_user(self, m_setup_keys):
        """Apply keys for root only."""
        keys = ["key1"]
        user = None
        cc_ssh.apply_credentials(keys, user, False, ssh_util.DISABLE_USER_OPTS)
        self.assertEqual(
            [mock.call(set(keys), "root", options="")],
            m_setup_keys.call_args_list,
        )

    def test_apply_credentials_with_user_disable_root(self, m_setup_keys):
        """Apply keys for the given user and disable root ssh."""
        keys = ["key1"]
        user = "clouduser"
        options = ssh_util.DISABLE_USER_OPTS
        cc_ssh.apply_credentials(keys, user, True, options)
        options = options.replace("$USER", user)
        options = options.replace("$DISABLE_USER", "root")
        self.assertEqual(
            [
                mock.call(set(keys), user),
                mock.call(set(keys), "root", options=options),
            ],
            m_setup_keys.call_args_list,
        )

    def test_apply_credentials_with_no_user_disable_root(self, m_setup_keys):
        """Apply keys no user and disable root ssh."""
        keys = ["key1"]
        user = None
        options = ssh_util.DISABLE_USER_OPTS
        cc_ssh.apply_credentials(keys, user, True, options)
        options = options.replace("$USER", "NONE")
        options = options.replace("$DISABLE_USER", "root")
        self.assertEqual(
            [mock.call(set(keys), "root", options=options)],
            m_setup_keys.call_args_list,
        )

    @mock.patch(MODPATH + "glob.glob")
    @mock.patch(MODPATH + "ug_util.normalize_users_groups")
    @mock.patch(MODPATH + "os.path.exists")
    def test_handle_no_cfg(self, m_path_exists, m_nug, m_glob, m_setup_keys):
        """Test handle with no config ignores generating existing keyfiles."""
        cfg = {}
        keys = ["key1"]
        m_glob.return_value = []  # Return no matching keys to prevent removal
        # Mock os.path.exits to True to short-circuit the key writing logic
        m_path_exists.return_value = True
        m_nug.return_value = ([], {})
        cc_ssh.PUBLISH_HOST_KEYS = False
        cloud = self.tmp_cloud(distro="ubuntu", metadata={"public-keys": keys})
        cc_ssh.handle("name", cfg, cloud, LOG, None)
        options = ssh_util.DISABLE_USER_OPTS.replace("$USER", "NONE")
        options = options.replace("$DISABLE_USER", "root")
        m_glob.assert_called_once_with("/etc/ssh/ssh_host_*key*")
        self.assertIn(
            [
                mock.call("/etc/ssh/ssh_host_rsa_key"),
                mock.call("/etc/ssh/ssh_host_dsa_key"),
                mock.call("/etc/ssh/ssh_host_ecdsa_key"),
                mock.call("/etc/ssh/ssh_host_ed25519_key"),
            ],
            m_path_exists.call_args_list,
        )
        self.assertEqual(
            [mock.call(set(keys), "root", options=options)],
            m_setup_keys.call_args_list,
        )

    @mock.patch(MODPATH + "glob.glob")
    @mock.patch(MODPATH + "ug_util.normalize_users_groups")
    @mock.patch(MODPATH + "os.path.exists")
    def test_dont_allow_public_ssh_keys(
        self, m_path_exists, m_nug, m_glob, m_setup_keys
    ):
        """Test allow_public_ssh_keys=False ignores ssh public keys from
        platform.
        """
        cfg = {"allow_public_ssh_keys": False}
        keys = ["key1"]
        user = "clouduser"
        m_glob.return_value = []  # Return no matching keys to prevent removal
        # Mock os.path.exits to True to short-circuit the key writing logic
        m_path_exists.return_value = True
        m_nug.return_value = ({user: {"default": user}}, {})
        cloud = self.tmp_cloud(distro="ubuntu", metadata={"public-keys": keys})
        cc_ssh.handle("name", cfg, cloud, LOG, None)

        options = ssh_util.DISABLE_USER_OPTS.replace("$USER", user)
        options = options.replace("$DISABLE_USER", "root")
        self.assertEqual(
            [
                mock.call(set(), user),
                mock.call(set(), "root", options=options),
            ],
            m_setup_keys.call_args_list,
        )

    @mock.patch(MODPATH + "glob.glob")
    @mock.patch(MODPATH + "ug_util.normalize_users_groups")
    @mock.patch(MODPATH + "os.path.exists")
    def test_handle_no_cfg_and_default_root(
        self, m_path_exists, m_nug, m_glob, m_setup_keys
    ):
        """Test handle with no config and a default distro user."""
        cfg = {}
        keys = ["key1"]
        user = "clouduser"
        m_glob.return_value = []  # Return no matching keys to prevent removal
        # Mock os.path.exits to True to short-circuit the key writing logic
        m_path_exists.return_value = True
        m_nug.return_value = ({user: {"default": user}}, {})
        cloud = self.tmp_cloud(distro="ubuntu", metadata={"public-keys": keys})
        cc_ssh.handle("name", cfg, cloud, LOG, None)

        options = ssh_util.DISABLE_USER_OPTS.replace("$USER", user)
        options = options.replace("$DISABLE_USER", "root")
        self.assertEqual(
            [
                mock.call(set(keys), user),
                mock.call(set(keys), "root", options=options),
            ],
            m_setup_keys.call_args_list,
        )

    @mock.patch(MODPATH + "glob.glob")
    @mock.patch(MODPATH + "ug_util.normalize_users_groups")
    @mock.patch(MODPATH + "os.path.exists")
    def test_handle_cfg_with_explicit_disable_root(
        self, m_path_exists, m_nug, m_glob, m_setup_keys
    ):
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
        cloud = self.tmp_cloud(distro="ubuntu", metadata={"public-keys": keys})
        cc_ssh.handle("name", cfg, cloud, LOG, None)

        options = ssh_util.DISABLE_USER_OPTS.replace("$USER", user)
        options = options.replace("$DISABLE_USER", "root")
        self.assertEqual(
            [
                mock.call(set(keys), user),
                mock.call(set(keys), "root", options=options),
            ],
            m_setup_keys.call_args_list,
        )

    @mock.patch(MODPATH + "glob.glob")
    @mock.patch(MODPATH + "ug_util.normalize_users_groups")
    @mock.patch(MODPATH + "os.path.exists")
    def test_handle_cfg_without_disable_root(
        self, m_path_exists, m_nug, m_glob, m_setup_keys
    ):
        """Test handle with disable_root == False."""
        # When disable_root == False, the ssh redirect for root is skipped
        cfg = {"disable_root": False}
        keys = ["key1"]
        user = "clouduser"
        m_glob.return_value = []  # Return no matching keys to prevent removal
        # Mock os.path.exits to True to short-circuit the key writing logic
        m_path_exists.return_value = True
        m_nug.return_value = ({user: {"default": user}}, {})
        cloud = self.tmp_cloud(distro="ubuntu", metadata={"public-keys": keys})
        cloud.get_public_ssh_keys = mock.Mock(return_value=keys)
        cc_ssh.handle("name", cfg, cloud, LOG, None)

        self.assertEqual(
            [
                mock.call(set(keys), user),
                mock.call(set(keys), "root", options=""),
            ],
            m_setup_keys.call_args_list,
        )

    @mock.patch(MODPATH + "glob.glob")
    @mock.patch(MODPATH + "ug_util.normalize_users_groups")
    @mock.patch(MODPATH + "os.path.exists")
    def test_handle_publish_hostkeys_default(
        self, m_path_exists, m_nug, m_glob, m_setup_keys
    ):
        """Test handle with various configs for ssh_publish_hostkeys."""
        self._publish_hostkey_test_setup()
        cc_ssh.PUBLISH_HOST_KEYS = True
        keys = ["key1"]
        user = "clouduser"
        # Return no matching keys for first glob, test keys for second.
        m_glob.side_effect = iter(
            [
                [],
                self.test_hostkey_files,
            ]
        )
        # Mock os.path.exits to True to short-circuit the key writing logic
        m_path_exists.return_value = True
        m_nug.return_value = ({user: {"default": user}}, {})
        cloud = self.tmp_cloud(distro="ubuntu", metadata={"public-keys": keys})
        cloud.datasource.publish_host_keys = mock.Mock()

        cfg = {}
        expected_call = [
            self.test_hostkeys[key_type] for key_type in KEY_NAMES_NO_DSA
        ]
        cc_ssh.handle("name", cfg, cloud, LOG, None)
        self.assertEqual(
            [mock.call(expected_call)],
            cloud.datasource.publish_host_keys.call_args_list,
        )

    @mock.patch(MODPATH + "glob.glob")
    @mock.patch(MODPATH + "ug_util.normalize_users_groups")
    @mock.patch(MODPATH + "os.path.exists")
    def test_handle_publish_hostkeys_config_enable(
        self, m_path_exists, m_nug, m_glob, m_setup_keys
    ):
        """Test handle with various configs for ssh_publish_hostkeys."""
        self._publish_hostkey_test_setup()
        cc_ssh.PUBLISH_HOST_KEYS = False
        keys = ["key1"]
        user = "clouduser"
        # Return no matching keys for first glob, test keys for second.
        m_glob.side_effect = iter(
            [
                [],
                self.test_hostkey_files,
            ]
        )
        # Mock os.path.exits to True to short-circuit the key writing logic
        m_path_exists.return_value = True
        m_nug.return_value = ({user: {"default": user}}, {})
        cloud = self.tmp_cloud(distro="ubuntu", metadata={"public-keys": keys})
        cloud.datasource.publish_host_keys = mock.Mock()

        cfg = {"ssh_publish_hostkeys": {"enabled": True}}
        expected_call = [
            self.test_hostkeys[key_type] for key_type in KEY_NAMES_NO_DSA
        ]
        cc_ssh.handle("name", cfg, cloud, LOG, None)
        self.assertEqual(
            [mock.call(expected_call)],
            cloud.datasource.publish_host_keys.call_args_list,
        )

    @mock.patch(MODPATH + "glob.glob")
    @mock.patch(MODPATH + "ug_util.normalize_users_groups")
    @mock.patch(MODPATH + "os.path.exists")
    def test_handle_publish_hostkeys_config_disable(
        self, m_path_exists, m_nug, m_glob, m_setup_keys
    ):
        """Test handle with various configs for ssh_publish_hostkeys."""
        self._publish_hostkey_test_setup()
        cc_ssh.PUBLISH_HOST_KEYS = True
        keys = ["key1"]
        user = "clouduser"
        # Return no matching keys for first glob, test keys for second.
        m_glob.side_effect = iter(
            [
                [],
                self.test_hostkey_files,
            ]
        )
        # Mock os.path.exits to True to short-circuit the key writing logic
        m_path_exists.return_value = True
        m_nug.return_value = ({user: {"default": user}}, {})
        cloud = self.tmp_cloud(distro="ubuntu", metadata={"public-keys": keys})
        cloud.datasource.publish_host_keys = mock.Mock()

        cfg = {"ssh_publish_hostkeys": {"enabled": False}}
        cc_ssh.handle("name", cfg, cloud, LOG, None)
        self.assertFalse(cloud.datasource.publish_host_keys.call_args_list)
        cloud.datasource.publish_host_keys.assert_not_called()

    @mock.patch(MODPATH + "glob.glob")
    @mock.patch(MODPATH + "ug_util.normalize_users_groups")
    @mock.patch(MODPATH + "os.path.exists")
    def test_handle_publish_hostkeys_config_blacklist(
        self, m_path_exists, m_nug, m_glob, m_setup_keys
    ):
        """Test handle with various configs for ssh_publish_hostkeys."""
        self._publish_hostkey_test_setup()
        cc_ssh.PUBLISH_HOST_KEYS = True
        keys = ["key1"]
        user = "clouduser"
        # Return no matching keys for first glob, test keys for second.
        m_glob.side_effect = iter(
            [
                [],
                self.test_hostkey_files,
            ]
        )
        # Mock os.path.exits to True to short-circuit the key writing logic
        m_path_exists.return_value = True
        m_nug.return_value = ({user: {"default": user}}, {})
        cloud = self.tmp_cloud(distro="ubuntu", metadata={"public-keys": keys})
        cloud.datasource.publish_host_keys = mock.Mock()

        cfg = {
            "ssh_publish_hostkeys": {
                "enabled": True,
                "blacklist": ["dsa", "rsa"],
            }
        }
        expected_call = [
            self.test_hostkeys[key_type] for key_type in ["ecdsa", "ed25519"]
        ]
        cc_ssh.handle("name", cfg, cloud, LOG, None)
        self.assertEqual(
            [mock.call(expected_call)],
            cloud.datasource.publish_host_keys.call_args_list,
        )

    @mock.patch(MODPATH + "glob.glob")
    @mock.patch(MODPATH + "ug_util.normalize_users_groups")
    @mock.patch(MODPATH + "os.path.exists")
    def test_handle_publish_hostkeys_empty_blacklist(
        self, m_path_exists, m_nug, m_glob, m_setup_keys
    ):
        """Test handle with various configs for ssh_publish_hostkeys."""
        self._publish_hostkey_test_setup()
        cc_ssh.PUBLISH_HOST_KEYS = True
        keys = ["key1"]
        user = "clouduser"
        # Return no matching keys for first glob, test keys for second.
        m_glob.side_effect = iter(
            [
                [],
                self.test_hostkey_files,
            ]
        )
        # Mock os.path.exits to True to short-circuit the key writing logic
        m_path_exists.return_value = True
        m_nug.return_value = ({user: {"default": user}}, {})
        cloud = self.tmp_cloud(distro="ubuntu", metadata={"public-keys": keys})
        cloud.datasource.publish_host_keys = mock.Mock()

        cfg = {"ssh_publish_hostkeys": {"enabled": True, "blacklist": []}}
        expected_call = [
            self.test_hostkeys[key_type]
            for key_type in cc_ssh.GENERATE_KEY_NAMES
        ]
        cc_ssh.handle("name", cfg, cloud, LOG, None)
        self.assertEqual(
            [mock.call(expected_call)],
            cloud.datasource.publish_host_keys.call_args_list,
        )

    @mock.patch(MODPATH + "ug_util.normalize_users_groups")
    @mock.patch(MODPATH + "util.write_file")
    def test_handle_ssh_keys_in_cfg(self, m_write_file, m_nug, m_setup_keys):
        """Test handle with ssh keys and certificate."""
        # Populate a config dictionary to pass to handle() as well
        # as the expected file-writing calls.
        cfg = {"ssh_keys": {}}

        expected_calls = []
        for key_type in cc_ssh.GENERATE_KEY_NAMES:
            private_name = "{}_private".format(key_type)
            public_name = "{}_public".format(key_type)
            cert_name = "{}_certificate".format(key_type)

            # Actual key contents don"t have to be realistic
            private_value = "{}_PRIVATE_KEY".format(key_type)
            public_value = "{}_PUBLIC_KEY".format(key_type)
            cert_value = "{}_CERT_KEY".format(key_type)

            cfg["ssh_keys"][private_name] = private_value
            cfg["ssh_keys"][public_name] = public_value
            cfg["ssh_keys"][cert_name] = cert_value

            expected_calls.extend(
                [
                    mock.call(
                        "/etc/ssh/ssh_host_{}_key".format(key_type),
                        private_value,
                        384,
                    ),
                    mock.call(
                        "/etc/ssh/ssh_host_{}_key.pub".format(key_type),
                        public_value,
                        384,
                    ),
                    mock.call(
                        "/etc/ssh/ssh_host_{}_key-cert.pub".format(key_type),
                        cert_value,
                        384,
                    ),
                    mock.call(
                        "/etc/ssh/sshd_config",
                        "HostCertificate /etc/ssh/ssh_host_{}_key-cert.pub"
                        "\n".format(key_type),
                        preserve_mode=True,
                    ),
                ]
            )

        # Run the handler.
        m_nug.return_value = ([], {})
        with mock.patch(
            MODPATH + "ssh_util.parse_ssh_config", return_value=[]
        ):
            cc_ssh.handle(
                "name", cfg, self.tmp_cloud(distro="ubuntu"), LOG, None
            )

        # Check that all expected output has been done.
        for call_ in expected_calls:
            self.assertIn(call_, m_write_file.call_args_list)
