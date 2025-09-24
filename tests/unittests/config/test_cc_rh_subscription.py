# This file is part of cloud-init. See LICENSE file for license information.

"""Tests for registering RHEL subscription via rh_subscription."""

import copy
import logging

import pytest

from cloudinit import subp
from cloudinit.config import cc_rh_subscription
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import (
    mock,
    skipUnlessJsonSchema,
    skipUnlessJsonSchemaVersionGreaterThan,
)

SUBMGR = cc_rh_subscription.SubscriptionManager
SUB_MAN_CLI = "cloudinit.config.cc_rh_subscription._sub_man_cli"
NAME = "cc_rh_subscription"


@mock.patch(SUB_MAN_CLI)
class TestHappyPath:

    CONFIG = {
        "rh_subscription": {
            "username": "scooby@do.com",
            "password": "scooby-snacks",
        }
    }

    CONFIG_FULL = {
        "rh_subscription": {
            "username": "scooby@do.com",
            "password": "scooby-snacks",
            "auto_attach": True,
            "service_level": "self-support",
            "add_pool": ["pool1", "pool2", "pool3"],
            "enable_repo": ["repo1", "repo2", "repo3"],
            "disable_repo": ["repo4", "repo5"],
            "release_version": "7.6b",
        }
    }

    def test_already_registered(self, m_sman_cli, caplog):
        """
        Emulates a system that is already registered. Ensure it gets
        a non-ProcessExecution error from is_registered()
        """
        cc_rh_subscription.handle(NAME, self.CONFIG, None, [])
        assert m_sman_cli.call_count == 1
        assert "System is already registered" in caplog.text

    @mock.patch.object(
        cc_rh_subscription.SubscriptionManager, "_set_release_version"
    )
    def test_simple_registration(
        self, m_set_release_version, m_sman_cli, caplog
    ):
        """
        Simple registration with username and password
        """
        reg = (
            "The system has been registered with ID:"
            " 12345678-abde-abcde-1234-1234567890abc"
        )
        m_sman_cli.side_effect = [subp.ProcessExecutionError, (reg, "bar")]
        cc_rh_subscription.handle(NAME, self.CONFIG, None, [])
        assert mock.call(["identity"]) in m_sman_cli.call_args_list
        assert (
            mock.call(
                [
                    "register",
                    "--username=scooby@do.com",
                    "--password=scooby-snacks",
                ],
                logstring_val=True,
            )
            in m_sman_cli.call_args_list
        )
        assert "rh_subscription plugin completed successfully" in caplog.text
        assert m_sman_cli.call_count == 2
        assert m_set_release_version.call_count == 0

    @pytest.mark.parametrize(
        "variable_name_separator",
        (
            pytest.param("_", id="update_repos_disable_with_none"),
            pytest.param(
                "-", id="same_functional_behavior_with_deprecated_keys"
            ),
        ),
    )
    @mock.patch.object(cc_rh_subscription.SubscriptionManager, "_getRepos")
    def test_update_repos_disable_with_none(
        self, m_get_repos, m_sman_cli, variable_name_separator
    ):
        cfg = copy.deepcopy(self.CONFIG)
        m_get_repos.return_value = ([], ["repo1"])

        enable_repo_key = "enable_repo".replace("_", variable_name_separator)
        disable_repo_key = "disable_repo".replace("_", variable_name_separator)
        cfg["rh_subscription"].update(
            {enable_repo_key: ["repo1"], disable_repo_key: None}
        )
        mysm = cc_rh_subscription.SubscriptionManager(cfg)
        assert True is mysm.update_repos()
        m_get_repos.assert_called_with()
        assert m_sman_cli.call_args_list == [
            mock.call(["repos", "--enable=repo1"])
        ]

    def test_full_registration(self, m_sman_cli, caplog):
        """
        Registration with auto_attach, service_level, adding pools,
        enabling and disabling yum repos and setting release_version
        """
        call_lists = []
        call_lists.append(["attach", "--pool=pool1", "--pool=pool3"])
        call_lists.append(
            ["repos", "--disable=repo5", "--enable=repo2", "--enable=repo3"]
        )
        call_lists.append(["attach", "--auto", "--servicelevel=self-support"])
        call_lists.append(["release", "--set=7.6b"])
        reg = (
            "The system has been registered with ID:"
            " 12345678-abde-abcde-1234-1234567890abc"
        )
        m_sman_cli.side_effect = [
            subp.ProcessExecutionError,
            (reg, "bar"),
            ("Service level set to: self-support", ""),
            ("pool1\npool3\n", ""),
            ("pool2\n", ""),
            ("", ""),
            ("Repo ID: repo1\nRepo ID: repo5\n", ""),
            ("Repo ID: repo2\nRepo ID: repo3\nRepo ID: repo4", ""),
            ("", ""),
            ("Release set to: 7.6b", ""),
        ]
        # to avoid deleting the actual cache files
        # (triggered by the presence of the release_version key)
        # on the host running the tests
        mock.patch("shutil.rmtree")

        cc_rh_subscription.handle(NAME, self.CONFIG_FULL, None, [])
        assert m_sman_cli.call_count == 10
        for call in call_lists:
            assert mock.call(call) in m_sman_cli.call_args_list
        assert "rh_subscription plugin completed successfully" in caplog.text


