# This file is part of cloud-init. See LICENSE file for license information.

"""Tests for registering RHEL subscription via rh_subscription."""

import copy
import logging

from cloudinit.config import cc_rh_subscription
from cloudinit import util

from cloudinit.tests.helpers import TestCase, mock


class GoodTests(TestCase):
    def setUp(self):
        super(GoodTests, self).setUp()
        self.name = "cc_rh_subscription"
        self.cloud_init = None
        self.log = logging.getLogger("good_tests")
        self.args = []
        self.handle = cc_rh_subscription.handle
        self.SM = cc_rh_subscription.SubscriptionManager

        self.config = {'rh_subscription':
                       {'username': 'scooby@do.com',
                        'password': 'scooby-snacks'
                        }}
        self.config_full = {'rh_subscription':
                            {'username': 'scooby@do.com',
                             'password': 'scooby-snacks',
                             'auto-attach': True,
                             'service-level': 'self-support',
                             'add-pool': ['pool1', 'pool2', 'pool3'],
                             'enable-repo': ['repo1', 'repo2', 'repo3'],
                             'disable-repo': ['repo4', 'repo5']
                             }}

    def test_already_registered(self):
        '''
        Emulates a system that is already registered. Ensure it gets
        a non-ProcessExecution error from is_registered()
        '''
        with mock.patch.object(cc_rh_subscription.SubscriptionManager,
                               '_sub_man_cli') as mockobj:
            self.SM.log_success = mock.MagicMock()
            self.handle(self.name, self.config, self.cloud_init,
                        self.log, self.args)
            self.assertEqual(self.SM.log_success.call_count, 1)
            self.assertEqual(mockobj.call_count, 1)

    def test_simple_registration(self):
        '''
        Simple registration with username and password
        '''
        self.SM.log_success = mock.MagicMock()
        reg = "The system has been registered with ID:" \
              " 12345678-abde-abcde-1234-1234567890abc"
        self.SM._sub_man_cli = mock.MagicMock(
            side_effect=[util.ProcessExecutionError, (reg, 'bar')])
        self.handle(self.name, self.config, self.cloud_init,
                    self.log, self.args)
        self.assertIn(mock.call(['identity']),
                      self.SM._sub_man_cli.call_args_list)
        self.assertIn(mock.call(['register', '--username=scooby@do.com',
                                 '--password=scooby-snacks'],
                                logstring_val=True),
                      self.SM._sub_man_cli.call_args_list)

        self.assertEqual(self.SM.log_success.call_count, 1)
        self.assertEqual(self.SM._sub_man_cli.call_count, 2)

    @mock.patch.object(cc_rh_subscription.SubscriptionManager, "_getRepos")
    @mock.patch.object(cc_rh_subscription.SubscriptionManager, "_sub_man_cli")
    def test_update_repos_disable_with_none(self, m_sub_man_cli, m_get_repos):
        cfg = copy.deepcopy(self.config)
        m_get_repos.return_value = ([], ['repo1'])
        m_sub_man_cli.return_value = (b'', b'')
        cfg['rh_subscription'].update(
            {'enable-repo': ['repo1'], 'disable-repo': None})
        mysm = cc_rh_subscription.SubscriptionManager(cfg)
        self.assertEqual(True, mysm.update_repos())
        m_get_repos.assert_called_with()
        self.assertEqual(m_sub_man_cli.call_args_list,
                         [mock.call(['repos', '--enable=repo1'])])

    def test_full_registration(self):
        '''
        Registration with auto-attach, service-level, adding pools,
        and enabling and disabling yum repos
        '''
        call_lists = []
        call_lists.append(['attach', '--pool=pool1', '--pool=pool3'])
        call_lists.append(['repos', '--disable=repo5', '--enable=repo2',
                           '--enable=repo3'])
        call_lists.append(['attach', '--auto', '--servicelevel=self-support'])
        self.SM.log_success = mock.MagicMock()
        reg = "The system has been registered with ID:" \
              " 12345678-abde-abcde-1234-1234567890abc"
        self.SM._sub_man_cli = mock.MagicMock(
            side_effect=[util.ProcessExecutionError, (reg, 'bar'),
                         ('Service level set to: self-support', ''),
                         ('pool1\npool3\n', ''), ('pool2\n', ''), ('', ''),
                         ('Repo ID: repo1\nRepo ID: repo5\n', ''),
                         ('Repo ID: repo2\nRepo ID: repo3\nRepo ID: '
                          'repo4', ''),
                         ('', '')])
        self.handle(self.name, self.config_full, self.cloud_init,
                    self.log, self.args)
        for call in call_lists:
            self.assertIn(mock.call(call), self.SM._sub_man_cli.call_args_list)
        self.assertEqual(self.SM.log_success.call_count, 1)
        self.assertEqual(self.SM._sub_man_cli.call_count, 9)


