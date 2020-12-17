# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import cloud
from cloudinit import distros
from cloudinit.config import cc_ca_certs
from cloudinit import helpers
from cloudinit import subp
from cloudinit import util

from cloudinit.tests.helpers import TestCase

import logging
import shutil
import tempfile
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


class TestConfig(TestCase):
    def setUp(self):
        super(TestConfig, self).setUp()
        self.name = "ca-certs"
        self.paths = None
        self.log = logging.getLogger("TestNoConfig")
        self.args = []

    def _fetch_distro(self, kind):
        cls = distros.fetch(kind)
        paths = helpers.Paths({})
        return cls(kind, {}, paths)

    def _get_cloud(self, kind):
        distro = self._fetch_distro(kind)
        return cloud.Cloud(None, self.paths, None, distro, None)

    def _mock_init(self):
        self.mocks = ExitStack()
        self.addCleanup(self.mocks.close)

        # Mock out the functions that actually modify the system
        self.mock_add = self.mocks.enter_context(
            mock.patch.object(cc_ca_certs, 'add_ca_certs'))
        self.mock_update = self.mocks.enter_context(
            mock.patch.object(cc_ca_certs, 'update_ca_certs'))
        self.mock_remove = self.mocks.enter_context(
            mock.patch.object(cc_ca_certs, 'remove_default_ca_certs'))

    def test_no_trusted_list(self):
        """
        Test that no certificates are written if the 'trusted' key is not
        present.
        """
        config = {"ca-certs": {}}

        for distro_name in cc_ca_certs.distros:
            self._mock_init()
            cloud = self._get_cloud(distro_name)
            cc_ca_certs.handle(self.name, config, cloud, self.log, self.args)

            self.assertEqual(self.mock_add.call_count, 0)
            self.assertEqual(self.mock_update.call_count, 1)
            self.assertEqual(self.mock_remove.call_count, 0)

    def test_empty_trusted_list(self):
        """Test that no certificate are written if 'trusted' list is empty."""
        config = {"ca-certs": {"trusted": []}}

        for distro_name in cc_ca_certs.distros:
            self._mock_init()
            cloud = self._get_cloud(distro_name)
            cc_ca_certs.handle(self.name, config, cloud, self.log, self.args)

            self.assertEqual(self.mock_add.call_count, 0)
            self.assertEqual(self.mock_update.call_count, 1)
            self.assertEqual(self.mock_remove.call_count, 0)

    def test_single_trusted(self):
        """Test that a single cert gets passed to add_ca_certs."""
        config = {"ca-certs": {"trusted": ["CERT1"]}}

        for distro_name in cc_ca_certs.distros:
            self._mock_init()
            cloud = self._get_cloud(distro_name)
            conf = cc_ca_certs._distro_ca_certs_configs(distro_name)
            cc_ca_certs.handle(self.name, config, cloud, self.log, self.args)

            self.mock_add.assert_called_once_with(conf, ['CERT1'])
            self.assertEqual(self.mock_update.call_count, 1)
            self.assertEqual(self.mock_remove.call_count, 0)

    def test_multiple_trusted(self):
        """Test that multiple certs get passed to add_ca_certs."""
        config = {"ca-certs": {"trusted": ["CERT1", "CERT2"]}}

        for distro_name in cc_ca_certs.distros:
            self._mock_init()
            cloud = self._get_cloud(distro_name)
            conf = cc_ca_certs._distro_ca_certs_configs(distro_name)
            cc_ca_certs.handle(self.name, config, cloud, self.log, self.args)

            self.mock_add.assert_called_once_with(conf, ['CERT1', 'CERT2'])
            self.assertEqual(self.mock_update.call_count, 1)
            self.assertEqual(self.mock_remove.call_count, 0)

    def test_remove_default_ca_certs(self):
        """Test remove_defaults works as expected."""
        config = {"ca-certs": {"remove-defaults": True}}

        for distro_name in cc_ca_certs.distros:
            self._mock_init()
            cloud = self._get_cloud(distro_name)
            cc_ca_certs.handle(self.name, config, cloud, self.log, self.args)

            self.assertEqual(self.mock_add.call_count, 0)
            self.assertEqual(self.mock_update.call_count, 1)
            self.assertEqual(self.mock_remove.call_count, 1)

    def test_no_remove_defaults_if_false(self):
        """Test remove_defaults is not called when config value is False."""
        config = {"ca-certs": {"remove-defaults": False}}

        for distro_name in cc_ca_certs.distros:
            self._mock_init()
            cloud = self._get_cloud(distro_name)
            cc_ca_certs.handle(self.name, config, cloud, self.log, self.args)

            self.assertEqual(self.mock_add.call_count, 0)
            self.assertEqual(self.mock_update.call_count, 1)
            self.assertEqual(self.mock_remove.call_count, 0)

    def test_correct_order_for_remove_then_add(self):
        """Test remove_defaults is not called when config value is False."""
        config = {"ca-certs": {"remove-defaults": True, "trusted": ["CERT1"]}}

        for distro_name in cc_ca_certs.distros:
            self._mock_init()
            cloud = self._get_cloud(distro_name)
            conf = cc_ca_certs._distro_ca_certs_configs(distro_name)
            cc_ca_certs.handle(self.name, config, cloud, self.log, self.args)

            self.mock_add.assert_called_once_with(conf, ['CERT1'])
            self.assertEqual(self.mock_update.call_count, 1)
            self.assertEqual(self.mock_remove.call_count, 1)


