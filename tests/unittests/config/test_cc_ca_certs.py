# This file is part of cloud-init. See LICENSE file for license information.
# pylint: disable=attribute-defined-outside-init
import copy
import os
import re
from typing import List
from unittest import mock

import pytest

from cloudinit import distros, helpers, subp, util
from cloudinit.config import Config, cc_ca_certs
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import SCHEMA_EMPTY_ERROR, skipUnlessJsonSchema
from tests.unittests.util import get_cloud

ALL_DISTRO_NAMES = sorted(
    {name for family in distros.OSFAMILIES.values() for name in family}
)


class TestNoConfig:
    def test_no_config(self):
        """
        Test that nothing is done if no ca-certs configuration is provided.
        """
        name = "ca_certs"
        cloud_init = get_cloud("ubuntu")
        args: List[str] = []

        config = util.get_builtin_cfg()
        with mock.patch.object(util, "write_file") as util_mock:
            with mock.patch.object(
                cc_ca_certs, "update_ca_certs"
            ) as certs_mock:
                cc_ca_certs.handle(name, config, cloud_init, args)

                assert util_mock.call_count == 0
                assert certs_mock.call_count == 0


class TestConfig:
    name = "ca_certs"
    paths = None
    args: List = []

    @pytest.mark.parametrize("distro_name", ALL_DISTRO_NAMES)
    def test_distro_config(self, distro_name):
        profile = "debian"
        if distro_name in cc_ca_certs.distros:
            if distro_name in ("aosc", "photon"):
                profile = distro_name
            elif distro_name in distros.OSFAMILIES["redhat"]:
                profile = "rhel"
            elif distro_name in distros.OSFAMILIES["suse"]:
                profile = "opensuse"

        expected = copy.deepcopy(
            cc_ca_certs.DISTRO_OVERRIDES.get(
                profile, cc_ca_certs.DEFAULT_CONFIG
            )
        )
        expected["ca_cert_full_path"] = os.path.join(
            expected["ca_cert_local_path"], expected["ca_cert_filename"]
        )

        assert cc_ca_certs._distro_ca_certs_configs(distro_name) == expected

    def test_supported_distros(self):
        assert set(cc_ca_certs.distros) <= set(ALL_DISTRO_NAMES)
        assert cc_ca_certs.meta["distros"] == cc_ca_certs.distros

        unsupported_distros = {
            "OpenCloudOS",
            "TencentOS",
            "arch",
            "cos",
            "dragonfly",
            "eurolinux",
            "freebsd",
            "gentoo",
            "miraclelinux",
            "netbsd",
            "openbsd",
            "openeuler",
            "openmandriva",
            "suse",
            "virtuozzo",
        }
        assert (
            set(ALL_DISTRO_NAMES) - set(cc_ca_certs.distros)
            == unsupported_distros
        )

    def _fetch_distro(self, kind):
        cls = distros.fetch(kind)
        paths = helpers.Paths({})
        return cls(kind, {}, paths)

    @pytest.fixture
    def ca_mocks(self, mocker):
        """Fixture to provide mocked ca_cert functions"""
        mock_add = mocker.patch.object(cc_ca_certs, "add_ca_certs")
        mock_update = mocker.patch.object(cc_ca_certs, "update_ca_certs")
        mock_remove = mocker.patch.object(
            cc_ca_certs, "disable_default_ca_certs"
        )
        ca_mocks = mock.Mock()
        ca_mocks.attach_mock(mock_add, "add")
        ca_mocks.attach_mock(mock_update, "update")
        ca_mocks.attach_mock(mock_remove, "remove")
        return ca_mocks

    @pytest.mark.parametrize("distro_name", cc_ca_certs.distros)
    @mock.patch(
        "cloudinit.distros.networking.subp.subp",
        return_value=("", None),
    )
    def test_no_trusted_list(self, _, distro_name, ca_mocks):
        """
        Test that no certificates are written if the 'trusted' key is not
        present.
        """
        config: Config = {"ca_certs": {}}
        cloud = get_cloud(distro_name)
        cc_ca_certs.handle(self.name, config, cloud, self.args)

        assert ca_mocks.add.call_count == 0
        assert ca_mocks.update.call_count == 1
        assert ca_mocks.remove.call_count == 0

    @pytest.mark.parametrize("distro_name", cc_ca_certs.distros)
    @mock.patch(
        "cloudinit.distros.networking.subp.subp",
        return_value=("", None),
    )
    def test_empty_trusted_list(self, _, distro_name, ca_mocks):
        """Test that no certificate are written if 'trusted' list is empty."""
        config: Config = {"ca_certs": {"trusted": []}}
        cloud = get_cloud(distro_name)
        cc_ca_certs.handle(self.name, config, cloud, self.args)

        assert ca_mocks.add.call_count == 0
        assert ca_mocks.update.call_count == 1
        assert ca_mocks.remove.call_count == 0

    @pytest.mark.parametrize("distro_name", cc_ca_certs.distros)
    @mock.patch(
        "cloudinit.distros.networking.subp.subp",
        return_value=("", None),
    )
    def test_single_trusted(self, _, distro_name, ca_mocks):
        """Test that a single cert gets passed to add_ca_certs."""
        config = {"ca_certs": {"trusted": ["CERT1"]}}
        cloud = get_cloud(distro_name)
        conf = cc_ca_certs._distro_ca_certs_configs(distro_name)
        cc_ca_certs.handle(self.name, config, cloud, self.args)

        ca_mocks.add.assert_called_once_with(conf, ["CERT1"])
        assert ca_mocks.update.call_count == 1
        assert ca_mocks.remove.call_count == 0

    @pytest.mark.parametrize("distro_name", cc_ca_certs.distros)
    @mock.patch(
        "cloudinit.distros.networking.subp.subp",
        return_value=("", None),
    )
    def test_multiple_trusted(self, _, distro_name, ca_mocks):
        """Test that multiple certs get passed to add_ca_certs."""
        config = {"ca_certs": {"trusted": ["CERT1", "CERT2"]}}
        cloud = get_cloud(distro_name)
        conf = cc_ca_certs._distro_ca_certs_configs(distro_name)
        cc_ca_certs.handle(self.name, config, cloud, self.args)

        ca_mocks.add.assert_called_once_with(conf, ["CERT1", "CERT2"])
        assert ca_mocks.update.call_count == 1
        assert ca_mocks.remove.call_count == 0

    @pytest.mark.parametrize("distro_name", cc_ca_certs.distros)
    @mock.patch(
        "cloudinit.distros.networking.subp.subp",
        return_value=("", None),
    )
    def test_remove_default_ca_certs(self, _, distro_name, ca_mocks):
        """Test remove_defaults works as expected."""
        config = {"ca_certs": {"remove_defaults": True}}
        cloud = get_cloud(distro_name)
        cc_ca_certs.handle(self.name, config, cloud, self.args)

        assert ca_mocks.add.call_count == 0
        assert ca_mocks.update.call_count == 1
        assert ca_mocks.remove.call_count == 1

    @pytest.mark.parametrize("distro_name", cc_ca_certs.distros)
    @mock.patch(
        "cloudinit.distros.networking.subp.subp",
        return_value=("", None),
    )
    def test_no_remove_defaults_if_false(self, _, distro_name, ca_mocks):
        """Test remove_defaults is not called when config value is False."""
        config = {"ca_certs": {"remove_defaults": False}}
        cloud = get_cloud(distro_name)
        cc_ca_certs.handle(self.name, config, cloud, self.args)

        assert ca_mocks.add.call_count == 0
        assert ca_mocks.update.call_count == 1
        assert ca_mocks.remove.call_count == 0

    @pytest.mark.parametrize("distro_name", cc_ca_certs.distros)
    @mock.patch(
        "cloudinit.distros.networking.subp.subp",
        return_value=("", None),
    )
    def test_correct_order_for_remove_then_add(self, _, distro_name, ca_mocks):
        """
        Test remove_defaults is called before add.
        """
        config = {"ca_certs": {"remove_defaults": True, "trusted": ["CERT1"]}}
        cloud = get_cloud(distro_name)
        conf = cc_ca_certs._distro_ca_certs_configs(distro_name)

        cc_ca_certs.handle(self.name, config, cloud, self.args)

        assert ca_mocks.mock_calls == [
            mock.call.remove(distro_name, conf),
            mock.call.add(conf, ["CERT1"]),
            mock.call.update(conf),
        ]


