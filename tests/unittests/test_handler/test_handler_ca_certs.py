# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import cloud
from cloudinit.config import cc_ca_certs
from cloudinit import helpers
from cloudinit import util

from ..helpers import TestCase

import logging
import shutil
import tempfile
import unittest

try:
    from unittest import mock
except ImportError:
    import mock
try:
    from contextlib import ExitStack
except ImportError:
    from contextlib2 import ExitStack


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
        self.cloud = cloud.Cloud(None, self.paths, None, None, None)
        self.log = logging.getLogger("TestNoConfig")
        self.args = []

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

        cc_ca_certs.handle(self.name, config, self.cloud, self.log, self.args)

        self.assertEqual(self.mock_add.call_count, 0)
        self.assertEqual(self.mock_update.call_count, 1)
        self.assertEqual(self.mock_remove.call_count, 0)

    def test_empty_trusted_list(self):
        """Test that no certificate are written if 'trusted' list is empty."""
        config = {"ca-certs": {"trusted": []}}

        cc_ca_certs.handle(self.name, config, self.cloud, self.log, self.args)

        self.assertEqual(self.mock_add.call_count, 0)
        self.assertEqual(self.mock_update.call_count, 1)
        self.assertEqual(self.mock_remove.call_count, 0)

    def test_single_trusted(self):
        """Test that a single cert gets passed to add_ca_certs."""
        config = {"ca-certs": {"trusted": ["CERT1"]}}

        cc_ca_certs.handle(self.name, config, self.cloud, self.log, self.args)

        self.mock_add.assert_called_once_with(['CERT1'])
        self.assertEqual(self.mock_update.call_count, 1)
        self.assertEqual(self.mock_remove.call_count, 0)

    def test_multiple_trusted(self):
        """Test that multiple certs get passed to add_ca_certs."""
        config = {"ca-certs": {"trusted": ["CERT1", "CERT2"]}}

        cc_ca_certs.handle(self.name, config, self.cloud, self.log, self.args)

        self.mock_add.assert_called_once_with(['CERT1', 'CERT2'])
        self.assertEqual(self.mock_update.call_count, 1)
        self.assertEqual(self.mock_remove.call_count, 0)

    def test_remove_default_ca_certs(self):
        """Test remove_defaults works as expected."""
        config = {"ca-certs": {"remove-defaults": True}}

        cc_ca_certs.handle(self.name, config, self.cloud, self.log, self.args)

        self.assertEqual(self.mock_add.call_count, 0)
        self.assertEqual(self.mock_update.call_count, 1)
        self.assertEqual(self.mock_remove.call_count, 1)

    def test_no_remove_defaults_if_false(self):
        """Test remove_defaults is not called when config value is False."""
        config = {"ca-certs": {"remove-defaults": False}}

        cc_ca_certs.handle(self.name, config, self.cloud, self.log, self.args)

        self.assertEqual(self.mock_add.call_count, 0)
        self.assertEqual(self.mock_update.call_count, 1)
        self.assertEqual(self.mock_remove.call_count, 0)

    def test_correct_order_for_remove_then_add(self):
        """Test remove_defaults is not called when config value is False."""
        config = {"ca-certs": {"remove-defaults": True, "trusted": ["CERT1"]}}

        cc_ca_certs.handle(self.name, config, self.cloud, self.log, self.args)

        self.mock_add.assert_called_once_with(['CERT1'])
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

    def test_no_certs_in_list(self):
        """Test that no certificate are written if not provided."""
        with mock.patch.object(util, 'write_file') as mockobj:
            cc_ca_certs.add_ca_certs([])
        self.assertEqual(mockobj.call_count, 0)

    def test_single_cert_trailing_cr(self):
        """Test adding a single certificate to the trusted CAs
        when existing ca-certificates has trailing newline"""
        cert = "CERT1\nLINE2\nLINE3"

        ca_certs_content = "line1\nline2\ncloud-init-ca-certs.crt\nline3\n"
        expected = "line1\nline2\nline3\ncloud-init-ca-certs.crt\n"

        with ExitStack() as mocks:
            mock_write = mocks.enter_context(
                mock.patch.object(util, 'write_file'))
            mock_load = mocks.enter_context(
                mock.patch.object(util, 'load_file',
                                  return_value=ca_certs_content))

            cc_ca_certs.add_ca_certs([cert])

            mock_write.assert_has_calls([
                mock.call("/usr/share/ca-certificates/cloud-init-ca-certs.crt",
                          cert, mode=0o644),
                mock.call("/etc/ca-certificates.conf", expected, omode="wb")])
            mock_load.assert_called_once_with("/etc/ca-certificates.conf")

    def test_single_cert_no_trailing_cr(self):
        """Test adding a single certificate to the trusted CAs
        when existing ca-certificates has no trailing newline"""
        cert = "CERT1\nLINE2\nLINE3"

        ca_certs_content = "line1\nline2\nline3"

        with ExitStack() as mocks:
            mock_write = mocks.enter_context(
                mock.patch.object(util, 'write_file'))
            mock_load = mocks.enter_context(
                mock.patch.object(util, 'load_file',
                                  return_value=ca_certs_content))

            cc_ca_certs.add_ca_certs([cert])

            mock_write.assert_has_calls([
                mock.call("/usr/share/ca-certificates/cloud-init-ca-certs.crt",
                          cert, mode=0o644),
                mock.call("/etc/ca-certificates.conf",
                          "%s\n%s\n" % (ca_certs_content,
                                        "cloud-init-ca-certs.crt"),
                          omode="wb")])

            mock_load.assert_called_once_with("/etc/ca-certificates.conf")

    def test_multiple_certs(self):
        """Test adding multiple certificates to the trusted CAs."""
        certs = ["CERT1\nLINE2\nLINE3", "CERT2\nLINE2\nLINE3"]
        expected_cert_file = "\n".join(certs)
        ca_certs_content = "line1\nline2\nline3"

        with ExitStack() as mocks:
            mock_write = mocks.enter_context(
                mock.patch.object(util, 'write_file'))
            mock_load = mocks.enter_context(
                mock.patch.object(util, 'load_file',
                                  return_value=ca_certs_content))

            cc_ca_certs.add_ca_certs(certs)

            mock_write.assert_has_calls([
                mock.call("/usr/share/ca-certificates/cloud-init-ca-certs.crt",
                          expected_cert_file, mode=0o644),
                mock.call("/etc/ca-certificates.conf",
                          "%s\n%s\n" % (ca_certs_content,
                                        "cloud-init-ca-certs.crt"),
                          omode='wb')])

            mock_load.assert_called_once_with("/etc/ca-certificates.conf")