class TestAddCaCerts(TestCase):

    def setUp(self):
        super(TestAddCaCerts, self).setUp()
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir)
        self.paths = helpers.Paths({
            'cloud_dir': tmpdir,
        })
        self.add_patch("cloudinit.config.cc_ca_certs.os.stat", "m_stat")

    def _fetch_distro(self, kind):
        cls = distros.fetch(kind)
        paths = helpers.Paths({})
        return cls(kind, {}, paths)

    def test_no_certs_in_list(self):
        """Test that no certificate are written if not provided."""
        for distro_name in cc_ca_certs.distros:
            conf = cc_ca_certs._distro_ca_certs_configs(distro_name)
            with mock.patch.object(util, 'write_file') as mockobj:
                cc_ca_certs.add_ca_certs(conf, [])
            self.assertEqual(mockobj.call_count, 0)

    def test_single_cert_trailing_cr(self):
        """Test adding a single certificate to the trusted CAs
        when existing ca-certificates has trailing newline"""
        cert = "CERT1\nLINE2\nLINE3"

        ca_certs_content = "line1\nline2\ncloud-init-ca-certs.crt\nline3\n"
        expected = "line1\nline2\nline3\ncloud-init-ca-certs.crt\n"

        self.m_stat.return_value.st_size = 1

        for distro_name in cc_ca_certs.distros:
            conf = cc_ca_certs._distro_ca_certs_configs(distro_name)

            with ExitStack() as mocks:
                mock_write = mocks.enter_context(
                    mock.patch.object(util, 'write_file'))
                mock_load = mocks.enter_context(
                    mock.patch.object(util, 'load_file',
                                      return_value=ca_certs_content))

                cc_ca_certs.add_ca_certs(conf, [cert])

                mock_write.assert_has_calls([
                    mock.call(conf['ca_cert_full_path'],
                              cert, mode=0o644)])
                if conf['ca_cert_config'] is not None:
                    mock_write.assert_has_calls([
                        mock.call(conf['ca_cert_config'],
                                  expected, omode="wb")])
                    mock_load.assert_called_once_with(conf['ca_cert_config'])

    def test_single_cert_no_trailing_cr(self):
        """Test adding a single certificate to the trusted CAs
        when existing ca-certificates has no trailing newline"""
        cert = "CERT1\nLINE2\nLINE3"

        ca_certs_content = "line1\nline2\nline3"

        self.m_stat.return_value.st_size = 1

        for distro_name in cc_ca_certs.distros:
            conf = cc_ca_certs._distro_ca_certs_configs(distro_name)

            with ExitStack() as mocks:
                mock_write = mocks.enter_context(
                    mock.patch.object(util, 'write_file'))
                mock_load = mocks.enter_context(
                    mock.patch.object(util, 'load_file',
                                      return_value=ca_certs_content))

                cc_ca_certs.add_ca_certs(conf, [cert])

                mock_write.assert_has_calls([
                    mock.call(conf['ca_cert_full_path'],
                              cert, mode=0o644)])
                if conf['ca_cert_config'] is not None:
                    mock_write.assert_has_calls([
                        mock.call(conf['ca_cert_config'],
                                  "%s\n%s\n" % (ca_certs_content,
                                                conf['ca_cert_filename']),
                                  omode="wb")])

                    mock_load.assert_called_once_with(conf['ca_cert_config'])

    def test_single_cert_to_empty_existing_ca_file(self):
        """Test adding a single certificate to the trusted CAs
        when existing ca-certificates.conf is empty"""
        cert = "CERT1\nLINE2\nLINE3"

        expected = "cloud-init-ca-certs.crt\n"

        self.m_stat.return_value.st_size = 0

        for distro_name in cc_ca_certs.distros:
            conf = cc_ca_certs._distro_ca_certs_configs(distro_name)
            with mock.patch.object(util, 'write_file',
                                   autospec=True) as m_write:

                cc_ca_certs.add_ca_certs(conf, [cert])

                m_write.assert_has_calls([
                    mock.call(conf['ca_cert_full_path'],
                              cert, mode=0o644)])
                if conf['ca_cert_config'] is not None:
                    m_write.assert_has_calls([
                        mock.call(conf['ca_cert_config'],
                                  expected, omode="wb")])

    def test_multiple_certs(self):
        """Test adding multiple certificates to the trusted CAs."""
        certs = ["CERT1\nLINE2\nLINE3", "CERT2\nLINE2\nLINE3"]
        expected_cert_file = "\n".join(certs)
        ca_certs_content = "line1\nline2\nline3"

        self.m_stat.return_value.st_size = 1

        for distro_name in cc_ca_certs.distros:
            conf = cc_ca_certs._distro_ca_certs_configs(distro_name)

            with ExitStack() as mocks:
                mock_write = mocks.enter_context(
                    mock.patch.object(util, 'write_file'))
                mock_load = mocks.enter_context(
                    mock.patch.object(util, 'load_file',
                                      return_value=ca_certs_content))

                cc_ca_certs.add_ca_certs(conf, certs)

                mock_write.assert_has_calls([
                    mock.call(conf['ca_cert_full_path'],
                              expected_cert_file, mode=0o644)])
                if conf['ca_cert_config'] is not None:
                    mock_write.assert_has_calls([
                        mock.call(conf['ca_cert_config'],
                                  "%s\n%s\n" % (ca_certs_content,
                                                conf['ca_cert_filename']),
                                  omode='wb')])

                    mock_load.assert_called_once_with(conf['ca_cert_config'])


