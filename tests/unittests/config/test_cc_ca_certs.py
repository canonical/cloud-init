# This file is part of cloud-init. See LICENSE file for license information.
import re
import shutil
import tempfile
import unittest
from contextlib import ExitStack
from unittest import mock

import pytest

from cloudinit import distros, helpers
from cloudinit import log as logger
from cloudinit import subp, util
from cloudinit.config import cc_ca_certs
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import TestCase, skipUnlessJsonSchema
from tests.unittests.util import get_cloud


class TestNoConfig(unittest.TestCase):
    def setUp(self):
        super(TestNoConfig, self).setUp()
        self.name = "ca_certs"
        self.cloud_init = None
        self.args = []

    def test_no_config(self):
        """
        Test that nothing is done if no ca-certs configuration is provided.
        """
        config = util.get_builtin_cfg()
        with ExitStack() as mocks:
            util_mock = mocks.enter_context(
                mock.patch.object(util, "write_file")
            )
            certs_mock = mocks.enter_context(
                mock.patch.object(cc_ca_certs, "update_ca_certs")
            )

            cc_ca_certs.handle(self.name, config, self.cloud_init, self.args)

            self.assertEqual(util_mock.call_count, 0)
            self.assertEqual(certs_mock.call_count, 0)


class TestConfig(TestCase):
    def setUp(self):
        super(TestConfig, self).setUp()
        self.name = "ca_certs"
        self.paths = None
        self.args = []

    def _fetch_distro(self, kind):
        cls = distros.fetch(kind)
        paths = helpers.Paths({})
        return cls(kind, {}, paths)

    def _mock_init(self):
        self.mocks = ExitStack()
        self.addCleanup(self.mocks.close)

        # Mock out the functions that actually modify the system
        self.mock_add = self.mocks.enter_context(
            mock.patch.object(cc_ca_certs, "add_ca_certs")
        )
        self.mock_update = self.mocks.enter_context(
            mock.patch.object(cc_ca_certs, "update_ca_certs")
        )
        self.mock_remove = self.mocks.enter_context(
            mock.patch.object(cc_ca_certs, "disable_default_ca_certs")
        )

    @mock.patch(
        "cloudinit.distros.networking.subp.subp",
        return_value=("", None),
    )
    def test_no_trusted_list(self, _):
        """
        Test that no certificates are written if the 'trusted' key is not
        present.
        """
        config = {"ca_certs": {}}

        for distro_name in cc_ca_certs.distros:
            self._mock_init()
            cloud = get_cloud(distro_name)
            cc_ca_certs.handle(self.name, config, cloud, self.args)

            self.assertEqual(self.mock_add.call_count, 0)
            self.assertEqual(self.mock_update.call_count, 1)
            self.assertEqual(self.mock_remove.call_count, 0)

    @mock.patch(
        "cloudinit.distros.networking.subp.subp",
        return_value=("", None),
    )
    def test_empty_trusted_list(self, _):
        """Test that no certificate are written if 'trusted' list is empty."""
        config = {"ca_certs": {"trusted": []}}

        for distro_name in cc_ca_certs.distros:
            self._mock_init()
            cloud = get_cloud(distro_name)
            cc_ca_certs.handle(self.name, config, cloud, self.args)

            self.assertEqual(self.mock_add.call_count, 0)
            self.assertEqual(self.mock_update.call_count, 1)
            self.assertEqual(self.mock_remove.call_count, 0)

    @mock.patch(
        "cloudinit.distros.networking.subp.subp",
        return_value=("", None),
    )
    def test_single_trusted(self, _):
        """Test that a single cert gets passed to add_ca_certs."""
        config = {"ca_certs": {"trusted": ["CERT1"]}}

        for distro_name in cc_ca_certs.distros:
            self._mock_init()
            cloud = get_cloud(distro_name)
            conf = cc_ca_certs._distro_ca_certs_configs(distro_name)
            cc_ca_certs.handle(self.name, config, cloud, self.args)

            self.mock_add.assert_called_once_with(conf, ["CERT1"])
            self.assertEqual(self.mock_update.call_count, 1)
            self.assertEqual(self.mock_remove.call_count, 0)

    @mock.patch(
        "cloudinit.distros.networking.subp.subp",
        return_value=("", None),
    )
    def test_multiple_trusted(self, _):
        """Test that multiple certs get passed to add_ca_certs."""
        config = {"ca_certs": {"trusted": ["CERT1", "CERT2"]}}

        for distro_name in cc_ca_certs.distros:
            self._mock_init()
            cloud = get_cloud(distro_name)
            conf = cc_ca_certs._distro_ca_certs_configs(distro_name)
            cc_ca_certs.handle(self.name, config, cloud, self.args)

            self.mock_add.assert_called_once_with(conf, ["CERT1", "CERT2"])
            self.assertEqual(self.mock_update.call_count, 1)
            self.assertEqual(self.mock_remove.call_count, 0)

    @mock.patch(
        "cloudinit.distros.networking.subp.subp",
        return_value=("", None),
    )
    def test_remove_default_ca_certs(self, _):
        """Test remove_defaults works as expected."""
        config = {"ca_certs": {"remove_defaults": True}}

        for distro_name in cc_ca_certs.distros:
            self._mock_init()
            cloud = get_cloud(distro_name)
            cc_ca_certs.handle(self.name, config, cloud, self.args)

            self.assertEqual(self.mock_add.call_count, 0)
            self.assertEqual(self.mock_update.call_count, 1)
            self.assertEqual(self.mock_remove.call_count, 1)

    @mock.patch(
        "cloudinit.distros.networking.subp.subp",
        return_value=("", None),
    )
    def test_no_remove_defaults_if_false(self, _):
        """Test remove_defaults is not called when config value is False."""
        config = {"ca_certs": {"remove_defaults": False}}

        for distro_name in cc_ca_certs.distros:
            self._mock_init()
            cloud = get_cloud(distro_name)
            cc_ca_certs.handle(self.name, config, cloud, self.args)

            self.assertEqual(self.mock_add.call_count, 0)
            self.assertEqual(self.mock_update.call_count, 1)
            self.assertEqual(self.mock_remove.call_count, 0)

    @mock.patch(
        "cloudinit.distros.networking.subp.subp",
        return_value=("", None),
    )
    def test_correct_order_for_remove_then_add(self, _):
        """
        Test remove_defaults is called before add.
        """
        config = {"ca_certs": {"remove_defaults": True, "trusted": ["CERT1"]}}

        for distro_name in cc_ca_certs.distros:
            self._mock_init()
            cloud = get_cloud(distro_name)
            conf = cc_ca_certs._distro_ca_certs_configs(distro_name)
            cc_ca_certs.handle(self.name, config, cloud, self.args)

            self.assertEqual(self.mock_remove.call_count, 1)
            self.mock_add.assert_called_once_with(conf, ["CERT1"])
            self.assertEqual(self.mock_update.call_count, 1)


