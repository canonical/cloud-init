# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import cloud
from cloudinit import distros
from cloudinit.config import cc_ca_certs
from cloudinit import helpers
from cloudinit import subp
from cloudinit import util

from cloudinit.tests.helpers import FilesystemMockingTestCase

import os
import logging
import unittest
from contextlib import ExitStack
from unittest import mock


class TestNoConfig(unittest.TestCase):
    def setUp(self):
        super(TestNoConfig, self).setUp()
        self.name = "ca-certs"
        self.cloud_init = None
        self.log = logging.getLogger("TestNoConfig")
        self.args = []

    def test_no_config(self):
        """
        Test that nothing is done if no ca-certs configuration is provided.
        """
        config = util.get_builtin_cfg()
        with ExitStack() as mocks:
            util_mock = mocks.enter_context(
                mock.patch.object(util, 'write_file'))
            certs_mock = mocks.enter_context(
                mock.patch.object(cc_ca_certs, 'update_ca_certs'))

            cc_ca_certs.handle(self.name, config, self.cloud_init, self.log,
                               self.args)

            self.assertEqual(util_mock.call_count, 0)
            self.assertEqual(certs_mock.call_count, 0)


class TestConfig(FilesystemMockingTestCase):
    def setUp(self):
        super(TestConfig, self).setUp()
        self.new_root = self.tmp_dir()
        self.name = "ca-certs"
        self.log = logging.getLogger("TestConfig")
        self.args = []

    def _get_cloud(self, distro, sys_cfg=None):
        self.new_root = self.reRoot(root=self.new_root)
        paths = helpers.Paths({'cloud_dir': self.new_root})
        cls = distros.fetch(distro)
        if not sys_cfg:
            sys_cfg = {}
        mydist = cls(distro, sys_cfg, paths)

        self._mock_init()
        return cloud.Cloud(None, paths, sys_cfg, mydist, None)

    def _mock_init(self):
        self.mocks = ExitStack()
        self.addCleanup(self.mocks.close)

        # Mock out the functions that actually modify the system
        self.mock_add = self.mocks.enter_context(
            mock.patch.object(cc_ca_certs, 'add_ca_certs'))
        self.mock_update_certs = self.mocks.enter_context(
            mock.patch.object(cc_ca_certs, 'update_ca_certs'))
        self.mock_update_config = self.mocks.enter_context(
            mock.patch.object(cc_ca_certs, 'update_cert_config'))
        self.mock_remove = self.mocks.enter_context(
            mock.patch.object(cc_ca_certs, 'remove_default_ca_certs'))

    def test_no_trusted_list(self):
        """
        Test that no certificates are written if the 'trusted' key is not
        present.
        """
        config = {"ca-certs": {}}
        for distro in cc_ca_certs.distros:
            mycloud = self._get_cloud(distro)
            cc_ca_certs.handle(self.name, config, mycloud, self.log, self.args)
            self.assertEqual(self.mock_add.call_count, 0)
            self.assertEqual(self.mock_update_certs.call_count, 1)
            self.assertEqual(self.mock_update_config.call_count, 0)
            self.assertEqual(self.mock_remove.call_count, 0)

    def test_empty_trusted_list(self):
        """Test that no certificate are written if 'trusted' list is empty."""
        config = {"ca-certs": {"trusted": []}}
        for distro in cc_ca_certs.distros:
            mycloud = self._get_cloud(distro)
            cc_ca_certs.handle(self.name, config, mycloud, self.log, self.args)

            self.assertEqual(self.mock_add.call_count, 0)
            self.assertEqual(self.mock_update_certs.call_count, 1)
            self.assertEqual(self.mock_update_config.call_count, 0)
            self.assertEqual(self.mock_remove.call_count, 0)

    def test_single_trusted(self):
        """Test that a single cert gets passed to add_ca_certs."""
        config = {"ca-certs": {"trusted": ["CERT1"]}}
        for distro in cc_ca_certs.distros:
            mycloud = self._get_cloud(distro)
            cc_ca_certs.handle(self.name, config, mycloud, self.log, self.args)

            self.mock_add.assert_called_once_with(distro, ['CERT1'])
            self.assertEqual(self.mock_update_certs.call_count, 1)
            self.assertEqual(self.mock_update_config.call_count, 0)
            self.assertEqual(self.mock_remove.call_count, 0)

    def test_multiple_trusted(self):
        """Test that multiple certs get passed to add_ca_certs."""
        config = {"ca-certs": {"trusted": ["CERT1", "CERT2"]}}

        for distro in cc_ca_certs.distros:
            mycloud = self._get_cloud(distro)
            cc_ca_certs.handle(self.name, config, mycloud, self.log, self.args)

            self.mock_add.assert_called_once_with(distro, ['CERT1', 'CERT2'])
            self.assertEqual(self.mock_update_certs.call_count, 1)
            self.assertEqual(self.mock_update_config.call_count, 0)
            self.assertEqual(self.mock_remove.call_count, 0)

    def test_remove_default_ca_certs(self):
        """Test remove_defaults works as expected."""
        config = {"ca-certs": {"remove-defaults": True}}

        for distro in cc_ca_certs.distros:
            mycloud = self._get_cloud(distro)
            cc_ca_certs.handle(self.name, config, mycloud, self.log, self.args)

            self.assertEqual(self.mock_add.call_count, 0)
            self.assertEqual(self.mock_update_certs.call_count, 1)
            self.assertEqual(self.mock_update_config.call_count, 0)
            self.assertEqual(self.mock_remove.call_count, 1)

    def test_no_remove_defaults_if_false(self):
        """Test remove_defaults is not called when config value is False."""
        config = {"ca-certs": {"remove-defaults": False}}

        for distro in cc_ca_certs.distros:
            mycloud = self._get_cloud(distro)
            cc_ca_certs.handle(self.name, config, mycloud, self.log, self.args)

            self.assertEqual(self.mock_add.call_count, 0)
            self.assertEqual(self.mock_update_certs.call_count, 1)
            self.assertEqual(self.mock_update_config.call_count, 0)
            self.assertEqual(self.mock_remove.call_count, 0)

    def test_correct_order_for_remove_then_add(self):
        """Test remove_defaults is not called when config value is False."""
        config = {"ca-certs": {"remove-defaults": True, "trusted": ["CERT1"]}}

        for distro in cc_ca_certs.distros:
            mycloud = self._get_cloud(distro)
            cc_ca_certs.handle(self.name, config, mycloud, self.log, self.args)

            self.mock_add.assert_called_once_with(distro, ['CERT1'])
            self.assertEqual(self.mock_update_certs.call_count, 1)
            self.assertEqual(self.mock_update_config.call_count, 0)
            self.assertEqual(self.mock_remove.call_count, 1)