class TestUpdateCaCerts(unittest.TestCase):
    def test_commands(self):
        for distro_name in cc_ca_certs.distros:
            conf = cc_ca_certs._distro_ca_certs_configs(distro_name)
            with mock.patch.object(subp, 'subp') as mockobj:
                cc_ca_certs.update_ca_certs(conf)
                mockobj.assert_called_once_with(
                    conf['ca_cert_update_cmd'], capture=False)


class TestRemoveDefaultCaCerts(TestCase):

    def setUp(self):
        super(TestRemoveDefaultCaCerts, self).setUp()
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir)
        self.paths = helpers.Paths({
            'cloud_dir': tmpdir,
        })

    def test_commands(self):
        for distro_name in cc_ca_certs.distros:
            conf = cc_ca_certs._distro_ca_certs_configs(distro_name)

            with ExitStack() as mocks:
                mock_delete = mocks.enter_context(
                    mock.patch.object(util, 'delete_dir_contents'))
                mock_write = mocks.enter_context(
                    mock.patch.object(util, 'write_file'))
                mock_subp = mocks.enter_context(
                    mock.patch.object(subp, 'subp'))

                cc_ca_certs.remove_default_ca_certs(distro_name, conf)

                mock_delete.assert_has_calls([
                    mock.call(conf['ca_cert_path']),
                    mock.call(conf['ca_cert_system_path'])])

                if conf['ca_cert_config'] is not None:
                    mock_write.assert_called_once_with(
                        conf['ca_cert_config'], "", mode=0o644)

                if distro_name in ['debian', 'ubuntu']:
                    mock_subp.assert_called_once_with(
                        ('debconf-set-selections', '-'),
                        "ca-certificates \
ca-certificates/trust_new_crts select no")

# vi: ts=4 expandtab
