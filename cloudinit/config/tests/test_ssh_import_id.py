# This file is part of cloud-init. See LICENSE file for license information.

import os.path

from cloudinit.config import cc_ssh_import_id
from cloudinit.tests.helpers import CiTestCase, mock
import logging

LOG = logging.getLogger(__name__)

MODPATH = "cloudinit.config.cc_ssh_import_id."

class DummyCloud(object):
    distro = 'dummy'

class TestHandleSshImportId(CiTestCase):
    """Test cc_ssh_import_id handling of import-id config."""

    @mock.patch(MODPATH + 'ug_util.normalize_users_groups')
    @mock.patch(MODPATH + 'import_ssh_ids')
    def test_handle_import_converts_string_to_list(self, m_import, m_ugroups):
        """Test ssh_import_id cfg space separated string converts to list."""
        mycloud = DummyCloud()
        mycfg = {'ssh_import_id': 'foo bar baz'}
        m_ugroups.return_value = ({'ubuntu': {'default': True}}, None)
        cc_ssh_import_id.handle(None, mycfg, mycloud, LOG, [])
        m_import.has_calls([
            mock.call(['foo', 'bar', 'baz'], 'ubuntu', LOG)])

    @mock.patch(MODPATH + 'ug_util.normalize_users_groups')
    @mock.patch(MODPATH + 'import_ssh_ids')
    def test_handle_import_converts_string_to_list_user_cfg(self, m_import,
                                                            m_ugroups):
        """Test ssh_import_id user_cfg space sep string converts to list."""
        mycloud = DummyCloud()
        mycfg = {}
        m_ugroups.return_value = (
            {'ubuntu': {
                'default': True,
                'ssh_import_id': 'foo bar baz'}}, None)
        cc_ssh_import_id.handle(None, mycfg, mycloud, LOG, [])
        m_import.has_calls([
            mock.call(['foo', 'bar', 'baz'], 'ubuntu', LOG)])


    @mock.patch(MODPATH + 'ug_util.normalize_users_groups')
    @mock.patch(MODPATH + 'import_ssh_ids')
    def test_handle_import_single_string_user_cfg(self, m_import, m_ugroups):
        """Test ssh_import_id user cfg space separated string converts to list.
        """
        mycloud = DummyCloud()
        mycfg = {}
        m_ugroups.return_value = (
            {'ubuntu': {'default': True, 'ssh_import_id': 'foo'}}, None)
        cc_ssh_import_id.handle(None, mycfg, mycloud, LOG, [])
        m_import.has_calls([
            mock.call(['foo'], 'ubuntu', LOG)])

    @mock.patch(MODPATH + 'ug_util.normalize_users_groups')
    @mock.patch(MODPATH + 'import_ssh_ids')
    def test_handle_import_lists(self, m_import, m_ugroups):
        """Test ssh_import_id cfg space separated string converts to list."""
        mycloud = DummyCloud()
        mycfg = {'ssh_import_id': ['foo', 'bar', 'baz']}
        m_ugroups.return_value = ({'ubuntu': {'default': True}}, None)
        cc_ssh_import_id.handle(None, mycfg, mycloud, LOG, [])
        m_import.has_calls([
            mock.call(['foo', 'bar', 'baz'], 'ubuntu', LOG)])

    @mock.patch(MODPATH + 'ug_util.normalize_users_groups')
    @mock.patch(MODPATH + 'import_ssh_ids')
    def test_handle_import_lists_user_cfg(self, m_import, m_ugroups):
        """Test ssh_import_id user cfg space separated string converts to list.
        """
        mycloud = DummyCloud()
        mycfg = {}
        m_ugroups.return_value = (
            {'ubuntu': {'default': True,
                        'ssh_import_id': ['foo', 'bar', 'baz']}}, None)
        cc_ssh_import_id.handle(None, mycfg, mycloud, LOG, [])
        m_import.has_calls([
            mock.call(['foo', 'bar', 'baz'], 'ubuntu', LOG)])


    @mock.patch(MODPATH + 'ug_util.normalize_users_groups')
    @mock.patch(MODPATH + 'import_ssh_ids')
    def test_handle_import_empty_list(self, m_import, m_ugroups):
        """Test ssh_import_id cfg space separated string converts to list."""
        mycloud = DummyCloud()
        mycfg = {'ssh_import_id': []}
        m_ugroups.return_value = ({'ubuntu': {'default': True}}, None)
        cc_ssh_import_id.handle(None, mycfg, mycloud, LOG, [])
        self.assertEqual(m_import.call_count, 0)

    @mock.patch(MODPATH + 'ug_util.normalize_users_groups')
    @mock.patch(MODPATH + 'import_ssh_ids')
    def test_handle_import_empty_list_user(self, m_import, m_ugroups):
        """Test ssh_import_id user cfg space separated string converts to list.
        """
        mycloud = DummyCloud()
        mycfg = {}
        m_ugroups.return_value = (
            {'ubuntu': {'default': True, 'ssh_import_id': []}}, None)
        cc_ssh_import_id.handle(None, mycfg, mycloud, LOG, [])
        self.assertEqual(m_import.call_count, 0)

