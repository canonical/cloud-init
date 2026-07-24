# This file is part of cloud-init. See LICENSE file for license information.

"""test_apk_configure
Test creation of repositories file
"""

import re
import textwrap

import pytest

from cloudinit import util
from cloudinit.config import cc_apk_configure
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import SCHEMA_EMPTY_ERROR, skipUnlessJsonSchema
from tests.unittests.util import get_cloud

REPO_FILE = "/etc/apk/repositories"
DEFAULT_MIRROR_URL = "https://dl-cdn.alpinelinux.org/alpine"
CC_APK = "cloudinit.config.cc_apk_configure"


class TestApkConfigure:
    @pytest.fixture(autouse=True)
    def setup(self, mocker, tmpdir):
        mocker.patch("cloudinit.temp_utils._ROOT_TMPDIR", str(tmpdir))
        yield

    @pytest.mark.parametrize(
        "config",
        (
            ({}),
            ({"apk_repos": {}}),
            ({"apk_repos": {"alpine_repo": []}}),
        ),
    )
    def test_no_config(self, config, mocker):
        """
        Test that nothing is done if no apk_configure
        configuration is provided.
        """
        m_write_repos = mocker.patch(CC_APK + "._write_repositories_file")

        cc_apk_configure.handle("", config, get_cloud(), [])
        assert m_write_repos.call_count == 0

    def test_only_main_repo(self, fake_filesystem):
        """
        Test when only details of main repo is written to file.
        """
        alpine_version = "v3.12"
        config = {"apk_repos": {"alpine_repo": {"version": alpine_version}}}

        cc_apk_configure.handle("", config, get_cloud(), [])

        expected_content = textwrap.dedent(
            """\
            #
            # Created by cloud-init
            #
            # This file is written on first boot of an instance
            #

            {0}/{1}/main

            """.format(
                DEFAULT_MIRROR_URL, alpine_version
            )
        )

        assert util.load_text_file(REPO_FILE) == expected_content

    def test_main_and_community_repos(self, fake_filesystem):
        """
        Test when only details of main and community repos are
        written to file.
        """
        alpine_version = "edge"
        config = {
            "apk_repos": {
                "alpine_repo": {
                    "version": alpine_version,
                    "community_enabled": True,
                }
            }
        }

        cc_apk_configure.handle("", config, get_cloud(), [])

        expected_content = textwrap.dedent(
            """\
            #
            # Created by cloud-init
            #
            # This file is written on first boot of an instance
            #

            {0}/{1}/main
            {0}/{1}/community

            """.format(
                DEFAULT_MIRROR_URL, alpine_version
            )
        )

        assert util.load_text_file(REPO_FILE) == expected_content

    def test_main_community_testing_repos(self, fake_filesystem):
        """
        Test when details of main, community and testing repos
        are written to file.
        """
        alpine_version = "v3.12"
        config = {
            "apk_repos": {
                "alpine_repo": {
                    "version": alpine_version,
                    "community_enabled": True,
                    "testing_enabled": True,
                }
            }
        }

        cc_apk_configure.handle("", config, get_cloud(), [])

        expected_content = textwrap.dedent(
            """\
            #
            # Created by cloud-init
            #
            # This file is written on first boot of an instance
            #

            {0}/{1}/main
            {0}/{1}/community
            #
            # Testing - using with non-Edge installation may cause problems!
            #
            {0}/edge/testing

            """.format(
                DEFAULT_MIRROR_URL, alpine_version
            )
        )

        assert util.load_text_file(REPO_FILE) == expected_content

    def test_edge_main_community_testing_repos(self, fake_filesystem):
        """
        Test when details of main, community and testing repos
        for Edge version of Alpine are written to file.
        """
        alpine_version = "edge"
        config = {
            "apk_repos": {
                "alpine_repo": {
                    "version": alpine_version,
                    "community_enabled": True,
                    "testing_enabled": True,
                }
            }
        }

        cc_apk_configure.handle("", config, get_cloud(), [])

        expected_content = textwrap.dedent(
            """\
            #
            # Created by cloud-init
            #
            # This file is written on first boot of an instance
            #

            {0}/{1}/main
            {0}/{1}/community
            {0}/{1}/testing

            """.format(
                DEFAULT_MIRROR_URL, alpine_version
            )
        )

        assert util.load_text_file(REPO_FILE) == expected_content

    def test_main_community_testing_local_repos(self, fake_filesystem):
        """
        Test when details of main, community, testing and
        local repos are written to file.
        """
        alpine_version = "v3.12"
        local_repo_url = "http://some.mirror/whereever"
        config = {
            "apk_repos": {
                "alpine_repo": {
                    "version": alpine_version,
                    "community_enabled": True,
                    "testing_enabled": True,
                },
                "local_repo_base_url": local_repo_url,
            }
        }

        cc_apk_configure.handle("", config, get_cloud(), [])

        expected_content = textwrap.dedent(
            """\
            #
            # Created by cloud-init
            #
            # This file is written on first boot of an instance
            #

            {0}/{1}/main
            {0}/{1}/community
            #
            # Testing - using with non-Edge installation may cause problems!
            #
            {0}/edge/testing

            #
            # Local repo
            #
            {2}/{1}

            """.format(
                DEFAULT_MIRROR_URL, alpine_version, local_repo_url
            )
        )

        assert util.load_text_file(REPO_FILE) == expected_content

    def test_edge_main_community_testing_local_repos(self, fake_filesystem):
        """
        Test when details of main, community, testing and local repos
        for Edge version of Alpine are written to file.
        """
        alpine_version = "edge"
        local_repo_url = "http://some.mirror/whereever"
        config = {
            "apk_repos": {
                "alpine_repo": {
                    "version": alpine_version,
                    "community_enabled": True,
                    "testing_enabled": True,
                },
                "local_repo_base_url": local_repo_url,
            }
        }

        cc_apk_configure.handle("", config, get_cloud(), [])

        expected_content = textwrap.dedent(
            """\
            #
            # Created by cloud-init
            #
            # This file is written on first boot of an instance
            #

            {0}/{1}/main
            {0}/{1}/community
            {0}/edge/testing

            #
            # Local repo
            #
            {2}/{1}

            """.format(
                DEFAULT_MIRROR_URL, alpine_version, local_repo_url
            )
        )

        assert util.load_text_file(REPO_FILE) == expected_content