class TestUpdateCaCerts(unittest.TestCase):
    def test_commands(self):
        with mock.patch.object(util, 'subp') as mockobj:
            cc_ca_certs.update_ca_certs()
            mockobj.assert_called_once_with(
                ["update-ca-certificates"], capture=False)


class TestRemoveDefaultCaCerts(TestCase):

    def setUp(self):
        super(TestRemoveDefaultCaCerts, self).setUp()
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir)
        self.paths = helpers.Paths({
            'cloud_dir': tmpdir,
        })

    def test_commands(self):
        with ExitStack() as mocks:
            mock_delete = mocks.enter_context(
                mock.patch.object(util, 'delete_dir_contents'))
            mock_write = mocks.enter_context(
                mock.patch.object(util, 'write_file'))
            mock_subp = mocks.enter_context(mock.patch.object(util, 'subp'))

            cc_ca_certs.remove_default_ca_certs()

            mock_delete.assert_has_calls([
                mock.call("/usr/share/ca-certificates/"),
                mock.call("/etc/ssl/certs/")])

            mock_write.assert_called_once_with(
                "/etc/ca-certificates.conf", "", mode=0o644)

            mock_subp.assert_called_once_with(
                ('debconf-set-selections', '-'),
                "ca-certificates ca-certificates/trust_new_crts select no")

# vi: ts=4 expandtab