class TestAddCaCerts(TestCase):
    def setUp(self):
        super(TestAddCaCerts, self).setUp()
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir)
        self.paths = helpers.Paths(
            {
                "cloud_dir": tmpdir,
            }
        )
        self.add_patch("cloudinit.config.cc_ca_certs.os.stat", "m_stat")

    def _fetch_distro(self, kind):
        cls = distros.fetch(kind)
        paths = helpers.Paths({})
        return cls(kind, {}, paths)

    def test_no_certs_in_list(self):
        """Test that no certificate are written if not provided."""
        for distro_name in cc_ca_certs.distros:
            conf = cc_ca_certs._distro_ca_certs_configs(distro_name)
            with mock.patch.object(util, "write_file") as mockobj:
                cc_ca_certs.add_ca_certs(conf, [])
            self.assertEqual(mockobj.call_count, 0)

    def test_single_cert(self):
        """Test adding a single certificate to the trusted CAs."""
        cert = "CERT1\nLINE2\nLINE3"

        self.m_stat.return_value.st_size = 1

        for distro_name in cc_ca_certs.distros:
            conf = cc_ca_certs._distro_ca_certs_configs(distro_name)

            with ExitStack() as mocks:
                mock_write = mocks.enter_context(
                    mock.patch.object(util, "write_file")
                )

                cc_ca_certs.add_ca_certs(conf, [cert])

                mock_write.assert_has_calls(
                    [
                        mock.call(
                            conf["ca_cert_full_path"].format(cert_index=1),
                            cert,
                            mode=0o644,
                        )
                    ]
                )

    def test_multiple_certs(self):
        """Test adding multiple certificates to the trusted CAs."""
        certs = ["CERT1\nLINE2\nLINE3", "CERT2\nLINE2\nLINE3"]
        expected_cert_1_file = certs[0]
        expected_cert_2_file = certs[1]

        self.m_stat.return_value.st_size = 1

        for distro_name in cc_ca_certs.distros:
            conf = cc_ca_certs._distro_ca_certs_configs(distro_name)

            with ExitStack() as mocks:
                mock_write = mocks.enter_context(
                    mock.patch.object(util, "write_file")
                )

                cc_ca_certs.add_ca_certs(conf, certs)

                mock_write.assert_has_calls(
                    [
                        mock.call(
                            conf["ca_cert_full_path"].format(cert_index=1),
                            expected_cert_1_file,
                            mode=0o644,
                        ),
                        mock.call(
                            conf["ca_cert_full_path"].format(cert_index=2),
                            expected_cert_2_file,
                            mode=0o644,
                        ),
                    ]
                )