class TestApkConfigureTinyCloudStyle:
    def test_structured_and_raw_repositories(self, fake_filesystem):
        config = {
            "apk": {
                "repositories": [
                    {
                        "base_url": "https://dl-cdn.alpinelinux.org/alpine",
                        "version": "v3.24",
                        "repos": ["main", "community"],
                    },
                    "https://packages.example.net/alpine/custom",
                ]
            }
        }

        cc_apk_configure.handle("", config, get_cloud(), [])

        expected_content = textwrap.dedent(
            """\
            #
            # Created by cloud-init
            #
            # This file is written on first boot of an instance
            #

            https://dl-cdn.alpinelinux.org/alpine/v3.24/main
            https://dl-cdn.alpinelinux.org/alpine/v3.24/community
            https://packages.example.net/alpine/custom

            """
        )

        assert util.load_text_file(REPO_FILE) == expected_content

    def test_duplicate_repositories_are_written_once(self, fake_filesystem):
        repository_url = "https://packages.example.net/custom"
        config = {"apk": {"repositories": [repository_url, repository_url]}}

        cc_apk_configure.handle("", config, get_cloud(), [])

        assert util.load_text_file(REPO_FILE).count(repository_url) == 1

    def test_apk_without_repositories_falls_back_to_apk_repos(
        self, fake_filesystem
    ):
        config = {
            "apk": {"preserve_repositories": False},
            "apk_repos": {"alpine_repo": {"version": "v3.24"}},
        }

        cc_apk_configure.handle("", config, get_cloud(), [])

        assert (
            f"{DEFAULT_MIRROR_URL}/v3.24/main"
            in util.load_text_file(REPO_FILE)
        )

    def test_apk_repositories_take_precedence_over_apk_repos(
        self, fake_filesystem, caplog
    ):
        config = {
            "apk": {"repositories": ["https://packages.example.net/custom"]},
            "apk_repos": {"alpine_repo": {"version": "v3.24"}},
        }

        cc_apk_configure.handle("", config, get_cloud(), [])

        repository_file = util.load_text_file(REPO_FILE)
        assert "https://packages.example.net/custom" in repository_file
        assert f"{DEFAULT_MIRROR_URL}/v3.24/main" not in repository_file
        assert "Both 'apk.repositories' and 'apk_repos'" in caplog.text

    def test_apk_preserve_repositories_overrides_apk_repos(self, mocker):
        config = {
            "apk": {
                "preserve_repositories": True,
                "repositories": ["https://packages.example.net/custom"],
            },
            "apk_repos": {"alpine_repo": {"version": "v3.24"}},
        }
        m_write_legacy = mocker.patch(CC_APK + "._write_repositories_file")
        m_write_repositories = mocker.patch(
            CC_APK + "._write_repository_entries"
        )

        cc_apk_configure.handle("", config, get_cloud(), [])

        m_write_legacy.assert_not_called()
        m_write_repositories.assert_not_called()


    @pytest.mark.parametrize(
        "release, repository_version",
        (
            ("3.24.0", "v3.24"),
            ("edge", "edge"),
            ("3.25.0_alpha20260724", "edge"),
            ("3.25.0_beta20260724", "edge"),
            ("3.25.0_pre20260724", "edge"),
        ),
    )
    def test_infers_repository_version_from_alpine_release(
        self, fake_filesystem, release, repository_version
    ):
        util.write_file("/etc/alpine-release", f"{release}\n")
        config = {
            "apk": {
                "repositories": [
                    {
                        "base_url": "https://dl-cdn.alpinelinux.org/alpine",
                        "repos": ["main"],
                    }
                ]
            }
        }

        cc_apk_configure.handle("", config, get_cloud(), [])

        expected_url = (
            "https://dl-cdn.alpinelinux.org/alpine/"
            f"{repository_version}/main"
        )
        assert expected_url in util.load_text_file(REPO_FILE)

    def test_requires_version_when_alpine_release_is_unrecognized(
        self, fake_filesystem
    ):
        util.write_file("/etc/alpine-release", "unknown\n")
        config = {"apk": {"repositories": [{"repos": ["main"]}]}}

        with pytest.raises(
            ValueError,
            match=r"set apk.repositories\[\].version explicitly",
        ):
            cc_apk_configure.handle("", config, get_cloud(), [])


class TestApkConfigureSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        (
            # Valid schemas
            ({"apk_repos": {"preserve_repositories": True}}, None),
            ({"apk_repos": {"alpine_repo": None}}, None),
            ({"apk_repos": {"alpine_repo": {"version": "v3.24"}}}, None),
            (
                {
                    "apk_repos": {
                        "alpine_repo": {
                            "base_url": "http://yep",
                            "community_enabled": True,
                            "testing_enabled": True,
                            "version": "v3.24",
                        }
                    }
                },
                None,
            ),
            ({"apk_repos": {"local_repo_base_url": "http://some"}}, None),
            # Invalid schemas
            (
                {"apk_repos": {"alpine_repo": {"version": False}}},
                "apk_repos.alpine_repo.version: False is not of type 'string'",
            ),
            (
                {
                    "apk_repos": {
                        "alpine_repo": {"version": "v3.12", "bogus": 1}
                    }
                },
                re.escape(
                    "apk_repos.alpine_repo: Additional properties are not"
                    " allowed ('bogus' was unexpected)"
                ),
            ),
            (
                {"apk_repos": {"alpine_repo": {}}},
                "apk_repos.alpine_repo: 'version' is a required property,"
                f" apk_repos.alpine_repo: {{}} {SCHEMA_EMPTY_ERROR}",
            ),
            (
                {"apk_repos": {"alpine_repo": True}},
                "apk_repos.alpine_repo: True is not of type 'object', 'null'",
            ),
            (
                {"apk_repos": {"preserve_repositories": "wrongtype"}},
                "apk_repos.preserve_repositories: 'wrongtype' is not of type"
                " 'boolean'",
            ),
            (
                {"apk_repos": {}},
                f"apk_repos: {{}} {SCHEMA_EMPTY_ERROR}",
            ),
            (
                {"apk_repos": {"local_repo_base_url": None}},
                "apk_repos.local_repo_base_url: None is not of type 'string'",
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


class TestApkConfigureTinyCloudStyleSchema:
    @skipUnlessJsonSchema()
    def test_schema_validation(self):
        schema = get_schema()
        validate_cloudconfig_schema(
            {
                "apk": {
                    "repositories": [
                        {
                            "base_url": "https://dl-cdn.alpinelinux.org/alpine",
                            "version": "v3.24",
                            "repos": ["main", "community"],
                        },
                        "https://packages.example.net/alpine/custom",
                    ]
                }
            },
            schema,
            strict=True,
        )
        with pytest.raises(SchemaValidationError):
            validate_cloudconfig_schema(
                {
                    "apk": {
                        "repositories": [
                            {
                                "base_url": "https://dl-cdn.alpinelinux.org/alpine",
                                "repos": "main",
                            }
                        ]
                    }
                },
                schema,
                strict=True,
            )
