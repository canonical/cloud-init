# This file is part of cloud-init. See LICENSE file for license information.
import logging
import re

import pytest

from cloudinit import subp
from cloudinit.config.cc_ubuntu_advantage import (
    configure_ua,
    handle,
    maybe_install_ua_tools,
    supplemental_schema_validation,
)
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import does_not_raise, mock, skipUnlessJsonSchema
from tests.unittests.util import get_cloud

# Module path used in mocks
MPATH = "cloudinit.config.cc_ubuntu_advantage"


@mock.patch(f"{MPATH}.subp.subp")
class TestConfigureUA:
    def test_configure_ua_attach_error(self, m_subp):
        """Errors from ua attach command are raised."""
        m_subp.side_effect = subp.ProcessExecutionError(
            "Invalid token SomeToken"
        )
        match = (
            "Failure attaching Ubuntu Advantage:\nUnexpected error while"
            " running command.\nCommand: -\nExit code: -\nReason: -\n"
            "Stdout: Invalid token SomeToken\nStderr: -"
        )
        with pytest.raises(RuntimeError, match=match):
            configure_ua(token="SomeToken")

    @pytest.mark.parametrize(
        "kwargs, call_args_list, log_record_tuples",
        [
            # When token is provided, attach the machine to ua using the token.
            pytest.param(
                {"token": "SomeToken"},
                [mock.call(["ua", "attach", "SomeToken"])],
                [
                    (
                        MPATH,
                        logging.DEBUG,
                        "Attaching to Ubuntu Advantage. ua attach SomeToken",
                    )
                ],
                id="with_token",
            ),
            # When services is an empty list, do not auto-enable attach.
            pytest.param(
                {"token": "SomeToken", "enable": []},
                [mock.call(["ua", "attach", "SomeToken"])],
                [
                    (
                        MPATH,
                        logging.DEBUG,
                        "Attaching to Ubuntu Advantage. ua attach SomeToken",
                    )
                ],
                id="with_empty_services",
            ),
            # When services a list, only enable specific services.
            pytest.param(
                {"token": "SomeToken", "enable": ["fips"]},
                [
                    mock.call(["ua", "attach", "SomeToken"]),
                    mock.call(
                        ["ua", "enable", "--assume-yes", "fips"], capture=True
                    ),
                ],
                [
                    (
                        MPATH,
                        logging.DEBUG,
                        "Attaching to Ubuntu Advantage. ua attach SomeToken",
                    )
                ],
                id="with_specific_services",
            ),
            # When services a string, treat as singleton list and warn
            pytest.param(
                {"token": "SomeToken", "enable": "fips"},
                [
                    mock.call(["ua", "attach", "SomeToken"]),
                    mock.call(
                        ["ua", "enable", "--assume-yes", "fips"], capture=True
                    ),
                ],
                [
                    (
                        MPATH,
                        logging.DEBUG,
                        "Attaching to Ubuntu Advantage. ua attach SomeToken",
                    ),
                    (
                        MPATH,
                        logging.WARNING,
                        "ubuntu_advantage: enable should be a list, not a "
                        "string; treating as a single enable",
                    ),
                ],
                id="with_string_services",
            ),
            # When services not string or list, warn but still attach
            pytest.param(
                {"token": "SomeToken", "enable": {"deffo": "wont work"}},
                [mock.call(["ua", "attach", "SomeToken"])],
                [
                    (
                        MPATH,
                        logging.DEBUG,
                        "Attaching to Ubuntu Advantage. ua attach SomeToken",
                    ),
                    (
                        MPATH,
                        logging.WARNING,
                        "ubuntu_advantage: enable should be a list, not a"
                        " dict; skipping enabling services",
                    ),
                ],
                id="with_weird_services",
            ),
        ],
    )
    @mock.patch(f"{MPATH}.maybe_install_ua_tools", mock.MagicMock())
    def test_configure_ua_attach(
        self, m_subp, kwargs, call_args_list, log_record_tuples, caplog
    ):
        configure_ua(**kwargs)
        assert call_args_list == m_subp.call_args_list
        for record_tuple in log_record_tuples:
            assert record_tuple in caplog.record_tuples

    def test_configure_ua_attach_on_service_error(self, m_subp, caplog):
        """all services should be enabled and then any failures raised"""

        def fake_subp(cmd, capture=None):
            fail_cmds = [
                ["ua", "enable", "--assume-yes", svc] for svc in ["esm", "cc"]
            ]
            if cmd in fail_cmds and capture:
                svc = cmd[-1]
                raise subp.ProcessExecutionError(
                    "Invalid {} credentials".format(svc.upper())
                )

        m_subp.side_effect = fake_subp

        with pytest.raises(
            RuntimeError,
            match=re.escape(
                'Failure enabling Ubuntu Advantage service(s): "esm", "cc"'
            ),
        ):
            configure_ua(token="SomeToken", enable=["esm", "cc", "fips"])
        assert m_subp.call_args_list == [
            mock.call(["ua", "attach", "SomeToken"]),
            mock.call(["ua", "enable", "--assume-yes", "esm"], capture=True),
            mock.call(["ua", "enable", "--assume-yes", "cc"], capture=True),
            mock.call(["ua", "enable", "--assume-yes", "fips"], capture=True),
        ]
        assert (
            MPATH,
            logging.WARNING,
            'Failure enabling "esm":\nUnexpected error'
            " while running command.\nCommand: -\nExit code: -\nReason: -\n"
            "Stdout: Invalid ESM credentials\nStderr: -",
        ) in caplog.record_tuples
        assert (
            MPATH,
            logging.WARNING,
            'Failure enabling "cc":\nUnexpected error'
            " while running command.\nCommand: -\nExit code: -\nReason: -\n"
            "Stdout: Invalid CC credentials\nStderr: -",
        ) in caplog.record_tuples
        assert 'Failure enabling "fips"' not in caplog.text

    def test_configure_ua_config_with_weird_params(self, m_subp, caplog):
        """When configs not string or list, warn but still attach"""
        configure_ua(
            token="SomeToken", config=["http_proxy=http://some-proxy.net:3128"]
        )
        assert [
            mock.call(["ua", "attach", "SomeToken"])
        ] == m_subp.call_args_list
        assert (
            MPATH,
            logging.WARNING,
            "ubuntu_advantage: config should be a dict, not a"
            " list; skipping enabling config parameters",
        ) == caplog.record_tuples[-2]
        assert (
            MPATH,
            logging.DEBUG,
            "Attaching to Ubuntu Advantage. ua attach SomeToken",
        ) == caplog.record_tuples[-1]

    def test_configure_ua_config_error_invalid_url(self, m_subp, caplog):
        """Errors from ua config command are raised."""
        m_subp.side_effect = subp.ProcessExecutionError(
            'Failure enabling "http_proxy"'
        )
        with pytest.raises(
            RuntimeError,
            match=re.escape(
                'Failure enabling Ubuntu Advantage config(s): "http_proxy"'
            ),
        ):
            configure_ua(
                token="SomeToken", config={"http_proxy": "not-a-valid-url"}
            )

    def test_configure_ua_config_error_non_string_values(self, m_subp):
        """ValueError raised for any values expected as string type."""
        cfg = {
            "global_apt_http_proxy": "noscheme",
            "http_proxy": ["no-proxy"],
            "https_proxy": 1,
        }
        match = re.escape(
            "Expected URL scheme http/https for"
            " ua:config:global_apt_http_proxy. Found: noscheme\n"
            "Expected a URL for ua:config:http_proxy. Found: ['no-proxy']\n"
            "Expected a URL for ua:config:https_proxy. Found: 1"
        )
        with pytest.raises(ValueError, match=match):
            supplemental_schema_validation(cfg)
        assert 0 == m_subp.call_count


class TestUbuntuAdvantageSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        [
            ({"ubuntu_advantage": {}}, "'token' is a required property"),
            # Strict keys
            (
                {"ubuntu_advantage": {"token": "win", "invalidkey": ""}},
                re.escape(
                    "ubuntu_advantage: Additional properties are not allowed"
                    " ('invalidkey"
                ),
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


class TestHandle:

    cloud = get_cloud()

    @pytest.mark.parametrize(
        [
            "cfg",
            "cloud",
            "log_record_tuples",
            "maybe_install_call_args_list",
            "configure_ua_call_args_list",
        ],
        [
            # When no ua-related configuration is provided, nothing happens.
            pytest.param(
                {},
                None,
                [
                    (
                        MPATH,
                        logging.DEBUG,
                        "Skipping module named nomatter, no 'ubuntu_advantage'"
                        " configuration found",
                    )
                ],
                [],
                [],
                id="no_config",
            ),
            # If ubuntu_advantage is provided, try installing ua-tools package.
            pytest.param(
                {"ubuntu_advantage": {"token": "valid"}},
                cloud,
                [],
                [mock.call(cloud)],
                None,
                id="tries_to_install_ubuntu_advantage_tools",
            ),
            # All ubuntu_advantage config keys are passed to configure_ua.
            pytest.param(
                {"ubuntu_advantage": {"token": "token", "enable": ["esm"]}},
                cloud,
                [],
                [mock.call(cloud)],
                [mock.call(token="token", enable=["esm"], config=None)],
                id="passes_credentials_and_services_to_configure_ua",
            ),
            # Warning when ubuntu-advantage key is present with new config
            pytest.param(
                {"ubuntu-advantage": {"token": "token", "enable": ["esm"]}},
                None,
                [
                    (
                        MPATH,
                        logging.WARNING,
                        'Deprecated configuration key "ubuntu-advantage"'
                        " provided. Expected underscore delimited "
                        '"ubuntu_advantage"; will attempt to continue.',
                    )
                ],
                None,
                [mock.call(token="token", enable=["esm"], config=None)],
                id="warns_on_deprecated_ubuntu_advantage_key_w_config",
            ),
            # ubuntu_advantage should be preferred over ubuntu-advantage
            pytest.param(
                {
                    "ubuntu-advantage": {"token": "nope", "enable": ["wrong"]},
                    "ubuntu_advantage": {"token": "token", "enable": ["esm"]},
                },
                None,
                [
                    (
                        MPATH,
                        logging.WARNING,
                        'Deprecated configuration key "ubuntu-advantage"'
                        " provided. Expected underscore delimited "
                        '"ubuntu_advantage"; will attempt to continue.',
                    )
                ],
                None,
                [mock.call(token="token", enable=["esm"], config=None)],
                id="prefers_new_style_config",
            ),
        ],
    )
    @mock.patch(f"{MPATH}.configure_ua")
    @mock.patch(f"{MPATH}.maybe_install_ua_tools")
    def test_handle(
        self,
        m_maybe_install_ua_tools,
        m_configure_ua,
        cfg,
        cloud,
        log_record_tuples,
        maybe_install_call_args_list,
        configure_ua_call_args_list,
        caplog,
    ):
        handle("nomatter", cfg=cfg, cloud=cloud, log=None, args=None)
        for record_tuple in log_record_tuples:
            assert record_tuple in caplog.record_tuples
        if maybe_install_call_args_list is not None:
            assert (
                maybe_install_call_args_list
                == m_maybe_install_ua_tools.call_args_list
            )
        if configure_ua_call_args_list is not None:
            assert configure_ua_call_args_list == m_configure_ua.call_args_list

    @pytest.mark.parametrize(
        "cfg, handle_kwargs, match",
        [
            pytest.param(
                {"ubuntu-advantage": {"commands": "nogo"}},
                dict(cloud=None, args=None),
                (
                    'Deprecated configuration "ubuntu-advantage: commands" '
                    'provided. Expected "token"'
                ),
                id="key_dashed",
            ),
            pytest.param(
                {"ubuntu_advantage": {"commands": "nogo"}},
                dict(cloud=None, args=None),
                (
                    'Deprecated configuration "ubuntu-advantage: commands" '
                    'provided. Expected "token"'
                ),
                id="key_underscore",
            ),
        ],
    )
    @mock.patch("%s.configure_ua" % MPATH)
    def test_handle_error_on_deprecated_commands_key_dashed(
        self, m_configure_ua, cfg, handle_kwargs, match
    ):
        with pytest.raises(RuntimeError, match=match):
            handle("nomatter", cfg=cfg, log=mock.Mock(), **handle_kwargs)
        assert 0 == m_configure_ua.call_count


@mock.patch(f"{MPATH}.subp.which")
class TestMaybeInstallUATools:
    @pytest.mark.parametrize(
        [
            "which_return",
            "update_side_effect",
            "install_side_effect",
            "expectation",
            "log_msg",
        ],
        [
            # Do nothing if ubuntu-advantage-tools already exists.
            pytest.param(
                "/usr/bin/ua",  # already installed
                RuntimeError("Some apt error"),
                None,
                does_not_raise(),  # No RuntimeError
                None,
                id="noop_when_ua_tools_present",
            ),
            # logs and raises apt update errors
            pytest.param(
                None,
                RuntimeError("Some apt error"),
                None,
                pytest.raises(RuntimeError, match="Some apt error"),
                "Package update failed\nTraceback",
                id="raises_update_errors",
            ),
            # logs and raises package install errors
            pytest.param(
                None,
                None,
                RuntimeError("Some install error"),
                pytest.raises(RuntimeError, match="Some install error"),
                "Failed to install ubuntu-advantage-tools\n",
                id="raises_install_errors",
            ),
        ],
    )
    def test_maybe_install_ua_tools(
        self,
        m_which,
        which_return,
        update_side_effect,
        install_side_effect,
        expectation,
        log_msg,
        caplog,
    ):
        m_which.return_value = which_return
        cloud = mock.MagicMock()
        if install_side_effect is None:
            cloud.distro.update_package_sources.side_effect = (
                update_side_effect
            )
        else:
            cloud.distro.update_package_sources.return_value = None
            cloud.distro.install_packages.side_effect = install_side_effect
        with expectation:
            maybe_install_ua_tools(cloud=cloud)
        if log_msg is not None:
            assert log_msg in caplog.text

    def test_maybe_install_ua_tools_happy_path(self, m_which):
        """maybe_install_ua_tools installs ubuntu-advantage-tools."""
        m_which.return_value = None
        cloud = mock.MagicMock()  # No errors raised
        maybe_install_ua_tools(cloud=cloud)
        assert [
            mock.call()
        ] == cloud.distro.update_package_sources.call_args_list
        assert [
            mock.call(["ubuntu-advantage-tools"])
        ] == cloud.distro.install_packages.call_args_list


# vi: ts=4 expandtab