class TestUpdateCaCerts(unittest.TestCase):
    def test_commands(self):
        for distro_name in cc_ca_certs.distros:
            conf = cc_ca_certs._distro_ca_certs_configs(distro_name)
            with mock.patch.object(subp, "subp") as mockobj:
                cc_ca_certs.update_ca_certs(conf)
                mockobj.assert_called_once_with(
                    conf["ca_cert_update_cmd"], capture=False
                )


class TestRemoveDefaultCaCerts(TestCase):
    def setUp(self):
        super(TestRemoveDefaultCaCerts, self).setUp()
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir)
        self.paths = helpers.Paths(
            {
                "cloud_dir": tmpdir,
            }
        )
        self.add_patch("cloudinit.config.cc_ca_certs.os.stat", "m_stat")

    def test_commands(self):
        ca_certs_content = "# line1\nline2\nline3\n"
        expected = (
            "# line1\n# Modified by cloud-init to deselect certs due to"
            " user-data\n!line2\n!line3\n"
        )
        self.m_stat.return_value.st_size = 1

        for distro_name in cc_ca_certs.distros:
            conf = cc_ca_certs._distro_ca_certs_configs(distro_name)

            with ExitStack() as mocks:
                mock_delete = mocks.enter_context(
                    mock.patch.object(util, "delete_dir_contents")
                )
                mock_load = mocks.enter_context(
                    mock.patch.object(
                        util, "load_file", return_value=ca_certs_content
                    )
                )
                mock_subp = mocks.enter_context(
                    mock.patch.object(subp, "subp")
                )
                mock_write = mocks.enter_context(
                    mock.patch.object(util, "write_file")
                )

                cc_ca_certs.disable_default_ca_certs(distro_name, conf)

                if distro_name == "rhel":
                    mock_delete.assert_has_calls(
                        [
                            mock.call(conf["ca_cert_path"]),
                            mock.call(conf["ca_cert_local_path"]),
                        ]
                    )
                    self.assertEqual([], mock_subp.call_args_list)
                elif distro_name in ["alpine", "debian", "ubuntu"]:
                    mock_load.assert_called_once_with(conf["ca_cert_config"])
                    mock_write.assert_called_once_with(
                        conf["ca_cert_config"], expected, omode="wb"
                    )

                    if distro_name in ["debian", "ubuntu"]:
                        mock_subp.assert_called_once_with(
                            ("debconf-set-selections", "-"),
                            data=(
                                "ca-certificates ca-certificates/"
                                "trust_new_crts select no"
                            ),
                        )
                    else:
                        assert mock_subp.call_count == 0

    def test_non_existent_cert_cfg(self):
        self.m_stat.return_value.st_size = 0

        for distro_name in cc_ca_certs.distros:
            conf = cc_ca_certs._distro_ca_certs_configs(distro_name)
            with ExitStack() as mocks:
                mocks.enter_context(
                    mock.patch.object(util, "delete_dir_contents")
                )
                mocks.enter_context(mock.patch.object(subp, "subp"))
                cc_ca_certs.disable_default_ca_certs(distro_name, conf)