class TestAddCaCerts(FilesystemMockingTestCase):
    def setUp(self):
        super(TestAddCaCerts, self).setUp()
        self.new_root = self.tmp_dir()
        self.name = "ca-certs"
        self.log = logging.getLogger("TestAddCaCerts")
        self.args = []

    def _get_cloud(self, distro, sys_cfg=None):
        self.new_root = self.reRoot(root=self.new_root)
        paths = helpers.Paths({'cloud_dir': self.new_root})
        cls = distros.fetch(distro)
        if not sys_cfg:
            sys_cfg = {}
        mydist = cls(distro, sys_cfg, paths)

        return cloud.Cloud(None, paths, sys_cfg, mydist, None)

    def _generate_file(self, path=None, content=None):
        self.new_root = self.reRoot(root=self.new_root)
        if not path:
            return
        conf_path = os.path.join(self.new_root, path)
        if not os.path.isfile(conf_path):
            util.write_file(conf_path, content=content)
        return

    def test_no_certs_in_list(self):
        """Test that no certificate are written if not provided."""
        for distro in cc_ca_certs.distros:
            with mock.patch.object(util, 'write_file') as mockobj:
                cc_ca_certs.add_ca_certs(distro, [])
            self.assertEqual(mockobj.call_count, 0)

    def test_single_cert_trailing_cr(self):
        """Test adding a single certificate to the trusted CAs
        when existing ca-certificates has trailing newline"""
        cert = "CERT1\nLINE2\nLINE3"

        ca_certs_content = "line1\nline2\ncloud-init-ca-certs.crt\nline3\n"
        expected = "line1\nline2\nline3\ncloud-init-ca-certs.crt\n"

        for distro in cc_ca_certs.distros:
            distro_conf = cc_ca_certs._distro_ca_certs_configs(distro)
            self._generate_file(distro_conf['ca_cert_config'],
                                ca_certs_content)

            with ExitStack() as mocks:
                mock_write = mocks.enter_context(
                    mock.patch.object(util, 'write_file'))
                mock_load = mocks.enter_context(
                    mock.patch.object(util, 'load_file',
                                      return_value=ca_certs_content))

                cc_ca_certs.add_ca_certs(distro, [cert])

                mock_write.assert_has_calls([
                    mock.call(distro_conf['ca_cert_full_path'],
                              cert, mode=0o644)])
                if distro_conf['ca_cert_config'] is not None:
                    mock_write.assert_has_calls([
                        mock.call(distro_conf['ca_cert_config'],
                                  expected, omode="wb")])
                    mock_load.assert_called_once_with(
                        distro_conf['ca_cert_config'])

    def test_single_cert_no_trailing_cr(self):
        """Test adding a single certificate to the trusted CAs
        when existing ca-certificates has no trailing newline"""
        cert = "CERT1\nLINE2\nLINE3"

        ca_certs_content = "line1\nline2\nline3"

        for distro in cc_ca_certs.distros:
            distro_conf = cc_ca_certs._distro_ca_certs_configs(distro)
            self._generate_file(distro_conf['ca_cert_config'],
                                ca_certs_content)

            with ExitStack() as mocks:
                mock_write = mocks.enter_context(
                    mock.patch.object(util, 'write_file'))
                mock_load = mocks.enter_context(
                    mock.patch.object(util, 'load_file',
                                      return_value=ca_certs_content))

                cc_ca_certs.add_ca_certs(distro, [cert])

                mock_write.assert_has_calls([
                    mock.call(distro_conf['ca_cert_full_path'],
                              cert, mode=0o644)])

                if distro_conf['ca_cert_config'] is not None:
                    mock_write.assert_has_calls([
                        mock.call(
                            distro_conf['ca_cert_config'],
                            "%s\n%s\n" % (ca_certs_content,
                                          distro_conf['ca_cert_filename']),
                            omode="wb")])
                    mock_load.assert_called_once_with(
                        distro_conf['ca_cert_config'])

    def test_single_cert_to_empty_existing_ca_file(self):
        """Test adding a single certificate to the trusted CAs
        when existing ca-certificates.conf is empty"""
        cert = "CERT1\nLINE2\nLINE3"

        expected = "cloud-init-ca-certs.crt\n"

        for distro in cc_ca_certs.distros:
            distro_conf = cc_ca_certs._distro_ca_certs_configs(distro)
            self._generate_file(distro_conf['ca_cert_config'], '')

            with ExitStack() as mocks:
                mock_write = mocks.enter_context(
                    mock.patch.object(util, 'write_file', autospec=True))
                mock_stat = mocks.enter_context(
                    mock.patch("cloudinit.config.cc_ca_certs.os.stat")
                )
                mock_stat.return_value.st_size = 0

                cc_ca_certs.add_ca_certs(distro, [cert])

                mock_write.assert_has_calls([
                    mock.call(distro_conf['ca_cert_full_path'],
                              cert, mode=0o644)])
                if distro_conf['ca_cert_config'] is not None:
                    mock_write.assert_has_calls([
                        mock.call(distro_conf['ca_cert_config'],
                                  expected, omode="wb")])

    def test_multiple_certs(self):
        """Test adding multiple certificates to the trusted CAs."""
        certs = ["CERT1\nLINE2\nLINE3", "CERT2\nLINE2\nLINE3"]
        expected_cert_file = "\n".join(certs)
        ca_certs_content = "line1\nline2\nline3"

        for distro in cc_ca_certs.distros:
            distro_conf = cc_ca_certs._distro_ca_certs_configs(distro)
            self._generate_file(distro_conf['ca_cert_config'],
                                ca_certs_content)

            with ExitStack() as mocks:
                mock_write = mocks.enter_context(
                    mock.patch.object(util, 'write_file'))
                mock_load = mocks.enter_context(
                    mock.patch.object(util, 'load_file',
                                      return_value=ca_certs_content))

                cc_ca_certs.add_ca_certs(distro, certs)

                mock_write.assert_has_calls([
                    mock.call(distro_conf['ca_cert_full_path'],
                              expected_cert_file, mode=0o644)])

                if distro_conf['ca_cert_config'] is not None:
                    mock_write.assert_has_calls([
                        mock.call(
                            distro_conf['ca_cert_config'],
                            "%s\n%s\n" % (ca_certs_content,
                                          distro_conf['ca_cert_filename']),
                            omode='wb')])

                    mock_load.assert_called_once_with(
                        distro_conf['ca_cert_config'])