class TestAddCaCerts:
    @pytest.fixture
    def setup_test(self, tmp_path, mocker):
        """Fixture to set up test environment"""
        paths = helpers.Paths(
            {
                "cloud_dir": str(tmp_path),
            }
        )
        m_stat = mocker.patch("cloudinit.config.cc_ca_certs.os.stat")
        return paths, m_stat

    def _fetch_distro(self, kind):
        cls = distros.fetch(kind)
        paths = helpers.Paths({})
        return cls(kind, {}, paths)

    @pytest.mark.parametrize("distro_name", cc_ca_certs.distros)
    def test_no_certs_in_list(self, distro_name):
        """Test that no certificate are written if not provided."""
        conf = cc_ca_certs._distro_ca_certs_configs(distro_name)
        with mock.patch.object(util, "write_file") as mockobj:
            cc_ca_certs.add_ca_certs(conf, [])
        assert mockobj.call_count == 0

    @pytest.mark.parametrize("distro_name", cc_ca_certs.distros)
    def test_single_cert(self, distro_name, setup_test):
        """Test adding a single certificate to the trusted CAs."""
        _, m_stat = setup_test
        cert = "CERT1\nLINE2\nLINE3"

        m_stat.return_value.st_size = 1
        conf = cc_ca_certs._distro_ca_certs_configs(distro_name)

        with mock.patch.object(util, "write_file") as mock_write:
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
            assert mock_write.call_count == 1

    @pytest.mark.parametrize("distro_name", cc_ca_certs.distros)
    def test_multiple_certs(self, distro_name, setup_test):
        """Test adding multiple certificates to the trusted CAs."""
        _, m_stat = setup_test
        certs = ["CERT1\nLINE2\nLINE3", "CERT2\nLINE2\nLINE3"]
        expected_cert_1_file = certs[0]
        expected_cert_2_file = certs[1]

        m_stat.return_value.st_size = 1
        conf = cc_ca_certs._distro_ca_certs_configs(distro_name)

        with mock.patch.object(util, "write_file") as mock_write:
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
            assert mock_write.call_count == 2


