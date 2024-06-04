# This file is part of cloud-init. See LICENSE file for license information.

import logging
import os.path
from typing import Optional
from unittest import mock

import pytest

from cloudinit import ssh_util, util
from cloudinit.config import cc_ssh
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import skipUnlessJsonSchema
from tests.unittests.util import get_cloud

LOG = logging.getLogger(__name__)

MODPATH = "cloudinit.config.cc_ssh."


@pytest.fixture(scope="function")
def publish_hostkey_test_setup(tmpdir):
    test_hostkeys = {
        "ecdsa": ("ecdsa-sha2-nistp256", "AAAAE2VjZ"),
        "ed25519": ("ssh-ed25519", "AAAAC3NzaC1lZDI"),
        "rsa": ("ssh-rsa", "AAAAB3NzaC1yc2EAAA"),
    }
    test_hostkey_files = []
    hostkey_tmpdir = tmpdir
    for key_type in cc_ssh.GENERATE_KEY_NAMES:
        filename = "ssh_host_%s_key.pub" % key_type
        filepath = os.path.join(hostkey_tmpdir, filename)
        test_hostkey_files.append(filepath)
        with open(filepath, "w") as f:
            f.write(" ".join(test_hostkeys[key_type]))

    with mock.patch.object(
        cc_ssh, "KEY_FILE_TPL", os.path.join(hostkey_tmpdir, "ssh_host_%s_key")
    ):
        yield test_hostkeys, test_hostkey_files


def _replace_options(user: Optional[str] = None) -> str:
    options = ssh_util.DISABLE_USER_OPTS
    if user:
        new_user = user
    else:
        new_user = "NONE"
    options = options.replace("$USER", new_user)
    options = options.replace("$DISABLE_USER", "root")
    return options