class TestUpdateCaCerts(unittest.TestCase):
    def test_commands(self):
        for distro in cc_ca_certs.distros:
            distro_conf = cc_ca_certs._distro_ca_certs_configs(distro)
            with mock.patch.object(subp, 'subp') as mockobj:
                cc_ca_certs.update_ca_certs(distro)
                mockobj.assert_called_once_with(
                    distro_conf['ca_cert_update_cmd'], capture=False)


class TestRemoveDefaultCaCerts(FilesystemMockingTestCase):

    def setUp(self):
        super(TestRemoveDefaultCaCerts, self).setUp()
        self.new_root = self.tmp_dir()
        self.name = "ca-certs"
        self.log = logging.getLogger("TestRemoveDefaultCaCerts")
        self.args = []
        self.reRoot(root=self.new_root)

    def _mock_init(self):
        self.mocks = ExitStack()
        self.addCleanup(self.mocks.close)

        self.mock_delete = self.mocks.enter_context(
            mock.patch.object(util, 'delete_dir_contents'))
        self.mock_write = self.mocks.enter_context(
            mock.patch.object(util, 'write_file'))
        self.mock_subp = self.mocks.enter_context(
            mock.patch.object(subp, 'subp'))

    def test_commands(self):
        for distro in cc_ca_certs.distros:
            self._mock_init()
            distro_conf = cc_ca_certs._distro_ca_certs_configs(distro)

            cc_ca_certs.remove_default_ca_certs(distro)

            self.mock_delete.assert_has_calls([
                mock.call(distro_conf['ca_cert_path']),
                mock.call(distro_conf['ca_cert_system_path'])])

            if distro_conf['ca_cert_config'] is not None:
                self.mock_write.assert_called_once_with(
                    distro_conf['ca_cert_config'], "", mode=0o644)

            if distro in ['debian', 'ubuntu']:
                self.mock_subp.assert_called_once_with(
                    ('debconf-set-selections', '-'),
                    "ca-certificates ca-certificates/trust_new_crts select no")

# vi: ts=4 expandtab