class TestCACertsSchema:
    """Directly test schema rather than through handle."""

    @pytest.mark.parametrize(
        "config, error_msg",
        (
            # Valid, yet deprecated schemas
            (
                {"ca-certs": {"remove-defaults": True}},
                "Cloud config schema deprecations: ca-certs:  "
                "Deprecated in version 22.3. Use ``ca_certs`` instead.,"
                " ca-certs.remove-defaults:  Deprecated in version 22.3"
                ". Use ``remove_defaults`` instead.",
            ),
            # Invalid schemas
            (
                {"ca_certs": 1},
                "ca_certs: 1 is not of type 'object'",
            ),
            (
                {"ca_certs": {}},
                re.escape("ca_certs: {} does not have enough properties"),
            ),
            (
                {"ca_certs": {"boguskey": 1}},
                re.escape(
                    "ca_certs: Additional properties are not allowed"
                    " ('boguskey' was unexpected)"
                ),
            ),
            (
                {"ca_certs": {"remove_defaults": 1}},
                "ca_certs.remove_defaults: 1 is not of type 'boolean'",
            ),
            (
                {"ca_certs": {"trusted": [1]}},
                "ca_certs.trusted.0: 1 is not of type 'string'",
            ),
            (
                {"ca_certs": {"trusted": []}},
                re.escape("ca_certs.trusted: [] is too short"),
            ),
        ),
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        """Assert expected schema validation and error messages."""
        # New-style schema $defs exist in config/cloud-init-schema*.json
        schema = get_schema()
        if error_msg is None:
            validate_cloudconfig_schema(config, schema, strict=True)
        else:
            with pytest.raises(SchemaValidationError, match=error_msg):
                validate_cloudconfig_schema(config, schema, strict=True)

    @mock.patch.object(cc_ca_certs, "update_ca_certs")
    def test_deprecate_key_warnings(self, update_ca_certs, caplog):
        """Assert warnings are logged for deprecated keys."""
        logger.setup_logging()
        cloud = get_cloud("ubuntu")
        cc_ca_certs.handle(
            "IGNORE", {"ca-certs": {"remove-defaults": False}}, cloud, []
        )
        expected_warnings = [
            "Key 'ca-certs' is deprecated in",
            "Key 'remove-defaults' is deprecated in",
        ]
        for warning in expected_warnings:
            assert warning in caplog.text
            assert "deprecat" in caplog.text
        assert 1 == update_ca_certs.call_count

    @mock.patch.object(cc_ca_certs, "update_ca_certs")
    def test_duplicate_keys(self, update_ca_certs, caplog):
        """Assert warnings are logged for deprecated keys."""
        cloud = get_cloud("ubuntu")
        cc_ca_certs.handle(
            "IGNORE",
            {
                "ca-certs": {"remove-defaults": True},
                "ca_certs": {"remove_defaults": False},
            },
            cloud,
            [],
        )
        expected_warning = (
            "Found both ca-certs (deprecated) and ca_certs config keys."
            " Ignoring ca-certs."
        )
        assert expected_warning in caplog.text
        assert 1 == update_ca_certs.call_count