@pytest.mark.usefixtures("fake_filesystem")
@mock.patch(MODPATH + "ssh_util.setup_user_keys")
class TestHandleSsh:
    """Test cc_ssh handling of ssh config."""

    @pytest.mark.parametrize(
        "keys,user,disable_root_opts",
        [
            # For the given user and root.
            pytest.param(["key1"], "clouduser", False, id="with_user"),
            # For root only.
            pytest.param(["key1"], None, False, id="with_no_user"),
            # For the given user and disable root ssh.
            pytest.param(
                ["key1"],
                "clouduser",
                True,
                id="with_user_disable_root",
            ),
            # No user and disable root ssh.
            pytest.param(
                ["key1"],
                None,
                True,
                id="with_no_user_disable_root",
            ),
        ],
    )
    def test_apply_credentials(
        self, m_setup_keys, keys, user, disable_root_opts
    ):
        options = ssh_util.DISABLE_USER_OPTS
        cc_ssh.apply_credentials(keys, user, disable_root_opts, options)
        if not disable_root_opts:
            expected_options = ""
        else:
            expected_options = _replace_options(user)
        expected_calls = [
            mock.call(set(keys), "root", options=expected_options)
        ]
        if user:
            expected_calls = [mock.call(set(keys), user)] + expected_calls
        assert expected_calls == m_setup_keys.call_args_list

    @pytest.mark.parametrize("fips_enabled", (True, False))
    @mock.patch(MODPATH + "glob.glob")
    @mock.patch(MODPATH + "ug_util.normalize_users_groups")
    @mock.patch(MODPATH + "os.path.exists")
    @mock.patch(MODPATH + "util.fips_enabled")
    def test_handle_no_cfg(
        self, m_fips, m_path_exists, m_nug, m_glob, m_setup_keys, fips_enabled
    ):
        """Test handle with no config ignores generating existing keyfiles."""
        m_fips.return_value = fips_enabled
        cfg = {}
        keys = ["key1"]
        m_glob.return_value = []  # Return no matching keys to prevent removal
        # Mock os.path.exits to True to short-circuit the key writing logic
        m_path_exists.return_value = True
        m_nug.return_value = ([], {})
        cc_ssh.PUBLISH_HOST_KEYS = False
        cloud = get_cloud(distro="ubuntu", metadata={"public-keys": keys})
        cc_ssh.handle("name", cfg, cloud, None)
        options = ssh_util.DISABLE_USER_OPTS.replace("$USER", "NONE")
        options = options.replace("$DISABLE_USER", "root")
        m_glob.assert_called_once_with("/etc/ssh/ssh_host_*key*")
        m_fips.assert_called_once()

        if not m_fips():
            expected_calls = [
                mock.call("/etc/ssh/ssh_host_rsa_key"),
                mock.call("/etc/ssh/ssh_host_ecdsa_key"),
                mock.call("/etc/ssh/ssh_host_ed25519_key"),
            ]
        else:
            # Enabled fips doesn't generate ed25519
            expected_calls = [
                mock.call("/etc/ssh/ssh_host_rsa_key"),
                mock.call("/etc/ssh/ssh_host_ecdsa_key"),
            ]
        assert expected_calls in m_path_exists.call_args_list
        assert [
            mock.call(set(keys), "root", options=options)
        ] == m_setup_keys.call_args_list

    @mock.patch(MODPATH + "glob.glob")
    @mock.patch(MODPATH + "ug_util.normalize_users_groups")
    @mock.patch(MODPATH + "os.path.exists")
    @mock.patch(MODPATH + "util.fips_enabled", return_value=False)
    def test_dont_allow_public_ssh_keys(
        self, m_fips, m_path_exists, m_nug, m_glob, m_setup_keys
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
        cloud = get_cloud(distro="ubuntu", metadata={"public-keys": keys})
        cc_ssh.handle("name", cfg, cloud, None)

        options = ssh_util.DISABLE_USER_OPTS.replace("$USER", user)
        options = options.replace("$DISABLE_USER", "root")
        assert [
            mock.call(set(), user),
            mock.call(set(), "root", options=options),
        ] == m_setup_keys.call_args_list

    @pytest.mark.parametrize(
        "cfg,mock_get_public_ssh_keys,empty_opts",
        [
            pytest.param({}, False, False, id="no_cfg"),
            pytest.param(
                {"disable_root": True},
                False,
                False,
                id="explicit_disable_root",
            ),
            # When disable_root == False, the ssh redirect for root is skipped
            pytest.param(
                {"disable_root": False},
                True,
                True,
                id="cfg_without_disable_root",
            ),
        ],
    )
    @mock.patch(MODPATH + "glob.glob")
    @mock.patch(MODPATH + "ug_util.normalize_users_groups")
    @mock.patch(MODPATH + "os.path.exists")
    @mock.patch(MODPATH + "util.fips_enabled", return_value=False)
    def test_handle_default_root(
        self,
        m_fips,
        m_path_exists,
        m_nug,
        m_glob,
        m_setup_keys,
        cfg,
        mock_get_public_ssh_keys,
        empty_opts,
    ):
        """Test handle with a default distro user."""
        keys = ["key1"]
        user = "clouduser"
        m_glob.return_value = []  # Return no matching keys to prevent removal
        # Mock os.path.exits to True to short-circuit the key writing logic
        m_path_exists.return_value = True
        m_nug.return_value = ({user: {"default": user}}, {})
        cloud = get_cloud(distro="ubuntu", metadata={"public-keys": keys})
        if mock_get_public_ssh_keys:
            cloud.get_public_ssh_keys = mock.Mock(return_value=keys)
        cc_ssh.handle("name", cfg, cloud, None)

        if empty_opts:
            options = ""
        else:
            options = _replace_options(user)
        assert [
            mock.call(set(keys), user),
            mock.call(set(keys), "root", options=options),
        ] == m_setup_keys.call_args_list

    @pytest.mark.parametrize(
        "cfg, expected_key_types",
        [
            pytest.param({}, cc_ssh.GENERATE_KEY_NAMES, id="default"),
            pytest.param(
                {"ssh_publish_hostkeys": {"enabled": True}},
                cc_ssh.GENERATE_KEY_NAMES,
                id="config_enable",
            ),
            pytest.param(
                {"ssh_publish_hostkeys": {"enabled": False}},
                None,
                id="config_disable",
            ),
            pytest.param(
                {
                    "ssh_publish_hostkeys": {
                        "enabled": True,
                        "blacklist": ["dsa", "rsa"],
                    }
                },
                ["ecdsa", "ed25519"],
                id="config_blacklist",
            ),
            pytest.param(
                {"ssh_publish_hostkeys": {"enabled": True, "blacklist": []}},
                cc_ssh.GENERATE_KEY_NAMES,
                id="empty_blacklist",
            ),
        ],
    )
    @mock.patch(MODPATH + "glob.glob")
    @mock.patch(MODPATH + "ug_util.normalize_users_groups")
    @mock.patch(MODPATH + "os.path.exists")
    @mock.patch(MODPATH + "util.fips_enabled", return_value=False)
    @mock.patch.object(cc_ssh, "PUBLISH_HOST_KEYS", True)
    def test_handle_publish_hostkeys(
        self,
        m_fips,
        m_path_exists,
        m_nug,
        m_glob,
        m_setup_keys,
        publish_hostkey_test_setup,
        cfg,
        expected_key_types,
    ):
        """Test handle with various configs for ssh_publish_hostkeys."""
        test_hostkeys, test_hostkey_files = publish_hostkey_test_setup
        keys = ["key1"]
        user = "clouduser"
        # Return no matching keys for first glob, test keys for second.
        m_glob.side_effect = iter(
            [
                [],
                test_hostkey_files,
            ]
        )
        # Mock os.path.exits to True to short-circuit the key writing logic
        m_path_exists.return_value = True
        m_nug.return_value = ({user: {"default": user}}, {})
        cloud = get_cloud(distro="ubuntu", metadata={"public-keys": keys})

        expected_calls = []
        if expected_key_types is not None:
            expected_calls = [
                mock.call(
                    [
                        test_hostkeys[key_type]
                        for key_type in expected_key_types
                    ]
                )
            ]

        with mock.patch.object(
            cloud.datasource, "publish_host_keys", mock.Mock()
        ):
            cc_ssh.handle("name", cfg, cloud, None)
            assert (
                expected_calls
                == cloud.datasource.publish_host_keys.call_args_list
            )

    @pytest.mark.parametrize(
        "ssh_keys_group_exists,sshd_version,expected_private_permissions",
        [(False, 9, 0o600), (True, 8, 0o640), (True, 10, 0o600)],
    )
    @mock.patch(MODPATH + "subp.subp", return_value=("", ""))
    @mock.patch(MODPATH + "util.get_group_id", return_value=10)
    @mock.patch(MODPATH + "ssh_util.get_opensshd_upstream_version")
    @mock.patch(MODPATH + "os.path.exists", return_value=False)
    @mock.patch(MODPATH + "os.chown")
    @mock.patch(MODPATH + "os.chmod")
    def test_ssh_hostkey_permissions(
        self,
        m_chmod,
        m_chown,
        m_exists,
        m_sshd_version,
        m_gid,
        m_subp,
        m_setup_keys,
        ssh_keys_group_exists,
        sshd_version,
        expected_private_permissions,
    ):
        """Test our generated hostkeys use same perms as sshd-keygen.

        SSHD version < 9.0 should apply 640 permissions to the private key.
        Otherwise, 600.
        """
        m_gid.return_value = 10 if ssh_keys_group_exists else -1
        m_sshd_version.return_value = util.Version(sshd_version, 0)
        key_path = cc_ssh.KEY_FILE_TPL % "rsa"
        cloud = get_cloud(distro="centos")
        cc_ssh.handle("name", {"ssh_genkeytypes": ["rsa"]}, cloud, [])
        if ssh_keys_group_exists:
            m_chown.assert_called_once_with(key_path, -1, 10)
        else:
            m_chown.assert_not_called()

        assert m_chmod.call_args_list == [
            mock.call(key_path, expected_private_permissions),
            mock.call(f"{key_path}.pub", 0o644),
        ]

    @pytest.mark.parametrize("with_sshd_dconf", [False, True])
    @mock.patch(MODPATH + "util.ensure_dir")
    @mock.patch(MODPATH + "ug_util.normalize_users_groups")
    @mock.patch(MODPATH + "util.write_file")
    def test_handle_ssh_keys_in_cfg(
        self,
        m_write_file,
        m_nug,
        m_ensure_dir,
        m_setup_keys,
        with_sshd_dconf,
        mocker,
    ):
        """Test handle with ssh keys and certificate."""
        # Populate a config dictionary to pass to handle() as well
        # as the expected file-writing calls.
        mocker.patch(
            MODPATH + "ssh_util._includes_dconf", return_value=with_sshd_dconf
        )
        if with_sshd_dconf:
            sshd_conf_fname = "/etc/ssh/sshd_config.d/50-cloud-init.conf"
        else:
            sshd_conf_fname = "/etc/ssh/sshd_config"

        cfg = {"ssh_keys": {}}

        expected_calls = []
        cert_content = ""
        for key_type in cc_ssh.GENERATE_KEY_NAMES:
            private_name = "{}_private".format(key_type)
            public_name = "{}_public".format(key_type)
            cert_name = "{}_certificate".format(key_type)

            # Actual key contents don't have to be realistic
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
                        0o600,
                    ),
                    mock.call(
                        "/etc/ssh/ssh_host_{}_key.pub".format(key_type),
                        public_value,
                        0o644,
                    ),
                    mock.call(
                        "/etc/ssh/ssh_host_{}_key-cert.pub".format(key_type),
                        cert_value,
                        0o644,
                    ),
                ]
            )
            cert_content += (
                f"HostCertificate /etc/ssh/ssh_host_{key_type}_key-cert.pub\n"
            )

        expected_calls.append(
            mock.call(
                sshd_conf_fname,
                cert_content,
                omode="ab",
                preserve_mode=True,
            )
        )

        # Run the handler.
        m_nug.return_value = ([], {})
        with mock.patch(
            MODPATH + "ssh_util.parse_ssh_config", return_value=[]
        ):
            cc_ssh.handle("name", cfg, get_cloud(distro="ubuntu"), None)

        # Check that all expected output has been done.
        for call_ in expected_calls:
            assert call_ in m_write_file.call_args_list

        if with_sshd_dconf:
            assert (
                mock.call("/etc/ssh/sshd_config.d", mode=0o755)
                in m_ensure_dir.call_args_list
            )
        else:
            assert [] == m_ensure_dir.call_args_list

    @pytest.mark.parametrize(
        "key_type,reason",
        [
            ("ecdsa-sk", "unsupported"),
            ("ed25519-sk", "unsupported"),
            ("public", "unrecognized"),
        ],
    )
    @mock.patch(MODPATH + "ug_util.normalize_users_groups")
    @mock.patch(MODPATH + "util.write_file")
    def test_handle_invalid_ssh_keys_are_skipped(
        self,
        m_write_file,
        m_nug,
        m_setup_keys,
        key_type,
        reason,
        caplog,
    ):
        cfg = {
            "ssh_keys": {
                f"{key_type}_private": f"{key_type}_private",
                f"{key_type}_public": f"{key_type}_public",
                f"{key_type}_certificate": f"{key_type}_certificate",
            },
            "ssh_deletekeys": False,
            "ssh_publish_hostkeys": {"enabled": False},
        }
        # Run the handler.
        m_nug.return_value = ([], {})
        with mock.patch(
            MODPATH + "ssh_util.parse_ssh_config", return_value=[]
        ):
            cc_ssh.handle("name", cfg, get_cloud("ubuntu"), None)
        assert [] == m_write_file.call_args_list
        expected_log_msgs = [
            f'Skipping {reason} ssh_keys entry: "{key_type}_private"',
            f'Skipping {reason} ssh_keys entry: "{key_type}_public"',
            f'Skipping {reason} ssh_keys entry: "{key_type}_certificate"',
        ]
        for expected_log_msg in expected_log_msgs:
            assert caplog.text.count(expected_log_msg) == 1


class TestSshSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        (
            ({"ssh_authorized_keys": ["key1", "key2"]}, None),
            (
                {"ssh_keys": {"rsa_a": "key"}},
                "'rsa_a' does not match any of the regexes",
            ),
            (
                {"ssh_keys": {"a_public": "key"}},
                "'a_public' does not match any of the regexes",
            ),
            (
                {"ssh_keys": {"ecdsa-sk_public": "key"}},
                "'ecdsa-sk_public' does not match any of the regexes",
            ),
            (
                {"ssh_keys": {"ed25519-sk_public": "key"}},
                "'ed25519-sk_public' does not match any of the regexes",
            ),
            (
                {"ssh_authorized_keys": "ssh-rsa blah"},
                "'ssh-rsa blah' is not of type 'array'",
            ),
            ({"ssh_genkeytypes": ["bad"]}, "'bad' is not one of"),
            (
                {"disable_root_opts": ["no-port-forwarding"]},
                r"\['no-port-forwarding'\] is not of type 'string'",
            ),
            (
                {"ssh_publish_hostkeys": {"key": "value"}},
                "Additional properties are not allowed",
            ),
        ),
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        if error_msg is None:
            validate_cloudconfig_schema(config, get_schema(), strict=True)
        else:
            with pytest.raises(SchemaValidationError, match=error_msg):
                validate_cloudconfig_schema(config, get_schema(), strict=True)
