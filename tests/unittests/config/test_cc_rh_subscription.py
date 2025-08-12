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
from tests.unittests.helpers import mock, skipUnlessJsonSchema

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
            "auto-attach": True,
            "service-level": "self-support",
            "add-pool": ["pool1", "pool2", "pool3"],
            "enable-repo": ["repo1", "repo2", "repo3"],
            "disable-repo": ["repo4", "repo5"],
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

    def test_simple_registration(self, m_sman_cli, caplog):
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

    @mock.patch.object(cc_rh_subscription.SubscriptionManager, "_getRepos")
    def test_update_repos_disable_with_none(self, m_get_repos, m_sman_cli):
        cfg = copy.deepcopy(self.CONFIG)
        m_get_repos.return_value = ([], ["repo1"])
        cfg["rh_subscription"].update(
            {"enable-repo": ["repo1"], "disable-repo": None}
        )
        mysm = cc_rh_subscription.SubscriptionManager(cfg)
        assert True is mysm.update_repos()
        m_get_repos.assert_called_with()
        assert m_sman_cli.call_args_list == [
            mock.call(["repos", "--enable=repo1"])
        ]

    def test_full_registration(self, m_sman_cli, caplog):
        """
        Registration with auto-attach, service-level, adding pools,
        and enabling and disabling yum repos
        """
        call_lists = []
        call_lists.append(["attach", "--pool=pool1", "--pool=pool3"])
        call_lists.append(
            ["repos", "--disable=repo5", "--enable=repo2", "--enable=repo3"]
        )
        call_lists.append(["attach", "--auto", "--servicelevel=self-support"])
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
        ]
        cc_rh_subscription.handle(NAME, self.CONFIG_FULL, None, [])
        assert m_sman_cli.call_count == 9
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
            "activation-key": "1234abcde",
        }
    }

    CONFIG_SERVICE = {
        "rh_subscription": {
            "username": "scooby@do.com",
            "password": "scooby-snacks",
            "service-level": "self-support",
        }
    }

    CONFIG_BADPOOL = {
        "rh_subscription": {
            "username": "scooby@do.com",
            "password": "scooby-snacks",
            "add-pool": "not_a_list",
        }
    }
    CONFIG_BADREPO = {
        "rh_subscription": {
            "username": "scooby@do.com",
            "password": "scooby-snacks",
            "enable-repo": "not_a_list",
        }
    }
    CONFIG_BADKEY = {
        "rh_subscription": {
            "activation-key": "abcdef1234",
            "fookey": "bar",
            "org": "ABC",
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
        """Attempt to register using service-level without auto-attach key."""
        m_sman_cli.side_effect = [
            subp.ProcessExecutionError,
            (self.REG, "bar"),
        ]
        cc_rh_subscription.handle(NAME, self.CONFIG_SERVICE, None, [])
        assert m_sman_cli.call_count == 1
        self.assert_logged_warnings(
            (
                "The service-level key must be used in conjunction with the"
                " auto-attach key.  Please re-run with auto-attach: True",
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

    def test_bad_key_value(self, m_sman_cli, caplog):
        """
        Attempt to register with a key that we don't know
        """
        m_sman_cli.side_effect = [
            subp.ProcessExecutionError,
            (self.REG, "bar"),
        ]
        cc_rh_subscription.handle(NAME, self.CONFIG_BADKEY, None, [])
        assert m_sman_cli.call_count == 1
        self.assert_logged_warnings(
            (
                "fookey is not a valid key for rh_subscription. Valid keys"
                " are: org, activation-key, username, password, disable-repo,"
                " enable-repo, add-pool, rhsm-baseurl, server-hostname,"
                " auto-attach, service-level",
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
                {"rh_subscription": {"enable-repo": "name"}},
                "'name' is not of type 'array'",
            ),
            (
                {"rh_subscription": {"disable-repo": "name"}},
                "'name' is not of type 'array'",
            ),
            (
                {
                    "rh_subscription": {
                        "activation-key": "foobar",
                        "org": "ABC",
                    }
                },
                None,
            ),
            (
                {"rh_subscription": {"activation-key": "foobar", "org": 314}},
                "Deprecated in version 24.2. Use of type integer for this"
                " value is deprecated. Use a string instead.",
            ),
        ],
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        if error_msg is None:
            validate_cloudconfig_schema(config, get_schema(), strict=True)
        else:
            with pytest.raises(SchemaValidationError, match=error_msg):
                validate_cloudconfig_schema(config, get_schema(), strict=True)