class TestBadInput(TestCase):
    name = "cc_rh_subscription"
    cloud_init = None
    log = logging.getLogger("bad_tests")
    args = []
    SM = cc_rh_subscription.SubscriptionManager
    reg = "The system has been registered with ID:" \
          " 12345678-abde-abcde-1234-1234567890abc"

    config_no_password = {'rh_subscription':
                          {'username': 'scooby@do.com'
                           }}

    config_no_key = {'rh_subscription':
                     {'activation-key': '1234abcde',
                      }}

    config_service = {'rh_subscription':
                      {'username': 'scooby@do.com',
                       'password': 'scooby-snacks',
                       'service-level': 'self-support'
                       }}

    config_badpool = {'rh_subscription':
                      {'username': 'scooby@do.com',
                       'password': 'scooby-snacks',
                       'add-pool': 'not_a_list'
                       }}
    config_badrepo = {'rh_subscription':
                      {'username': 'scooby@do.com',
                       'password': 'scooby-snacks',
                       'enable-repo': 'not_a_list'
                       }}
    config_badkey = {'rh_subscription':
                     {'activation-key': 'abcdef1234',
                      'fookey': 'bar',
                      'org': '123',
                      }}

    def setUp(self):
        super(TestBadInput, self).setUp()
        self.handle = cc_rh_subscription.handle

    def test_no_password(self):
        '''
        Attempt to register without the password key/value
        '''
        self.SM._sub_man_cli = mock.MagicMock(
            side_effect=[util.ProcessExecutionError, (self.reg, 'bar')])
        self.handle(self.name, self.config_no_password, self.cloud_init,
                    self.log, self.args)
        self.assertEqual(self.SM._sub_man_cli.call_count, 0)

    def test_no_org(self):
        '''
        Attempt to register without the org key/value
        '''
        self.input_is_missing_data(self.config_no_key)

    def test_service_level_without_auto(self):
        '''
        Attempt to register using service-level without the auto-attach key
        '''
        self.SM.log_warn = mock.MagicMock()
        self.SM._sub_man_cli = mock.MagicMock(
            side_effect=[util.ProcessExecutionError, (self.reg, 'bar')])
        self.handle(self.name, self.config_service, self.cloud_init,
                    self.log, self.args)
        self.assertEqual(self.SM._sub_man_cli.call_count, 1)
        self.assertEqual(self.SM.log_warn.call_count, 2)

    def test_pool_not_a_list(self):
        '''
        Register with pools that are not in the format of a list
        '''
        self.SM.log_warn = mock.MagicMock()
        self.SM._sub_man_cli = mock.MagicMock(
            side_effect=[util.ProcessExecutionError, (self.reg, 'bar')])
        self.handle(self.name, self.config_badpool, self.cloud_init,
                    self.log, self.args)
        self.assertEqual(self.SM._sub_man_cli.call_count, 2)
        self.assertEqual(self.SM.log_warn.call_count, 2)

    def test_repo_not_a_list(self):
        '''
        Register with repos that are not in the format of a list
        '''
        self.SM.log_warn = mock.MagicMock()
        self.SM._sub_man_cli = mock.MagicMock(
            side_effect=[util.ProcessExecutionError, (self.reg, 'bar')])
        self.handle(self.name, self.config_badrepo, self.cloud_init,
                    self.log, self.args)
        self.assertEqual(self.SM.log_warn.call_count, 3)
        self.assertEqual(self.SM._sub_man_cli.call_count, 2)

    def test_bad_key_value(self):
        '''
        Attempt to register with a key that we don't know
        '''
        self.SM.log_warn = mock.MagicMock()
        self.SM._sub_man_cli = mock.MagicMock(
            side_effect=[util.ProcessExecutionError, (self.reg, 'bar')])
        self.handle(self.name, self.config_badkey, self.cloud_init,
                    self.log, self.args)
        self.assertEqual(self.SM.log_warn.call_count, 2)
        self.assertEqual(self.SM._sub_man_cli.call_count, 1)

    def input_is_missing_data(self, config):
        '''
        Helper def for tests that having missing information
        '''
        self.SM.log_warn = mock.MagicMock()
        self.SM._sub_man_cli = mock.MagicMock(
            side_effect=[util.ProcessExecutionError])
        self.handle(self.name, config, self.cloud_init,
                    self.log, self.args)
        self.SM._sub_man_cli.assert_called_with(['identity'])
        self.assertEqual(self.SM.log_warn.call_count, 4)
        self.assertEqual(self.SM._sub_man_cli.call_count, 1)

# vi: ts=4 expandtab