@mock.patch(SUB_MAN_CLI)
class TestBadInput:
    SM = cc_rh_subscription.SubscriptionManager
    REG = (
        "The system has been registered with ID:"
        " 12345678-abde-abcde-1234-1234567890abc"
    )

    CONFIG_NO_PASSWORD = {"rh_subscription": {"username": "scooby@do.com"}}

    CONFIG_NO_KEY = {
        "rh_subscription": {
            "activation_key": "1234abcde",
        }
    }

    CONFIG_SERVICE = {
        "rh_subscription": {
            "username": "scooby@do.com",
            "password": "scooby-snacks",
            "service_level": "self-support",
        }
    }

    CONFIG_BADPOOL = {
        "rh_subscription": {
            "username": "scooby@do.com",
            "password": "scooby-snacks",
            "add_pool": "not_a_list",
        }
    }
    CONFIG_BADREPO = {
        "rh_subscription": {
            "username": "scooby@do.com",
            "password": "scooby-snacks",
            "enable_repo": "not_a_list",
        }
    }
    CONFIG_BAD_RELEASE_VERSION = {
        "rh_subscription": {
            "username": "scooby@do.com",
            "password": "scooby-snacks",
            "release_version": "bad_release_version",
        }
    }

    def assert_logged_warnings(self, warnings, caplog):
        missing = [
            w
            for w in warnings
            if (mock.ANY, logging.WARNING, w) not in caplog.record_tuples
        ]
        assert [] == missing, "Missing expected warnings."

    def test_no_password(self, m_sman_cli):
        """Attempt to register without the password key/value."""
        m_sman_cli.side_effect = [
            subp.ProcessExecutionError,
            (self.REG, "bar"),
        ]
        cc_rh_subscription.handle(NAME, self.CONFIG_NO_PASSWORD, None, [])
        assert m_sman_cli.call_count == 0

    def test_no_org(self, m_sman_cli, caplog):
        """Attempt to register without the org key/value."""
        m_sman_cli.side_effect = [subp.ProcessExecutionError]
        cc_rh_subscription.handle(NAME, self.CONFIG_NO_KEY, None, [])
        m_sman_cli.assert_called_with(["identity"])
        assert m_sman_cli.call_count == 1
        self.assert_logged_warnings(
            (
                "Unable to register system due to incomplete information.",
                "Use either activationkey and org *or* userid and password",
                "Registration failed or did not run completely",
                "rh_subscription plugin did not complete successfully",
            ),
            caplog,
        )

    def test_service_level_without_auto(self, m_sman_cli, caplog):
        """Attempt to register using service_level without auto_attach key."""
        m_sman_cli.side_effect = [
            subp.ProcessExecutionError,
            (self.REG, "bar"),
        ]
        cc_rh_subscription.handle(NAME, self.CONFIG_SERVICE, None, [])
        assert m_sman_cli.call_count == 1
        self.assert_logged_warnings(
            (
                "The service_level key must be used in conjunction with the"
                " auto_attach key.  Please re-run with auto_attach: True",
                "rh_subscription plugin did not complete successfully",
            ),
            caplog,
        )

    def test_pool_not_a_list(self, m_sman_cli, caplog):
        """
        Register with pools that are not in the format of a list
        """
        m_sman_cli.side_effect = [
            subp.ProcessExecutionError,
            (self.REG, "bar"),
        ]
        cc_rh_subscription.handle(NAME, self.CONFIG_BADPOOL, None, [])
        assert m_sman_cli.call_count == 2
        self.assert_logged_warnings(
            (
                "Pools must in the format of a list",
                "rh_subscription plugin did not complete successfully",
            ),
            caplog,
        )

    def test_repo_not_a_list(self, m_sman_cli, caplog):
        """
        Register with repos that are not in the format of a list
        """
        m_sman_cli.side_effect = [
            subp.ProcessExecutionError,
            (self.REG, "bar"),
        ]
        cc_rh_subscription.handle(NAME, self.CONFIG_BADREPO, None, [])
        assert m_sman_cli.call_count == 2
        self.assert_logged_warnings(
            (
                "Repo IDs must in the format of a list.",
                "Unable to add or remove repos",
                "rh_subscription plugin did not complete successfully",
            ),
            caplog,
        )

    @mock.patch.object(
        cc_rh_subscription.SubscriptionManager, "_delete_packagemanager_cache"
    )
    def test_bad_release_version(self, m_delete_pm_cache, m_sman_cli, caplog):
        """
        Failure at setting release_version
        """
        m_sman_cli.side_effect = [
            subp.ProcessExecutionError,
            (self.REG, "bar"),
            subp.ProcessExecutionError,
        ]
        cc_rh_subscription.handle(
            NAME, self.CONFIG_BAD_RELEASE_VERSION, None, []
        )
        assert m_sman_cli.call_count == 3
        assert m_delete_pm_cache.call_count == 0
        expected_cmd = [
            "release",
            f"--set={self.CONFIG_BAD_RELEASE_VERSION['rh_subscription']['release_version']}",
        ]
        self.assert_logged_warnings(
            (
                f"Unable to set release_version using: {expected_cmd}",
                "rh_subscription plugin did not complete successfully",
            ),
            caplog,
        )

    @mock.patch("shutil.rmtree", side_effect=[PermissionError])
    def test_pm_cache_deletion_after_setting_release_version(
        self, m_rmtree, m_sman_cli, caplog
    ):
        """
        Failure at deleting package manager cache
        after setting release_version
        """
        good_release_ver_cfg = copy.deepcopy(self.CONFIG_BAD_RELEASE_VERSION)
        good_release_ver_cfg["rh_subscription"][
            "release_version"
        ] = "1.2Server"
        m_sman_cli.side_effect = [
            subp.ProcessExecutionError,
            (self.REG, "bar"),
            ("Release set to: 1.2Server", ""),
        ]
        cc_rh_subscription.handle(NAME, good_release_ver_cfg, None, [])
        # assert "rh_subscription plugin completed successfully" in caplog.text
        assert m_sman_cli.call_count == 3
        assert m_rmtree.call_args_list == [mock.call("/var/cache/dnf")]
        self.assert_logged_warnings(
            (
                "Unable to delete the package manager cache",
                "rh_subscription plugin did not complete successfully",
            ),
            caplog,
        )


class TestRhSubscriptionSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        [
            (
                {"rh_subscription": {"bad": "input"}},
                "Additional properties are not allowed",
            ),
            (
                {"rh_subscription": {"add-pool": [1]}},
                "1 is not of type 'string'",
            ),
            (
                {"rh_subscription": {"add_pool": [1]}},
                "1 is not of type 'string'",
            ),
            (
                {"rh_subscription": {"add_pool": ["1"]}},
                None,
            ),
            # The json schema error message is not descriptive
            # but basically we need to confirm the schema will fail
            # the config validation when both add_pool and the deprecated
            # add-pool are added
            (
                {"rh_subscription": {"add_pool": ["1"], "add-pool": ["2"]}},
                r"({'add_pool': \['1'\], 'add-pool': \['2'\]} should not be"
                r" valid under {'required': \['add_pool', 'add-pool'\]}|"
                r"{'required': \['add_pool', 'add-pool'\]} is not allowed"
                r" for {'add_pool': \['1'\], 'add-pool': \['2'\]})",
            ),
            (
                {"rh_subscription": {"enable_repo": "name"}},
                "'name' is not of type 'array'",
            ),
            (
                {"rh_subscription": {"disable_repo": "name"}},
                "'name' is not of type 'array'",
            ),
            (
                {"rh_subscription": {"release_version": [10]}},
                r"\[10\] is not of type 'string'",
            ),
            (
                {
                    "rh_subscription": {
                        "activation_key": "foobar",
                        "org": "ABC",
                    }
                },
                None,
            ),
            (
                {"rh_subscription": {"activation_key": "foobar", "org": 314}},
                "Deprecated in version 24.2. Use of type integer for this"
                " value is deprecated. Use a string instead.",
            ),
        ],
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        self._validation_steps(config, error_msg)

    @pytest.mark.parametrize(
        "config, error_msg",
        [
            (
                {"rh_subscription": {"add-pool": ["1"]}},
                # The deprecation is not raised for jsonschema<4.0
                # as the latter can't merge $defs and inline keys
                r"Deprecated in version 25.3. Use \*\*add_pool\*\* instead.",
            ),
        ],
    )
    @skipUnlessJsonSchemaVersionGreaterThan(version=(3, 2, 0))
    def test_schema_validation_requiring_new_json_schema(
        self, config, error_msg
    ):
        self._validation_steps(config, error_msg)

    @staticmethod
    def _validation_steps(config, error_msg):
        if error_msg is None:
            validate_cloudconfig_schema(config, get_schema(), strict=True)
        else:
            with pytest.raises(SchemaValidationError, match=error_msg):
                validate_cloudconfig_schema(config, get_schema(), strict=True)