class TestUpdateCaCerts:
    @pytest.mark.parametrize("distro_name", cc_ca_certs.distros)
    def test_commands(self, distro_name):
        conf = cc_ca_certs._distro_ca_certs_configs(distro_name)
        with mock.patch.object(subp, "subp") as mockobj:
            cc_ca_certs.update_ca_certs(conf)
            mockobj.assert_called_once_with(
                conf["ca_cert_update_cmd"], capture=False
            )


class TestRemoveDefaultCaCerts:
    @pytest.fixture
    def setup_test(self, tmp_path, mocker):
        """Fixture to set up test environment"""
        paths = helpers.Paths(
            {
                "cloud_dir": str(tmp_path),
            }
        )
        m_stat = mocker.patch("cloudinit.config.cc_ca_certs.os.stat")
        return paths, m_stat

    @pytest.mark.parametrize("distro_name", ALL_DISTRO_NAMES)
    def test_commands(self, distro_name, setup_test):
        _, m_stat = setup_test
        ca_certs_content = "# line1\nline2\nline3\n"
        expected = (
            "# line1\n# Modified by cloud-init to deselect certs due to"
            " user-data\n!line2\n!line3\n"
        )
        m_stat.return_value.st_size = 1
        conf = cc_ca_certs._distro_ca_certs_configs(distro_name)

        with mock.patch.object(util, "delete_dir_contents") as mock_delete:
            with mock.patch.object(
                util, "load_text_file", return_value=ca_certs_content
            ) as mock_load:
                with mock.patch.object(subp, "subp") as mock_subp:
                    with mock.patch.object(util, "write_file") as mock_write:
                        calls = mock.Mock()
                        calls.attach_mock(mock_delete, "delete")
                        calls.attach_mock(mock_load, "load")
                        calls.attach_mock(mock_subp, "subp")
                        calls.attach_mock(mock_write, "write")

                        cc_ca_certs.disable_default_ca_certs(distro_name, conf)

                        if distro_name in [
                            "amazon",
                            "azurelinux",
                            "mariner",
                            "photon",
                            "rhel",
                        ]:
                            expected_calls = [
                                mock.call.delete(conf["ca_cert_path"]),
                                mock.call.delete(conf["ca_cert_local_path"]),
                            ]
                        elif distro_name in [
                            "alpine",
                            "aosc",
                            "debian",
                            "raspberry-pi-os",
                            "ubuntu",
                        ]:
                            expected_calls = [
                                mock.call.load(conf["ca_cert_config"]),
                                mock.call.write(
                                    conf["ca_cert_config"],
                                    expected,
                                    omode="wb",
                                ),
                            ]

                            if distro_name in [
                                "debian",
                                "raspberry-pi-os",
                                "ubuntu",
                            ]:
                                expected_calls.append(
                                    mock.call.subp(
                                        ["debconf-set-selections", "-"],
                                        data=(
                                            "ca-certificates "
                                            "ca-certificates/trust_new_crts "
                                            "select no"
                                        ),
                                    )
                                )
                        else:
                            expected_calls = []

                        assert calls.mock_calls == expected_calls

    @pytest.mark.parametrize("distro_name", cc_ca_certs.distros)
    def test_non_existent_cert_cfg(self, distro_name, setup_test):
        _, m_stat = setup_test
        m_stat.return_value.st_size = 0
        conf = cc_ca_certs._distro_ca_certs_configs(distro_name)

        with mock.patch.object(util, "delete_dir_contents"):
            with mock.patch.object(subp, "subp"):
                cc_ca_certs.disable_default_ca_certs(distro_name, conf)


@pytest.mark.usefixtures("clear_deprecation_log")
class TestCACertsSchema:
    """Directly test schema rather than through handle."""

    @pytest.mark.parametrize(
        "config, error_msg",
        (
            # Valid, yet deprecated schemas
            (
                {"ca-certs": {"remove-defaults": True}},
                re.escape(
                    "Cloud config schema deprecations: ca-certs:  "
                    "Deprecated in version 22.3. Use **ca_certs** instead.,"
                    " ca-certs.remove-defaults:  Deprecated in version 22.3"
                    ". Use **remove_defaults** instead."
                ),
            ),
            # Invalid schemas
            (
                {"ca_certs": 1},
                "ca_certs: 1 is not of type 'object'",
            ),
            (
                {"ca_certs": {}},
                re.escape("ca_certs: {} ") + SCHEMA_EMPTY_ERROR,
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
                re.escape("ca_certs.trusted: [] ") + SCHEMA_EMPTY_ERROR,
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
