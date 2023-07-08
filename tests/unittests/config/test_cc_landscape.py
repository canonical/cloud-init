# This file is part of cloud-init. See LICENSE file for license information.
import logging
import re

import pytest

from cloudinit.config import cc_landscape
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import mock, skipUnlessJsonSchema, wrap_and_call
from tests.unittests.util import get_cloud

LOG = logging.getLogger(__name__)


@mock.patch("cloudinit.config.cc_landscape.subp.subp")
class TestLandscape:
    def test_skip_empty_landscape_cloudconfig(self, m_subp):
        """Empty landscape cloud-config section does no work."""
        mycloud = get_cloud()
        mycloud.distro = mock.MagicMock()
        cfg = {"landscape": {}}
        cc_landscape.handle("notimportant", cfg, mycloud, None)
        assert mycloud.distro.install_packages.called is False

    def test_handler_error_on_invalid_landscape_type(self, m_subp):
        """Raise an error when landscape configuraiton option is invalid."""
        mycloud = get_cloud("ubuntu")
        cfg = {"landscape": "wrongtype"}
        with pytest.raises(RuntimeError) as exc:
            cc_landscape.handle("notimportant", cfg, mycloud, None)
        assert "'landscape' key existed in config, but not a dict" in str(
            exc.value
        )

    def test_handler_restarts_landscape_client(self, m_subp, tmpdir):
        """handler restarts landscape-client after install."""
        mycloud = get_cloud("ubuntu")
        mycloud.distro = mock.MagicMock()
        cfg = {"landscape": {"client": {}}}
        default_fn = tmpdir.join("default")
        wrap_and_call(
            "cloudinit.config.cc_landscape",
            {
                "LSC_CLIENT_CFG_FILE": {
                    "new": tmpdir.join("client.conf").strpath
                },
                "LS_DEFAULT_FILE": {"new": default_fn.strpath},
            },
            cc_landscape.handle,
            "notimportant",
            cfg,
            mycloud,
            None,
        )
        mycloud.distro.install_packages.assert_called_once_with(
            ("landscape-client",)
        )
        assert [
            mock.call(
                [
                    "landscape-config",
                    "--silent",
                    '--data-path="/var/lib/landscape/client"',
                    '--log-level="info"',
                    '--ping-url="http://landscape.canonical.com/ping"',
                    '--url="https://landscape.canonical.com/message-system"',
                ]
            ),
            mock.call(["service", "landscape-client", "restart"]),
        ] == m_subp.call_args_list

    def test_handler_installs_client_from_ppa_and_supports_overrides(
        self, m_subp, tmpdir
    ):
        """Call landscape-config with any filesystem overrides."""
        mycloud = get_cloud("ubuntu")
        mycloud.distro = mock.MagicMock()
        default_fn = tmpdir.join("default")
        client_fn = tmpdir.join("client.conf")
        client_fn.write("[client]\ndata_path = /var/lib/data\n")
        cfg = {
            "landscape": {
                "install_source": "ppa:landscape/self-hosted-beta",
                "client": {},
            }
        }
        expected_calls = [
            mock.call(
                ["add-apt-repository", "ppa:landscape/self-hosted-beta"]
            ),
            mock.call(
                [
                    "landscape-config",
                    "--silent",
                    '--data-path="/var/lib/data"',
                    '--log-level="info"',
                    '--ping-url="http://landscape.canonical.com/ping"',
                    '--url="https://landscape.canonical.com/message-system"',
                ]
            ),
            mock.call(["service", "landscape-client", "restart"]),
        ]
        wrap_and_call(
            "cloudinit.config.cc_landscape",
            {
                "LSC_CLIENT_CFG_FILE": {"new": client_fn.strpath},
                "LS_DEFAULT_FILE": {"new": default_fn.strpath},
            },
            cc_landscape.handle,
            "notimportant",
            cfg,
            mycloud,
            None,
        )
        mycloud.distro.install_packages.assert_called_once_with(
            ("landscape-client",)
        )
        assert expected_calls == m_subp.call_args_list
        assert "RUN=1\n" == default_fn.read()

    def test_handler_writes_merged_client_config_file_with_defaults(
        self, m_subp, tmpdir
    ):
        """Merge and write options from LSC_CLIENT_CFG_FILE with defaults."""
        # Write existing sparse client.conf file
        client_fn = tmpdir.join("client.conf")
        client_fn.write("[client]\ncomputer_title = My PC\n")
        default_fn = tmpdir.join("default")
        mycloud = get_cloud("ubuntu")
        mycloud.distro = mock.MagicMock()
        cfg = {"landscape": {"client": {}}}
        expected_calls = [
            mock.call(
                [
                    "landscape-config",
                    "--silent",
                    '--computer-title="My PC"',
                    '--data-path="/var/lib/landscape/client"',
                    '--log-level="info"',
                    '--ping-url="http://landscape.canonical.com/ping"',
                    '--url="https://landscape.canonical.com/message-system"',
                ]
            ),
            mock.call(["service", "landscape-client", "restart"]),
        ]
        wrap_and_call(
            "cloudinit.config.cc_landscape",
            {
                "LSC_CLIENT_CFG_FILE": {"new": client_fn.strpath},
                "LS_DEFAULT_FILE": {"new": default_fn.strpath},
            },
            cc_landscape.handle,
            "notimportant",
            cfg,
            mycloud,
            None,
        )
        assert expected_calls == m_subp.call_args_list

    def test_handler_writes_merged_provided_cloudconfig_with_defaults(
        self, m_subp, tmpdir
    ):
        """Merge and write options from cloud-config options with defaults."""
        # Write empty sparse client.conf file
        client_fn = tmpdir.join("client.conf")
        client_fn.write("")
        default_fn = tmpdir.join("default")
        mycloud = get_cloud("ubuntu")
        mycloud.distro = mock.MagicMock()
        cfg = {"landscape": {"client": {"computer_title": "My PC"}}}
        expected_calls = [
            mock.call(
                [
                    "landscape-config",
                    "--silent",
                    '--computer-title="My PC"',
                    '--data-path="/var/lib/landscape/client"',
                    '--log-level="info"',
                    '--ping-url="http://landscape.canonical.com/ping"',
                    '--url="https://landscape.canonical.com/message-system"',
                ]
            ),
            mock.call(["service", "landscape-client", "restart"]),
        ]
        wrap_and_call(
            "cloudinit.config.cc_landscape",
            {
                "LSC_CLIENT_CFG_FILE": {"new": client_fn.strpath},
                "LS_DEFAULT_FILE": {"new": default_fn.strpath},
            },
            cc_landscape.handle,
            "notimportant",
            cfg,
            mycloud,
            None,
        )
        assert expected_calls == m_subp.call_args_list


class TestLandscapeSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        [
            # Allow undocumented keys client keys without error
            ({"landscape": {"client": {"allow_additional_keys": 1}}}, None),
            ({"landscape": {"install_source": "distro", "client": {}}}, None),
            (
                {
                    "landscape": {
                        "install_source": "ppa:something",
                        "client": {},
                    }
                },
                None,
            ),
            (
                {"landscape": {"install_source": "ppu:", "client": {}}},
                re.escape(
                    "schema errors: landscape.install_source: 'ppu:'"
                    " does not match '^(distro|ppa:.+)$'"
                ),
            ),
            # tags are comma-delimited
            ({"landscape": {"client": {"tags": "1,2,3"}}}, None),
            ({"landscape": {"client": {"tags": "1"}}}, None),
            (
                {
                    "landscape": {
                        "client": {},
                        "random-config-value": {"tags": "1"},
                    }
                },
                "Additional properties are not allowed",
            ),
            # Require client key
            ({"landscape": {}}, "'client' is a required property"),
            # tags are not whitespace-delimited
            (
                {"landscape": {"client": {"tags": "1, 2,3"}}},
                "'1, 2,3' does not match",
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