class TestConstructor:
    """
    Test Constructor operations
    """

    def test_deprecated_values(self):
        """
        Confirm the constructor assigns the deprecated fields' cfg keys to the
        correct python object fields
        """

        cfg_with_new_keys = {"rh_subscription": {}}
        cfg_with_deprecated_keys = {"rh_subscription": {}}

        deprecation_pairs = [
            ("activation-key", "activation_key"),
            ("disable-repo", "disable_repo"),
            ("enable-repo", "enable_repo"),
            ("add-pool", "add_pool"),
            ("rhsm-baseurl", "rhsm_baseurl"),
            ("server-hostname", "server_hostname"),
            ("auto-attach", "auto_attach"),
            ("service-level", "service_level"),
        ]

        counter = 0
        for tuple in deprecation_pairs:
            cfg_with_new_keys["rh_subscription"][tuple[0]] = counter
            cfg_with_deprecated_keys["rh_subscription"][tuple[1]] = counter
            counter = counter + 1

        mgr_with_new_keys = cc_rh_subscription.SubscriptionManager(
            cfg_with_new_keys
        )
        mgr_with_deprecated_keys = cc_rh_subscription.SubscriptionManager(
            cfg_with_deprecated_keys
        )

        assert (
            mgr_with_new_keys.rhel_cfg == cfg_with_new_keys["rh_subscription"]
        )
        assert (
            mgr_with_deprecated_keys.rhel_cfg
            == cfg_with_deprecated_keys["rh_subscription"]
        )

        dict_new_without_rhel_cfg = mgr_with_new_keys.__dict__
        del dict_new_without_rhel_cfg["rhel_cfg"]

        dict_deprecated_without_rhel_cfg = mgr_with_deprecated_keys.__dict__
        del dict_deprecated_without_rhel_cfg["rhel_cfg"]

        assert dict_new_without_rhel_cfg == dict_deprecated_without_rhel_cfg
