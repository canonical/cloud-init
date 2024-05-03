# This file is part of cloud-init. See LICENSE file for license information.
import logging

import pytest

from cloudinit import subp
from cloudinit.config import cc_landscape
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import mock, skipUnlessJsonSchema, wrap_and_call
from tests.unittests.util import get_cloud

LOG = logging.getLogger(__name__)

MPATH = "cloudinit.config.cc_landscape"


@mock.patch(f"{MPATH}.subp.subp")
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
            ["landscape-client"]
        )
        assert [
            mock.call(
                ["landscape-config", "--silent", "--is-registered"], rcs=[5]
            ),
            mock.call(
                [
                    "landscape-config",
                    "--silent",
                    "--data-path",
                    "/var/lib/landscape/client",
                    "--log-level",
                    "info",
                    "--ping-url",
                    "http://landscape.canonical.com/ping",
                    "--url",
                    "https://landscape.canonical.com/message-system",
                ]
            ),
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
                ["landscape-config", "--silent", "--is-registered"], rcs=[5]
            ),
            mock.call(
                [
                    "landscape-config",
                    "--silent",
                    "--data-path",
                    "/var/lib/data",
                    "--log-level",
                    "info",
                    "--ping-url",
                    "http://landscape.canonical.com/ping",
                    "--url",
                    "https://landscape.canonical.com/message-system",
                ]
            ),
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
            ["landscape-client"]
        )
        assert expected_calls == m_subp.call_args_list

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
                ["landscape-config", "--silent", "--is-registered"], rcs=[5]
            ),
            mock.call(
                [
                    "landscape-config",
                    "--silent",
                    "--computer-title",
                    "My PC",
                    "--data-path",
                    "/var/lib/landscape/client",
                    "--log-level",
                    "info",
                    "--ping-url",
                    "http://landscape.canonical.com/ping",
                    "--url",
                    "https://landscape.canonical.com/message-system",
                ]
            ),
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
        cfg = {"landscape": {"client": {"computer_title": 'My" PC'}}}
        expected_calls = [
            mock.call(
                ["landscape-config", "--silent", "--is-registered"], rcs=[5]
            ),
            mock.call(
                [
                    "landscape-config",
                    "--silent",
                    "--computer-title",
                    'My" PC',
                    "--data-path",
                    "/var/lib/landscape/client",
                    "--log-level",
                    "info",
                    "--ping-url",
                    "http://landscape.canonical.com/ping",
                    "--url",
                    "https://landscape.canonical.com/message-system",
                ]
            ),
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

    @mock.patch(f"{MPATH}.merge_together")
    def test_handler_client_failed_registering(self, m_merge_together, m_subp):
        """landscape-client could not be registered"""
        mycloud = get_cloud("ubuntu")
        mycloud.distro = mock.MagicMock()
        cfg = {"landscape": {"client": {"computer_title": 'My" PC'}}}
        m_subp.side_effect = subp.ProcessExecutionError(
            "Could not register client"
        )
        match = (
            "Failure registering client:\nUnexpected error while"
            " running command.\nCommand: -\nExit code: -\nReason: -\n"
            "Stdout: Could not register client\nStderr: -"
        )
        with pytest.raises(RuntimeError, match=match):
            cc_landscape.handle("notimportant", cfg, mycloud, None)

    @mock.patch(f"{MPATH}.merge_together")
    def test_handler_client_is_already_registered(
        self, m_merge_together, m_subp, caplog
    ):
        """landscape-client is already registered"""
        mycloud = get_cloud("ubuntu")
        mycloud.distro = mock.MagicMock()
        cfg = {"landscape": {"client": {"computer_title": 'My" PC'}}}
        m_subp.side_effect = subp.ProcessExecutionError(
            "Client already registered to Landscape", exit_code=0
        )
        cc_landscape.handle("notimportant", cfg, mycloud, None)
        assert "Client already registered to Landscape" in caplog.text


class TestLandscapeSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        [
            # Allow undocumented keys client keys without error
            (
                {
                    "landscape": {
                        "client": {
                            "computer_title": "joe",
                            "account_name": "joe's acct",
                            "allow_additional_keys": 1,
                        }
                    }
                },
                None,
            ),
            (
                {
                    "landscape": {
                        "client": {
                            "computer_title": "joe",
                            "account_name": "joe's acct",
                        }
                    }
                },
                None,
            ),
            # tags are comma-delimited
            (
                {
                    "landscape": {
                        "client": {
                            "computer_title": "joe",
                            "account_name": "joe's acct",
                            "tags": "1,2,3",
                        }
                    }
                },
                None,
            ),
            (
                {
                    "landscape": {
                        "client": {
                            "computer_title": "joe",
                            "account_name": "joe's acct",
                            "client": {"tags": "1"},
                        }
                    }
                },
                None,
            ),
            (
                {
                    "landscape": {
                        "client": {
                            "computer_title": "joe",
                            "account_name": "joe's acct",
                        },
                        "random-config-value": {"tags": "1"},
                    }
                },
                "Additional properties are not allowed",
            ),
            # Require client key
            ({"landscape": {}}, "'client' is a required property"),
            # Require client.account_name and client.computer_title
            (
                {"landscape": {"client": {"computer_title": "joe"}}},
                "'account_name' is a required property",
            ),
            (
                {"landscape": {"client": {"account_name": "joe's acct"}}},
                "'computer_title' is a required property",
            ),
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
