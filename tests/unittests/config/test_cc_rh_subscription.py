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
from tests.unittests.helpers import CiTestCase, mock, skipUnlessJsonSchema

SUBMGR = cc_rh_subscription.SubscriptionManager
SUB_MAN_CLI = "cloudinit.config.cc_rh_subscription._sub_man_cli"


@mock.patch(SUB_MAN_CLI)
class GoodTests(CiTestCase):
    with_logs = True

    def setUp(self):
        super(GoodTests, self).setUp()
        self.name = "cc_rh_subscription"
        self.cloud_init = None
        self.log = logging.getLogger("good_tests")
        self.args = []
        self.handle = cc_rh_subscription.handle

        self.config = {
            "rh_subscription": {
                "username": "scooby@do.com",
                "password": "scooby-snacks",
            }
        }
        self.config_full = {
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

    def test_already_registered(self, m_sman_cli):
        """
        Emulates a system that is already registered. Ensure it gets
        a non-ProcessExecution error from is_registered()
        """
        self.handle(self.name, self.config, self.cloud_init, self.args)
        self.assertEqual(m_sman_cli.call_count, 1)
        self.assertIn("System is already registered", self.logs.getvalue())

    def test_simple_registration(self, m_sman_cli):
        """
        Simple registration with username and password
        """
        reg = (
            "The system has been registered with ID:"
            " 12345678-abde-abcde-1234-1234567890abc"
        )
        m_sman_cli.side_effect = [subp.ProcessExecutionError, (reg, "bar")]
        self.handle(self.name, self.config, self.cloud_init, self.args)
        self.assertIn(mock.call(["identity"]), m_sman_cli.call_args_list)
        self.assertIn(
            mock.call(
                [
                    "register",
                    "--username=scooby@do.com",
                    "--password=scooby-snacks",
                ],
                logstring_val=True,
            ),
            m_sman_cli.call_args_list,
        )
        self.assertIn(
            "rh_subscription plugin completed successfully",
            self.logs.getvalue(),
        )
        self.assertEqual(m_sman_cli.call_count, 2)

    @mock.patch.object(cc_rh_subscription.SubscriptionManager, "_getRepos")
    def test_update_repos_disable_with_none(self, m_get_repos, m_sman_cli):
        cfg = copy.deepcopy(self.config)
        m_get_repos.return_value = ([], ["repo1"])
        cfg["rh_subscription"].update(
            {"enable-repo": ["repo1"], "disable-repo": None}
        )
        mysm = cc_rh_subscription.SubscriptionManager(cfg)
        self.assertEqual(True, mysm.update_repos())
        m_get_repos.assert_called_with()
        self.assertEqual(
            m_sman_cli.call_args_list, [mock.call(["repos", "--enable=repo1"])]
        )

    def test_full_registration(self, m_sman_cli):
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
        self.handle(self.name, self.config_full, self.cloud_init, self.args)
        self.assertEqual(m_sman_cli.call_count, 9)
        for call in call_lists:
            self.assertIn(mock.call(call), m_sman_cli.call_args_list)
        self.assertIn(
            "rh_subscription plugin completed successfully",
            self.logs.getvalue(),
        )


@mock.patch(SUB_MAN_CLI)
class TestBadInput(CiTestCase):
    with_logs = True
    name = "cc_rh_subscription"
    cloud_init = None
    log = logging.getLogger("bad_tests")
    args: list = []
    SM = cc_rh_subscription.SubscriptionManager
    reg = (
        "The system has been registered with ID:"
        " 12345678-abde-abcde-1234-1234567890abc"
    )

    config_no_password = {"rh_subscription": {"username": "scooby@do.com"}}

    config_no_key = {
        "rh_subscription": {
            "activation-key": "1234abcde",
        }
    }

    config_service = {
        "rh_subscription": {
            "username": "scooby@do.com",
            "password": "scooby-snacks",
            "service-level": "self-support",
        }
    }

    config_badpool = {
        "rh_subscription": {
            "username": "scooby@do.com",
            "password": "scooby-snacks",
            "add-pool": "not_a_list",
        }
    }
    config_badrepo = {
        "rh_subscription": {
            "username": "scooby@do.com",
            "password": "scooby-snacks",
            "enable-repo": "not_a_list",
        }
    }
    config_badkey = {
        "rh_subscription": {
            "activation-key": "abcdef1234",
            "fookey": "bar",
            "org": "ABC",
        }
    }

    def setUp(self):
        super(TestBadInput, self).setUp()
        self.handle = cc_rh_subscription.handle

    def assert_logged_warnings(self, warnings):
        logs = self.logs.getvalue()
        missing = [w for w in warnings if "WARNING: " + w not in logs]
        self.assertEqual([], missing, "Missing expected warnings.")

    def test_no_password(self, m_sman_cli):
        """Attempt to register without the password key/value."""
        m_sman_cli.side_effect = [
            subp.ProcessExecutionError,
            (self.reg, "bar"),
        ]
        self.handle(
            self.name,
            self.config_no_password,
            self.cloud_init,
            self.args,
        )
        self.assertEqual(m_sman_cli.call_count, 0)

    def test_no_org(self, m_sman_cli):
        """Attempt to register without the org key/value."""
        m_sman_cli.side_effect = [subp.ProcessExecutionError]
        self.handle(self.name, self.config_no_key, self.cloud_init, self.args)
        m_sman_cli.assert_called_with(["identity"])
        self.assertEqual(m_sman_cli.call_count, 1)
        self.assert_logged_warnings(
            (
                "Unable to register system due to incomplete information.",
                "Use either activationkey and org *or* userid and password",
                "Registration failed or did not run completely",
                "rh_subscription plugin did not complete successfully",
            )
        )

    def test_service_level_without_auto(self, m_sman_cli):
        """Attempt to register using service-level without auto-attach key."""
        m_sman_cli.side_effect = [
            subp.ProcessExecutionError,
            (self.reg, "bar"),
        ]
        self.handle(
            self.name,
            self.config_service,
            self.cloud_init,
            self.args,
        )
        self.assertEqual(m_sman_cli.call_count, 1)
        self.assert_logged_warnings(
            (
                "The service-level key must be used in conjunction with ",
                "rh_subscription plugin did not complete successfully",
            )
        )

    def test_pool_not_a_list(self, m_sman_cli):
        """
        Register with pools that are not in the format of a list
        """
        m_sman_cli.side_effect = [
            subp.ProcessExecutionError,
            (self.reg, "bar"),
        ]
        self.handle(
            self.name,
            self.config_badpool,
            self.cloud_init,
            self.args,
        )
        self.assertEqual(m_sman_cli.call_count, 2)
        self.assert_logged_warnings(
            (
                "Pools must in the format of a list",
                "rh_subscription plugin did not complete successfully",
            )
        )

    def test_repo_not_a_list(self, m_sman_cli):
        """
        Register with repos that are not in the format of a list
        """
        m_sman_cli.side_effect = [
            subp.ProcessExecutionError,
            (self.reg, "bar"),
        ]
        self.handle(
            self.name,
            self.config_badrepo,
            self.cloud_init,
            self.args,
        )
        self.assertEqual(m_sman_cli.call_count, 2)
        self.assert_logged_warnings(
            (
                "Repo IDs must in the format of a list.",
                "Unable to add or remove repos",
                "rh_subscription plugin did not complete successfully",
            )
        )

    def test_bad_key_value(self, m_sman_cli):
        """
        Attempt to register with a key that we don't know
        """
        m_sman_cli.side_effect = [
            subp.ProcessExecutionError,
            (self.reg, "bar"),
        ]
        self.handle(self.name, self.config_badkey, self.cloud_init, self.args)
        self.assertEqual(m_sman_cli.call_count, 1)
        self.assert_logged_warnings(
            (
                "fookey is not a valid key for rh_subscription. Valid keys"
                " are:",
                "rh_subscription plugin did not complete successfully",
            )
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
