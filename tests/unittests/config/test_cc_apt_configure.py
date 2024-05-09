# This file is part of cloud-init. See LICENSE file for license information.

"""Tests for cc_apt_configure module"""

import re
from pathlib import Path
from unittest import mock

import pytest

from cloudinit import features
from cloudinit.config import cc_apt_configure as cc_apt
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import SCHEMA_EMPTY_ERROR, skipUnlessJsonSchema
from tests.unittests.util import get_cloud

M_PATH = "cloudinit.config.cc_apt_configure."


class TestAPTConfigureSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        (
            # Supplement valid schemas from examples tested in test_schema
            ({"apt": {"preserve_sources_list": True}}, None),
            # Invalid schemas
            (
                {"apt": "nonobject"},
                "apt: 'nonobject' is not of type 'object",
            ),
            (
                {"apt": {"boguskey": True}},
                re.escape(
                    "apt: Additional properties are not allowed"
                    " ('boguskey' was unexpected)"
                ),
            ),
            ({"apt": {}}, f"apt: {{}} {SCHEMA_EMPTY_ERROR}"),
            (
                {"apt": {"preserve_sources_list": 1}},
                "apt.preserve_sources_list: 1 is not of type 'boolean'",
            ),
            (
                {"apt": {"disable_suites": 1}},
                "apt.disable_suites: 1 is not of type 'array'",
            ),
            (
                {"apt": {"disable_suites": []}},
                re.escape("apt.disable_suites: [] ") + SCHEMA_EMPTY_ERROR,
            ),
            (
                {"apt": {"disable_suites": [1]}},
                "apt.disable_suites.0: 1 is not of type 'string'",
            ),
            (
                {"apt": {"disable_suites": ["a", "a"]}},
                re.escape(
                    "apt.disable_suites: ['a', 'a'] has non-unique elements"
                ),
            ),
            # All apt: primary tests are applicable for "security" key too.
            # Those apt:security tests are exercised in the unittest below
            (
                {"apt": {"primary": "nonlist"}},
                "apt.primary: 'nonlist' is not of type 'array'",
            ),
            (
                {"apt": {"primary": []}},
                re.escape("apt.primary: [] ") + SCHEMA_EMPTY_ERROR,
            ),
            (
                {"apt": {"primary": ["nonobj"]}},
                "apt.primary.0: 'nonobj' is not of type 'object'",
            ),
            (
                {"apt": {"primary": [{}]}},
                "apt.primary.0: 'arches' is a required property",
            ),
            (
                {"apt": {"primary": [{"boguskey": True}]}},
                re.escape(
                    "apt.primary.0: Additional properties are not allowed"
                    " ('boguskey' was unexpected)"
                ),
            ),
            (
                {"apt": {"primary": [{"arches": True}]}},
                "apt.primary.0.arches: True is not of type 'array'",
            ),
            (
                {"apt": {"primary": [{"uri": True}]}},
                "apt.primary.0.uri: True is not of type 'string'",
            ),
            (
                {
                    "apt": {
                        "primary": [
                            {"arches": ["amd64"], "search": "non-array"}
                        ]
                    }
                },
                "apt.primary.0.search: 'non-array' is not of type 'array'",
            ),
            (
                {"apt": {"primary": [{"arches": ["amd64"], "search": []}]}},
                re.escape("apt.primary.0.search: [] ") + SCHEMA_EMPTY_ERROR,
            ),
            (
                {
                    "apt": {
                        "primary": [{"arches": ["amd64"], "search_dns": "a"}]
                    }
                },
                "apt.primary.0.search_dns: 'a' is not of type 'boolean'",
            ),
            (
                {"apt": {"primary": [{"arches": ["amd64"], "keyid": 1}]}},
                "apt.primary.0.keyid: 1 is not of type 'string'",
            ),
            (
                {"apt": {"primary": [{"arches": ["amd64"], "key": 1}]}},
                "apt.primary.0.key: 1 is not of type 'string'",
            ),
            (
                {"apt": {"primary": [{"arches": ["amd64"], "keyserver": 1}]}},
                "apt.primary.0.keyserver: 1 is not of type 'string'",
            ),
            (
                {"apt": {"add_apt_repo_match": True}},
                "apt.add_apt_repo_match: True is not of type 'string'",
            ),
            (
                {"apt": {"debconf_selections": True}},
                "apt.debconf_selections: True is not of type 'object'",
            ),
            (
                {"apt": {"debconf_selections": {}}},
                f"apt.debconf_selections: {{}} {SCHEMA_EMPTY_ERROR}",
            ),
            (
                {"apt": {"sources_list": True}},
                "apt.sources_list: True is not of type 'string'",
            ),
            (
                {"apt": {"conf": True}},
                "apt.conf: True is not of type 'string'",
            ),
            (
                {"apt": {"http_proxy": True}},
                "apt.http_proxy: True is not of type 'string'",
            ),
            (
                {"apt": {"https_proxy": True}},
                "apt.https_proxy: True is not of type 'string'",
            ),
            (
                {"apt": {"proxy": True}},
                "apt.proxy: True is not of type 'string'",
            ),
            (
                {"apt": {"ftp_proxy": True}},
                "apt.ftp_proxy: True is not of type 'string'",
            ),
            (
                {"apt": {"sources": True}},
                "apt.sources: True is not of type 'object'",
            ),
            (
                {"apt": {"sources": {"opaquekey": True}}},
                "apt.sources.opaquekey: True is not of type 'object'",
            ),
            (
                {"apt": {"sources": {"opaquekey": {}}}},
                f"apt.sources.opaquekey: {{}} {SCHEMA_EMPTY_ERROR}",
            ),
            (
                {"apt": {"sources": {"opaquekey": {"boguskey": True}}}},
                re.escape(
                    "apt.sources.opaquekey: Additional properties are not"
                    " allowed ('boguskey' was unexpected)"
                ),
            ),
        ),
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        schema = get_schema()
        if error_msg is None:
            validate_cloudconfig_schema(config, schema, strict=True)
        else:
            with pytest.raises(SchemaValidationError, match=error_msg):
                validate_cloudconfig_schema(config, schema, strict=True)
            # Note apt['primary'] and apt['security'] have same defition
            # Avoid test setup duplicates by running same test using 'security'
            if isinstance(config.get("apt"), dict) and config["apt"].get(
                "primary"
            ):
                # To exercise security schema, rename test key from primary
                config["apt"]["security"] = config["apt"].pop("primary")
                error_msg = error_msg.replace("primary", "security")
                with pytest.raises(SchemaValidationError, match=error_msg):
                    validate_cloudconfig_schema(config, schema, strict=True)


