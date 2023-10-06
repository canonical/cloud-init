# This file is part of cloud-init. See LICENSE file for license information.
import json
import logging
import re
import sys
from collections import namedtuple

import pytest

from cloudinit import subp
from cloudinit.config.cc_ubuntu_advantage import (
    _attach,
    _auto_attach,
    _should_auto_attach,
    configure_ua,
    handle,
    maybe_install_ua_tools,
    set_ua_config,
    validate_schema_features,
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


class FakeUserFacingError(Exception):
    def __init__(self, msg: str):
        self.msg = msg


class FakeAlreadyAttachedError(FakeUserFacingError):
    pass


class FakeAlreadyAttachedOnPROError(FakeUserFacingError):
    pass


@pytest.fixture
def fake_uaclient(mocker):
    """Mocks `uaclient` module"""

    mocker.patch.dict("sys.modules")
    m_uaclient = mock.Mock()

    sys.modules["uaclient"] = m_uaclient

    # Exceptions
    _exceptions = namedtuple(
        "exceptions",
        [
            "UserFacingError",
            "AlreadyAttachedError",
        ],
    )(
        FakeUserFacingError,
        FakeAlreadyAttachedError,
    )
    sys.modules["uaclient.api.exceptions"] = _exceptions


@pytest.mark.usefixtures("fake_uaclient")
@mock.patch(f"{MPATH}.subp.subp")
class TestConfigureUA:
    def test_configure_ua_attach_error(self, m_subp):
        """Errors from pro attach command are raised."""
        m_subp.side_effect = subp.ProcessExecutionError(
            "Invalid token SomeToken"
        )
        match = (
            "Failure attaching Ubuntu Advantage:\nUnexpected error while"
            " running command.\nCommand: -\nExit code: -\nReason: -\n"
            "Stdout: Invalid token REDACTED\nStderr: -"
        )
        with pytest.raises(RuntimeError, match=match):
            configure_ua(token="SomeToken")

    @pytest.mark.parametrize(
        "kwargs, call_args_list, log_record_tuples",
        [
            # When token is provided, attach to pro using the token.
            pytest.param(
                {"token": "SomeToken"},
                [
                    mock.call(
                        ["pro", "attach", "SomeToken"],
                        logstring=["pro", "attach", "REDACTED"],
                        rcs={0, 2},
                    )
                ],
                [
                    (
                        MPATH,
                        logging.DEBUG,
                        "Attaching to Ubuntu Advantage. pro attach REDACTED",
                    )
                ],
                id="with_token",
            ),
            # When services is an empty list, do not auto-enable attach.
            pytest.param(
                {"token": "SomeToken", "enable": []},
                [
                    mock.call(
                        ["pro", "attach", "SomeToken"],
                        logstring=["pro", "attach", "REDACTED"],
                        rcs={0, 2},
                    )
                ],
                [
                    (
                        MPATH,
                        logging.DEBUG,
                        "Attaching to Ubuntu Advantage. pro attach REDACTED",
                    )
                ],
                id="with_empty_services",
            ),
            # When services a list, only enable specific services.
            pytest.param(
                {"token": "SomeToken", "enable": ["fips"]},
                [
                    mock.call(
                        ["pro", "attach", "--no-auto-enable", "SomeToken"],
                        logstring=[
                            "pro",
                            "attach",
                            "--no-auto-enable",
                            "REDACTED",
                        ],
                        rcs={0, 2},
                    ),
                    mock.call(
                        [
                            "pro",
                            "enable",
                            "--assume-yes",
                            "--format",
                            "json",
                            "fips",
                        ],
                        capture=True,
                        rcs={0, 1},
                    ),
                ],
                [
                    (
                        MPATH,
                        logging.DEBUG,
                        "Attaching to Ubuntu Advantage. pro attach"
                        " --no-auto-enable REDACTED",
                    )
                ],
                id="with_specific_services",
            ),
            # When services a string, treat as singleton list and warn
            pytest.param(
                {"token": "SomeToken", "enable": "fips"},
                [
                    mock.call(
                        ["pro", "attach", "--no-auto-enable", "SomeToken"],
                        logstring=[
                            "pro",
                            "attach",
                            "--no-auto-enable",
                            "REDACTED",
                        ],
                        rcs={0, 2},
                    ),
                    mock.call(
                        [
                            "pro",
                            "enable",
                            "--assume-yes",
                            "--format",
                            "json",
                            "fips",
                        ],
                        capture=True,
                        rcs={0, 1},
                    ),
                ],
                [
                    (
                        MPATH,
                        logging.DEBUG,
                        "Attaching to Ubuntu Advantage. pro attach"
                        " --no-auto-enable REDACTED",
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
                [
                    mock.call(
                        ["pro", "attach", "SomeToken"],
                        logstring=["pro", "attach", "REDACTED"],
                        rcs={0, 2},
                    )
                ],
                [
                    (
                        MPATH,
                        logging.DEBUG,
                        "Attaching to Ubuntu Advantage. pro attach REDACTED",
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
        m_subp.return_value = subp.SubpResult(json.dumps({"errors": []}), "")
        configure_ua(**kwargs)
        assert call_args_list == m_subp.call_args_list
        for record_tuple in log_record_tuples:
            assert record_tuple in caplog.record_tuples

    def test_configure_ua_already_attached(self, m_subp, caplog):
        """pro is already attached to an subscription"""
        m_subp.rcs = 2
        configure_ua(token="SomeToken")
        assert m_subp.call_args_list == [
            mock.call(
                ["pro", "attach", "SomeToken"],
                logstring=["pro", "attach", "REDACTED"],
                rcs={0, 2},
            )
        ]
        assert (
            MPATH,
            logging.DEBUG,
            "Attaching to Ubuntu Advantage. pro attach REDACTED",
        ) in caplog.record_tuples

    def test_configure_ua_attach_on_service_enabled(
        self, m_subp, caplog, fake_uaclient
    ):
        """retry enabling an already enabled service"""

        def fake_subp(cmd, capture=None, rcs=None, logstring=None):
            fail_cmds = [
                "pro",
                "enable",
                "--assume-yes",
                "--format",
                "json",
                "livepatch",
            ]
            if cmd == fail_cmds and capture:
                response = {
                    "errors": [
                        {
                            "message": "Does not matter",
                            "message_code": "service-already-enabled",
                            "service": cmd[-1],
                            "type": "service",
                        }
                    ]
                }
                return subp.SubpResult(json.dumps(response), "")

        m_subp.side_effect = fake_subp

        configure_ua(token="SomeToken", enable=["livepatch"])
        assert m_subp.call_args_list == [
            mock.call(
                ["pro", "attach", "--no-auto-enable", "SomeToken"],
                logstring=["pro", "attach", "--no-auto-enable", "REDACTED"],
                rcs={0, 2},
            ),
            mock.call(
                [
                    "pro",
                    "enable",
                    "--assume-yes",
                    "--format",
                    "json",
                    "livepatch",
                ],
                capture=True,
                rcs={0, 1},
            ),
        ]
        assert (
            MPATH,
            logging.DEBUG,
            "Service `livepatch` already enabled.",
        ) in caplog.record_tuples

    def test_configure_ua_attach_on_service_error(self, m_subp, caplog):
        """all services should be enabled and then any failures raised"""

        def fake_subp(cmd, capture=None, rcs=None, logstring=None):
            fail_cmd = [
                "pro",
                "enable",
                "--assume-yes",
                "--format",
                "json",
            ]
            if cmd[: len(fail_cmd)] == fail_cmd and capture:
                response = {
                    "errors": [
                        {
                            "message": f"Invalid {svc} credentials",
                            "message_code": "some-code",
                            "service": svc,
                            "type": "service",
                        }
                        for svc in ["esm", "cc"]
                    ]
                    + [
                        {
                            "message": "Cannot enable unknown service 'asdf'",
                            "message_code": "invalid-service-or-failure",
                            "service": None,
                            "type": "system",
                        }
                    ]
                }
                return subp.SubpResult(json.dumps(response), "")
            return subp.SubpResult(json.dumps({"errors": []}), "")

        m_subp.side_effect = fake_subp

        with pytest.raises(
            RuntimeError,
            match=re.escape(
                "Failure enabling Ubuntu Advantage service(s): esm, cc"
            ),
        ):
            configure_ua(
                token="SomeToken", enable=["esm", "cc", "fips", "asdf"]
            )
        assert m_subp.call_args_list == [
            mock.call(
                ["pro", "attach", "--no-auto-enable", "SomeToken"],
                logstring=["pro", "attach", "--no-auto-enable", "REDACTED"],
                rcs={0, 2},
            ),
            mock.call(
                [
                    "pro",
                    "enable",
                    "--assume-yes",
                    "--format",
                    "json",
                    "esm",
                    "cc",
                    "fips",
                    "asdf",
                ],
                capture=True,
                rcs={0, 1},
            ),
        ]
        assert (
            MPATH,
            logging.WARNING,
            "Failure enabling `esm`: Invalid esm credentials",
        ) in caplog.record_tuples
        assert (
            MPATH,
            logging.WARNING,
            "Failure enabling `cc`: Invalid cc credentials",
        ) in caplog.record_tuples
        assert (
            MPATH,
            logging.WARNING,
            "Failure of type `system`: Cannot enable unknown service 'asdf'",
        ) in caplog.record_tuples
        assert 'Failure enabling "fips"' not in caplog.text

    def test_ua_enable_unexpected_error_codes(self, m_subp):
        def fake_subp(cmd, capture=None, **kwargs):
            if cmd[:2] == ["pro", "enable"] and capture:
                raise subp.ProcessExecutionError(exit_code=255)
            return subp.SubpResult(json.dumps({"errors": []}), "")

        m_subp.side_effect = fake_subp

        with pytest.raises(
            RuntimeError,
            match=re.escape("Error while enabling service(s): esm"),
        ):
            configure_ua(token="SomeToken", enable=["esm"])

    def test_ua_enable_non_json_response(self, m_subp):
        def fake_subp(cmd, capture=None, **kwargs):
            if cmd[:2] == ["pro", "enable"] and capture:
                return subp.SubpResult("I dream to be a Json", "")
            return subp.SubpResult(json.dumps({"errors": []}), "")

        m_subp.side_effect = fake_subp

        with pytest.raises(
            RuntimeError,
            match=re.escape("UA response was not json: I dream to be a Json"),
        ):
            configure_ua(token="SomeToken", enable=["esm"])


class TestUbuntuAdvantageSchema:
    @pytest.mark.parametrize(
        "config, expectation",
        [
            ({"ubuntu_advantage": {}}, does_not_raise()),
            # Strict keys
            pytest.param(
                {"ubuntu_advantage": {"token": "win", "invalidkey": ""}},
                pytest.raises(
                    SchemaValidationError,
                    match=re.escape(
                        "ubuntu_advantage: Additional properties are not"
                        " allowed ('invalidkey"
                    ),
                ),
                id="additional_properties",
            ),
            pytest.param(
                {
                    "ubuntu_advantage": {
                        "features": {"disable_auto_attach": True}
                    }
                },
                does_not_raise(),
                id="disable_auto_attach",
            ),
            pytest.param(
                {
                    "ubuntu_advantage": {
                        "features": {"disable_auto_attach": False},
                        "enable": ["fips"],
                        "enable_beta": ["realtime-kernel"],
                        "token": "<token>",
                    }
                },
                does_not_raise(),
                id="pro_custom_services",
            ),
            pytest.param(
                {
                    "ubuntu_advantage": {
                        "enable": ["fips"],
                        "enable_beta": ["realtime-kernel"],
                        "token": "<token>",
                    }
                },
                does_not_raise(),
                id="non_pro_beta_services",
            ),
            pytest.param(
                {
                    "ubuntu_advantage": {
                        "features": {"asdf": False},
                        "enable": ["fips"],
                        "enable_beta": ["realtime-kernel"],
                        "token": "<token>",
                    }
                },
                pytest.raises(
                    SchemaValidationError,
                    match=re.escape(
                        "ubuntu_advantage.features: Additional properties are"
                        " not allowed ('asdf'"
                    ),
                ),
                id="pro_additional_features",
            ),
            pytest.param(
                {
                    "ubuntu_advantage": {
                        "enable": ["fips"],
                        "token": "<token>",
                        "config": {
                            "http_proxy": "http://some-proxy:8088",
                            "https_proxy": "https://some-proxy:8088",
                            "global_apt_https_proxy": "https://some-global-apt-proxy:8088/",  # noqa: E501
                            "global_apt_http_proxy": "http://some-global-apt-proxy:8088/",  # noqa: E501
                            "ua_apt_http_proxy": "http://10.0.10.10:3128",
                            "ua_apt_https_proxy": "https://10.0.10.10:3128",
                        },
                    }
                },
                does_not_raise(),
                id="ua_config_valid_set",
            ),
            pytest.param(
                {
                    "ubuntu_advantage": {
                        "enable": ["fips"],
                        "token": "<token>",
                        "config": {
                            "http_proxy": None,
                            "https_proxy": None,
                            "global_apt_https_proxy": None,
                            "global_apt_http_proxy": None,
                            "ua_apt_http_proxy": None,
                            "ua_apt_https_proxy": None,
                        },
                    }
                },
                does_not_raise(),
                id="ua_config_valid_unset",
            ),
            pytest.param(
                {
                    "ubuntu_advantage": {
                        "enable": ["fips"],
                        "token": "<token>",
                        "config": ["http_proxy=http://some-proxy:8088"],
                    }
                },
                pytest.raises(
                    SchemaValidationError,
                    match=re.escape(
                        "errors: ubuntu_advantage.config:"
                        " ['http_proxy=http://some-proxy:8088']"
                    ),
                ),
                id="ua_config_invalid_type",
            ),
            pytest.param(
                {
                    "ubuntu_advantage": {
                        "enable": ["fips"],
                        "token": "<token>",
                        "config": {
                            "http_proxy": 8888,
                            "https_proxy": ["http://some-proxy:8088"],
                        },
                    }
                },
                pytest.raises(
                    SchemaValidationError,
                    match=re.escape(
                        "errors: ubuntu_advantage.config.http_proxy: 8888"
                        " is not of type 'string', 'null',"
                        " ubuntu_advantage.config.https_proxy:"
                        " ['http://some-proxy:8088']"
                    ),
                ),
                id="ua_config_invalid_type",
            ),
            pytest.param(
                {
                    "ubuntu_advantage": {
                        "enable": ["fips"],
                        "token": "<token>",
                        "config": {
                            "http_proxy": "http://some-proxy:8088",
                            "hola": "adios",
                        },
                    }
                },
                does_not_raise(),
                id="ua_config_unknown_props_allowed",
            ),
        ],
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, expectation, caplog):
        with expectation:
            validate_cloudconfig_schema(config, get_schema(), strict=True)

    @pytest.mark.parametrize(
        "ua_section, expectation, log_msgs",
        [
            ({}, does_not_raise(), None),
            ({"features": {}}, does_not_raise(), None),
            (
                {"features": {"disable_auto_attach": True}},
                does_not_raise(),
                None,
            ),
            (
                {"features": {"disable_auto_attach": False}},
                does_not_raise(),
                None,
            ),
            (
                {"features": [0, 1]},
                pytest.raises(
                    RuntimeError,
                    match=(
                        "'ubuntu_advantage.features' should be a dict,"
                        " not a list"
                    ),
                ),
                ["'ubuntu_advantage.features' should be a dict, not a list\n"],
            ),
            (
                {"features": {"disable_auto_attach": [0, 1]}},
                pytest.raises(
                    RuntimeError,
                    match=(
                        "'ubuntu_advantage.features.disable_auto_attach'"
                        " should be a bool, not a list"
                    ),
                ),
                [
                    "'ubuntu_advantage.features.disable_auto_attach' should be"
                    " a bool, not a list\n"
                ],
            ),
        ],
    )
    def test_validate_schema_features(
        self, ua_section, expectation, log_msgs, caplog
    ):
        with expectation:
            validate_schema_features(ua_section)
        if log_msgs is not None:
            for log_msg in log_msgs:
                assert log_msg in caplog.text
        else:
            assert not caplog.text


class TestHandle:

    cloud = get_cloud()

    @pytest.mark.parametrize(
        [
            "cfg",
            "cloud",
            "log_record_tuples",
            "maybe_install_call_args_list",
            "set_ua_config_call_args_list",
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
                [],
                id="no_config",
            ),
            # If ubuntu_advantage is provided, try installing ua-tools package.
            pytest.param(
                {"ubuntu_advantage": {"token": "valid"}},
                cloud,
                [],
                [mock.call(cloud)],
                [mock.call(None)],
                None,
                id="tries_to_install_ubuntu_advantage_tools",
            ),
            # If ubuntu_advantage config provided, configure it.
            pytest.param(
                {
                    "ubuntu_advantage": {
                        "token": "valid",
                        "config": {"http_proxy": "http://proxy.org"},
                    }
                },
                cloud,
                [],
                None,
                [mock.call({"http_proxy": "http://proxy.org"})],
                None,
                id="set_ua_config",
            ),
            # All ubuntu_advantage config keys are passed to configure_ua.
            pytest.param(
                {"ubuntu_advantage": {"token": "token", "enable": ["esm"]}},
                cloud,
                [],
                [mock.call(cloud)],
                [mock.call(None)],
                [mock.call(token="token", enable=["esm"])],
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
                [mock.call(None)],
                [mock.call(token="token", enable=["esm"])],
                id="warns_on_deprecated_ubuntu_advantage_key_w_config",
            ),
            # Warning with beta services during attach
            pytest.param(
                {
                    "ubuntu_advantage": {
                        "token": "token",
                        "enable": ["esm"],
                        "enable_beta": ["realtime-kernel"],
                    }
                },
                None,
                [
                    (
                        MPATH,
                        logging.DEBUG,
                        "Ignoring `ubuntu_advantage.enable_beta` services in"
                        " UA attach: realtime-kernel",
                    )
                ],
                None,
                [mock.call(None)],
                [mock.call(token="token", enable=["esm"])],
                id="warns_on_enable_beta_in_attach",
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
                [mock.call(None)],
                [mock.call(token="token", enable=["esm"])],
                id="prefers_new_style_config",
            ),
        ],
    )
    @mock.patch(f"{MPATH}._should_auto_attach", return_value=False)
    @mock.patch(f"{MPATH}._auto_attach")
    @mock.patch(f"{MPATH}.configure_ua")
    @mock.patch(f"{MPATH}.set_ua_config")
    @mock.patch(f"{MPATH}.maybe_install_ua_tools")
    def test_handle_attach(
        self,
        m_maybe_install_ua_tools,
        m_set_ua_config,
        m_configure_ua,
        m_auto_attach,
        m_should_auto_attach,
        cfg,
        cloud,
        log_record_tuples,
        maybe_install_call_args_list,
        set_ua_config_call_args_list,
        configure_ua_call_args_list,
        caplog,
    ):
        """Non-Pro schemas and instance."""
        handle("nomatter", cfg=cfg, cloud=cloud, args=None)
        for record_tuple in log_record_tuples:
            assert record_tuple in caplog.record_tuples
        if maybe_install_call_args_list is not None:
            assert (
                maybe_install_call_args_list
                == m_maybe_install_ua_tools.call_args_list
            )
        if set_ua_config_call_args_list is not None:
            assert (
                set_ua_config_call_args_list == m_set_ua_config.call_args_list
            )
        if configure_ua_call_args_list is not None:
            assert configure_ua_call_args_list == m_configure_ua.call_args_list
        assert [] == m_auto_attach.call_args_list

    @pytest.mark.parametrize(
        [
            "cfg",
            "cloud",
            "log_record_tuples",
            "auto_attach_side_effect",
            "should_auto_attach",
            "auto_attach_call_args_list",
            "attach_call_args_list",
            "expectation",
        ],
        [
            # When auto_attach successes, no call to configure_ua.
            pytest.param(
                {
                    "ubuntu_advantage": {
                        "features": {"disable_auto_attach": False}
                    }
                },
                cloud,
                [],
                None,  # auto_attach successes
                True,  # Pro instance
                [
                    mock.call({"features": {"disable_auto_attach": False}})
                ],  # auto_attach_call_args_list
                [],  # attach_call_args_list
                does_not_raise(),
                id="auto_attach_success",
            ),
            # When auto_attach fails in a Pro instance, no call to
            # configure_ua.
            pytest.param(
                {
                    "ubuntu_advantage": {
                        "features": {"disable_auto_attach": False}
                    }
                },
                cloud,
                [],
                RuntimeError("Auto attach error"),
                True,  # Pro instance
                [
                    mock.call({"features": {"disable_auto_attach": False}})
                ],  # auto_attach_call_args_list
                [],  # attach_call_args_list
                pytest.raises(RuntimeError, match="Auto attach error"),
                id="auto_attach_error",
            ),
            # In a non-Pro instance with token, fallback to normal attach.
            pytest.param(
                {
                    "ubuntu_advantage": {
                        "features": {"disable_auto_attach": False},
                        "token": "token",
                    }
                },
                cloud,
                [],
                None,
                False,  # non-Pro instance
                [],  # auto_attach_call_args_list
                [
                    mock.call(
                        {
                            "features": {"disable_auto_attach": False},
                            "token": "token",
                        },
                    )
                ],  # attach_call_args_list
                does_not_raise(),
                id="not_pro_with_token",
            ),
            # In a non-Pro instance with enable, fallback to normal attach.
            pytest.param(
                {"ubuntu_advantage": {"enable": ["esm"]}},
                cloud,
                [],
                None,
                False,  # non-Pro instance
                [],  # auto_attach_call_args_list
                [
                    mock.call(
                        {
                            "enable": ["esm"],
                        },
                    )
                ],  # attach_call_args_list
                does_not_raise(),
                id="not_pro_with_enable",
            ),
        ],
    )
    @mock.patch(f"{MPATH}._should_auto_attach")
    @mock.patch(f"{MPATH}._auto_attach")
    @mock.patch(f"{MPATH}._attach")
    def test_handle_auto_attach_vs_attach(
        self,
        m_attach,
        m_auto_attach,
        m_should_auto_attach,
        cfg,
        cloud,
        log_record_tuples,
        auto_attach_side_effect,
        should_auto_attach,
        auto_attach_call_args_list,
        attach_call_args_list,
        expectation,
        caplog,
    ):
        m_should_auto_attach.return_value = should_auto_attach
        if auto_attach_side_effect is not None:
            m_auto_attach.side_effect = auto_attach_side_effect

        with expectation:
            handle("nomatter", cfg=cfg, cloud=cloud, args=None)

        for record_tuple in log_record_tuples:
            assert record_tuple in caplog.record_tuples
        if attach_call_args_list is not None:
            assert attach_call_args_list == m_attach.call_args_list
        else:
            assert [] == m_attach.call_args_list
        assert auto_attach_call_args_list == m_auto_attach.call_args_list

    @pytest.mark.parametrize("is_pro", [False, True])
    @pytest.mark.parametrize(
        "cfg",
        [
            (
                {
                    "ubuntu_advantage": {
                        "features": {"disable_auto_attach": False},
                    }
                }
            ),
            (
                {
                    "ubuntu_advantage": {
                        "features": {"disable_auto_attach": True},
                    }
                }
            ),
        ],
    )
    @mock.patch(f"{MPATH}._should_auto_attach")
    @mock.patch(f"{MPATH}._auto_attach")
    @mock.patch(f"{MPATH}._attach")
    def test_no_fallback_attach(
        self,
        m_attach,
        m_auto_attach,
        m_should_auto_attach,
        cfg,
        is_pro,
    ):
        """Checks that attach is not called in the case where we want only to
        enable or disable pro auto-attach.
        """
        m_should_auto_attach.return_value = is_pro
        handle("nomatter", cfg=cfg, cloud=self.cloud, args=None)
        assert not m_attach.call_args_list

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
            handle("nomatter", cfg=cfg, **handle_kwargs)
        assert 0 == m_configure_ua.call_count

    @pytest.mark.parametrize(
        "cfg, match",
        [
            pytest.param(
                {"ubuntu_advantage": [0, 1]},
                "'ubuntu_advantage' should be a dict, not a list",
                id="on_non_dict_config",
            ),
            pytest.param(
                {"ubuntu_advantage": {"features": [0, 1]}},
                "'ubuntu_advantage.features' should be a dict, not a list",
                id="on_non_dict_ua_section",
            ),
        ],
    )
    def test_handle_errors(self, cfg, match):
        with pytest.raises(RuntimeError, match=match):
            handle(
                "nomatter",
                cfg=cfg,
                cloud=self.cloud,
                args=None,
            )

    @mock.patch(f"{MPATH}.subp.subp")
    def test_ua_config_error_invalid_url(self, m_subp, caplog):
        """Errors from pro config command are raised."""
        cfg = {
            "ubuntu_advantage": {
                "token": "SomeToken",
                "config": {"http_proxy": "not-a-valid-url"},
            }
        }
        m_subp.side_effect = subp.ProcessExecutionError(
            'Failure enabling "http_proxy"'
        )
        with pytest.raises(
            ValueError,
            match=re.escape(
                "Invalid ubuntu_advantage configuration:\nExpected URL scheme"
                " http/https for ua:config:http_proxy"
            ),
        ):
            handle(
                "nomatter",
                cfg=cfg,
                cloud=self.cloud,
                args=None,
            )
        assert not caplog.text

    @mock.patch(f"{MPATH}._should_auto_attach", return_value=False)
    @mock.patch(f"{MPATH}.subp.subp")
    def test_fallback_to_attach_no_token(
        self, m_subp, m_should_auto_attach, caplog
    ):
        cfg = {"ubuntu_advantage": {"enable": ["esm"]}}
        with pytest.raises(
            RuntimeError,
            match=re.escape(
                "`ubuntu_advantage.token` required in non-Pro Ubuntu"
                " instances."
            ),
        ):
            handle(
                "nomatter",
                cfg=cfg,
                cloud=self.cloud,
                args=None,
            )
        assert [] == m_subp.call_args_list
        assert (
            "`ubuntu_advantage.token` required in non-Pro Ubuntu"
            " instances.\n"
        ) in caplog.text


class TestShouldAutoAttach:
    def test_should_auto_attach_error(self, caplog, fake_uaclient):
        m_should_auto_attach = mock.Mock()
        m_should_auto_attach.should_auto_attach.side_effect = (
            FakeUserFacingError("Some error")  # noqa: E501
        )
        sys.modules[
            "uaclient.api.u.pro.attach.auto.should_auto_attach.v1"
        ] = m_should_auto_attach
        assert not _should_auto_attach({})
        assert "Error during `should_auto_attach`: Some error" in caplog.text
        assert (
            "Unable to determine if this is an Ubuntu Pro instance."
            " Fallback to normal UA attach." in caplog.text
        )

    @pytest.mark.parametrize(
        "ua_section, expected_result",
        [
            ({}, None),
            ({"features": {"disable_auto_attach": False}}, None),
            # The user explicitly disables auto-attach, therefore we do not do
            # it:
            ({"features": {"disable_auto_attach": True}}, False),
        ],
    )
    def test_happy_path(
        self, ua_section, expected_result, caplog, fake_uaclient
    ):
        m_should_auto_attach = mock.Mock()
        sys.modules[
            "uaclient.api.u.pro.attach.auto.should_auto_attach.v1"
        ] = m_should_auto_attach
        should_auto_attach_value = object()
        m_should_auto_attach.should_auto_attach.return_value.should_auto_attach = (  # noqa: E501
            should_auto_attach_value
        )
        if expected_result is None:  # UA API does respond
            assert should_auto_attach_value == _should_auto_attach(ua_section)
            assert (
                "Checking if the instance can be attached to Ubuntu Pro took"
                in caplog.text
            )
        else:  # cloud-init does respond
            assert expected_result == _should_auto_attach(ua_section)
            assert not caplog.text


class TestAutoAttach:

    ua_section: dict = {}

    def test_full_auto_attach_error(self, caplog, mocker, fake_uaclient):
        mocker.patch.dict("sys.modules")
        sys.modules["uaclient.config"] = mock.Mock()
        m_full_auto_attach = mock.Mock()
        m_full_auto_attach.full_auto_attach.side_effect = FakeUserFacingError(
            "Some error"
        )
        sys.modules[
            "uaclient.api.u.pro.attach.auto.full_auto_attach.v1"
        ] = m_full_auto_attach
        expected_msg = "Error during `full_auto_attach`: Some error"
        with pytest.raises(RuntimeError, match=re.escape(expected_msg)):
            _auto_attach(self.ua_section)
        assert expected_msg in caplog.text

    def test_happy_path(self, caplog, mocker, fake_uaclient):
        mocker.patch.dict("sys.modules")
        sys.modules["uaclient.config"] = mock.Mock()
        sys.modules[
            "uaclient.api.u.pro.attach.auto.full_auto_attach.v1"
        ] = mock.Mock()
        _auto_attach(self.ua_section)
        assert "Attaching to Ubuntu Pro took" in caplog.text


class TestAttach:
    @mock.patch(f"{MPATH}.configure_ua")
    def test_attach_without_token_raises_error(self, m_configure_ua):
        with pytest.raises(
            RuntimeError,
            match=(
                "`ubuntu_advantage.token` required in non-Pro Ubuntu"
                " instances."
            ),
        ):
            _attach({"enable": ["esm"]})
        assert [] == m_configure_ua.call_args_list


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


@mock.patch(f"{MPATH}.subp.subp")
class TestSetUAConfig:
    def test_valid_config(self, m_subp, caplog):
        ua_config = {
            "http_proxy": "http://some-proxy:8088",
            "https_proxy": "https://user:pass@some-proxy:8088",
            "global_apt_https_proxy": "https://some-global-apt-proxy:8088/",
            "global_apt_http_proxy": "http://some-global-apt-proxy:8088/",
            "ua_apt_http_proxy": "http://10.0.10.10:3128",
            "ua_apt_https_proxy": "https://10.0.10.10:3128",
        }
        set_ua_config(ua_config)
        for ua_arg, redacted_arg in [
            (
                "http_proxy=http://some-proxy:8088",
                "http_proxy=REDACTED",
            ),
            (
                "https_proxy=https://user:pass@some-proxy:8088",
                "https_proxy=REDACTED",
            ),
            (
                "global_apt_https_proxy=https://some-global-apt-proxy:8088/",
                "global_apt_https_proxy=REDACTED",
            ),
            (
                "global_apt_http_proxy=http://some-global-apt-proxy:8088/",
                "global_apt_http_proxy=REDACTED",
            ),
            (
                "ua_apt_http_proxy=http://10.0.10.10:3128",
                "ua_apt_http_proxy=REDACTED",
            ),
            (
                "ua_apt_https_proxy=https://10.0.10.10:3128",
                "ua_apt_https_proxy=REDACTED",
            ),
        ]:
            assert (
                mock.call(
                    ["pro", "config", "set", ua_arg],
                    logstring=["pro", "config", "set", redacted_arg],
                )
                in m_subp.call_args_list
            )
            assert f"Enabling UA config {redacted_arg}\n" in caplog.text
            assert ua_arg not in caplog.text

        assert 6 == m_subp.call_count

    def test_ua_config_unset(self, m_subp, caplog):
        ua_config = {
            "https_proxy": "https://user:pass@some-proxy:8088",
            "http_proxy": None,
        }
        set_ua_config(ua_config)
        for call in [
            mock.call(["pro", "config", "unset", "http_proxy"]),
            mock.call(
                [
                    "pro",
                    "config",
                    "set",
                    "https_proxy=https://user:pass@some-proxy:8088",
                ],
                logstring=["pro", "config", "set", "https_proxy=REDACTED"],
            ),
        ]:
            assert call in m_subp.call_args_list
        assert 2 == m_subp.call_count
        assert "Enabling UA config https_proxy=REDACTED\n" in caplog.text
        assert "https://user:pass@some-proxy:8088" not in caplog.text
        assert "Disabling UA config for http_proxy\n" in caplog.text

    def test_ua_config_error_non_string_values(self, m_subp, caplog):
        """ValueError raised for any values expected as string type."""
        ua_config = {
            "global_apt_http_proxy": "noscheme",
            "http_proxy": ["no-proxy"],
            "https_proxy": 3.14,
        }
        match = re.escape(
            "Invalid ubuntu_advantage configuration:\n"
            "Expected URL scheme http/https for"
            " ua:config:global_apt_http_proxy\n"
            "Expected a URL for ua:config:http_proxy\n"
            "Expected a URL for ua:config:https_proxy"
        )
        with pytest.raises(ValueError, match=match):
            set_ua_config(ua_config)
        assert 0 == m_subp.call_count
        assert not caplog.text

    def test_ua_config_unknown_prop(self, m_subp, caplog):
        """On unknown config props, a log is issued and the prop is set."""
        ua_config = {"asdf": "qwer"}
        set_ua_config(ua_config)
        assert [
            mock.call(
                ["pro", "config", "set", "asdf=qwer"],
                logstring=["pro", "config", "set", "asdf=REDACTED"],
            )
        ] == m_subp.call_args_list
        assert "qwer" not in caplog.text
        assert (
            "Not validating unknown ubuntu_advantage.config.asdf property\n"
            in caplog.text
        )

    def test_ua_config_wrong_type(self, m_subp, caplog):
        ua_config = ["asdf", "qwer"]
        with pytest.raises(
            RuntimeError,
            match=(
                "ubuntu_advantage: config should be a dict, not"
                " a list; skipping enabling config parameters"
            ),
        ):
            set_ua_config(ua_config)
        assert 0 == m_subp.call_count
        assert not caplog.text

    def test_set_ua_config_error(self, m_subp, caplog):
        ua_config = {
            "https_proxy": "https://user:pass@some-proxy:8088",
        }
        # Simulate UA error
        m_subp.side_effect = subp.ProcessExecutionError(
            "Invalid proxy: https://user:pass@some-proxy:8088"
        )
        with pytest.raises(
            RuntimeError,
            match=re.escape(
                "Failure enabling/disabling Ubuntu Advantage config(s):"
                ' "https_proxy"'
            ),
        ):
            set_ua_config(ua_config)
        assert 1 == m_subp.call_count
        assert "https://user:pass@some-proxy:8088" not in caplog.text
        assert "Enabling UA config https_proxy=REDACTED\n" in caplog.text
        assert 'Failure enabling/disabling "https_proxy":\n' in caplog.text

    def test_unset_ua_config_error(self, m_subp, caplog):
        ua_config = {"https_proxy": None}
        # Simulate UA error
        m_subp.side_effect = subp.ProcessExecutionError(
            "Error unsetting https_proxy"
        )
        with pytest.raises(
            RuntimeError,
            match=re.escape(
                "Failure enabling/disabling Ubuntu Advantage config(s): "
                '"https_proxy"'
            ),
        ):
            set_ua_config(ua_config)
        assert 1 == m_subp.call_count
        assert "https://user:pass@some-proxy:8088" not in caplog.text
        assert "Disabling UA config for https_proxy\n" in caplog.text
        assert 'Failure enabling/disabling "https_proxy":\n' in caplog.text