class TestEnsureDependencies:
    @pytest.mark.parametrize(
        "cfg, already_installed, expected_install",
        (
            pytest.param({}, [], [], id="empty_cfg_no_pkg_installs"),
            pytest.param(
                {"sources": {"s1": {"keyid": "haveit"}}},
                ["gpg"],
                [],
                id="cfg_needs_gpg_no_installs_when_gpg_present",
            ),
            pytest.param(
                {"sources": {"s1": {"keyid": "haveit"}}},
                [],
                ["gnupg"],
                id="cfg_needs_gpg_installs_gnupg_when_absent",
            ),
            pytest.param(
                {"primary": [{"keyid": "haveit"}]},
                [],
                ["gnupg"],
                id="cfg_primary_needs_gpg_installs_gnupg_when_absent",
            ),
            pytest.param(
                {"security": [{"keyid": "haveit"}]},
                [],
                ["gnupg"],
                id="cfg_security_needs_gpg_installs_gnupg_when_absent",
            ),
            pytest.param(
                {"sources": {"s1": {"source": "ppa:yep"}}},
                ["add-apt-repository"],
                [],
                id="cfg_needs_sw_prop_common_when_present",
            ),
            pytest.param(
                {"sources": {"s1": {"source": "ppa:yep"}}},
                [],
                ["software-properties-common"],
                id="cfg_needs_sw_prop_common_when_add_apt_repo_absent",
            ),
        ),
    )
    def test_only_install_needed_packages(
        self, cfg, already_installed, expected_install, mocker
    ):
        """Only invoke install_packages when package installs are necessary"""
        mycloud = get_cloud("debian")
        install_packages = mocker.patch.object(
            mycloud.distro, "install_packages"
        )
        matcher = re.compile(cc_apt.ADD_APT_REPO_MATCH).search

        def fake_which(cmd):
            if cmd in already_installed:
                return "foundit"
            return None

        which = mocker.patch.object(cc_apt.shutil, "which")
        which.side_effect = fake_which
        cc_apt._ensure_dependencies(cfg, matcher, mycloud)
        if expected_install:
            install_packages.assert_called_once_with(expected_install)
        else:
            install_packages.assert_not_called()


class TestAptConfigure:
    @pytest.mark.parametrize(
        "src_content,distro_name,expected_content",
        (
            pytest.param(
                "content",
                "ubuntu",
                cc_apt.UBUNTU_DEFAULT_APT_SOURCES_LIST,
                id="ubuntu_replace_invalid_apt_source_list_with_default",
            ),
            pytest.param(
                "content",
                "debian",
                None,
                id="debian_remove_invalid_apt_source_list",
            ),
            pytest.param(
                cc_apt.UBUNTU_DEFAULT_APT_SOURCES_LIST,
                "ubuntu",
                cc_apt.UBUNTU_DEFAULT_APT_SOURCES_LIST,
                id="ubuntu_no_warning_when_existig_sources_list_content_allowed",
            ),
        ),
    )
    @mock.patch(M_PATH + "get_apt_cfg")
    @mock.patch.object(features, "APT_DEB822_SOURCE_LIST_FILE", True)
    def test_remove_source(
        self,
        m_get_apt_cfg,
        src_content,
        distro_name,
        expected_content,
        caplog,
        tmpdir,
    ):
        m_get_apt_cfg.return_value = {
            "sourcelist": f"{tmpdir}/etc/apt/sources.list",
            "sourceparts": f"{tmpdir}/etc/apt/sources.list.d/",
        }
        cloud = get_cloud(distro_name)
        sources_file = tmpdir.join("/etc/apt/sources.list")
        deb822_sources_file = tmpdir.join(
            f"/etc/apt/sources.list.d/{distro_name}.sources"
        )
        Path(sources_file).parent.mkdir(parents=True, exist_ok=True)
        sources_file.write(src_content)

        cfg = {
            "sources_list": """\
Types: deb
URIs: {{mirror}}
Suites: {{codename}} {{codename}}-updates {{codename}}-backports
Components: main restricted universe multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg"""
        }
        cc_apt.generate_sources_list(cfg, "noble", {}, cloud)
        if expected_content is None:
            assert not sources_file.exists()
            assert f"Removing {sources_file} to favor deb822" in caplog.text
        else:
            if src_content != expected_content:
                assert (
                    f"Replacing {sources_file} to favor deb822" in caplog.text
                )

            assert (
                cc_apt.UBUNTU_DEFAULT_APT_SOURCES_LIST == sources_file.read()
            )
            assert (
                f"Removing {sources_file} to favor deb822" not in caplog.text
            )
        assert deb822_sources_file.exists()
