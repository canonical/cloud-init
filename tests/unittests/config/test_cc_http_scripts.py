import re
import pytest

from logging import Logger
from unittest import mock
from textwrap import dedent
import urllib.request

from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from cloudinit.config.cc_http_scripts import handle, fetch_script
from tests.unittests.helpers import (
    skipUnlessJsonSchema,
)


class TestHandle:
    """Tests cc_http_scripts.handle()"""

    @pytest.mark.parametrize(
        "script, environments, want, is_exception",
        [
            (
                dedent(
                    """\
                    #!/bin/sh
                    echo "hello world"
                    """
                ),
                {},
                "hello world\n",
                False,
            ),
            (
                dedent(
                    """\
                    #!/bin/sh
                    printenv | egrep "CC_HTTP_SCRIPTS_ENV(1|2)"
                    """
                ),
                {
                    "CC_HTTP_SCRIPTS_ENV1": "value1",
                    "CC_HTTP_SCRIPTS_ENV2": "value2",
                },
                "CC_HTTP_SCRIPTS_ENV1=value1\nCC_HTTP_SCRIPTS_ENV2=value2\n",
                False,
            ),
            (
                dedent(
                    """\
                    #!/bin/sh
                    exit 1
                    """
                ),
                {},
                "",
                True,
            ),
            (
                dedent(
                    """\
                    #!/bin/sh
                    echo "invalid" 1>&2    
                    exit 1
                    """
                ),
                {},
                "invalid\n",
                True,
            ),
        ]
    )
    @mock.patch("cloudinit.config.cc_http_scripts.fetch_script")
    @mock.patch("cloudinit.config.cc_http_scripts.LOG")
    def test_handle(
        self,
        m_LOG,
        m_fetch_script,
        script,
        environments,
        want,
        is_exception,
        capfd,
    ):
        m_fetch_script.return_value = script.encode("utf-8")
        cfg = {"http_scripts": [{
            "url": "http://example.com",
            "environments": environments,
        }]}

        handle(mock.Mock(), cfg, mock.Mock(), mock.Mock(), mock.Mock())
        output, _ = capfd.readouterr()
        assert output == want
        m_LOG.debug.assert_any_call(
            "fetch script: %s", "http://example.com",
        )
        m_LOG.debug.assert_any_call(
            "run script: %s", "http://example.com",
        )

        if is_exception:
            m_LOG.exception.assert_any_call(
                "url: %s", "http://example.com",
            )


class TestFetchScript:
    """Tests cc_http_scripts.fetch_script()"""

    @pytest.mark.parametrize(
        "url, error_msg",
        [
            ("http://example.com", None),
            ("https://example.com", None),
            ("example.com", "unknown url type: 'example.com'"),
        ]
    )
    @mock.patch("cloudinit.config.cc_http_scripts.urllib.request.urlopen")
    def test_fetch_script(
        self,
        m_urlopen: mock.MagicMock,
        url: str,
        error_msg: str,
    ):
        m_urlopen.return_value.__enter__.return_value.read.return_value = b"script"

        if error_msg is None:
            got = fetch_script(url)
            req = m_urlopen.call_args[0][0]
            assert m_urlopen.call_count == 1
            assert type(req) == urllib.request.Request
            assert req.full_url == url
            assert got == b"script"
        else:
            with pytest.raises(ValueError, match=error_msg):
                got = fetch_script(url)
            assert m_urlopen.call_count == 0


@skipUnlessJsonSchema()
class TestHttpScriptsSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        (
            ({"http_scripts": [{"url": "http://example.com"}]}, None),
            (
                {
                    "http_scripts": [
                        {"url": "http://example.com"},
                        {"url": "http://example.com"},
                    ]
                },
                None,
            ),
            (
                {
                    "http_scripts": [
                        {
                            "url": "http://example.com",
                            "environments": {
                                "ENV1": "value1",
                                "ENV2": "value2",
                            },
                        }
                    ]
                },
                None,
            ),
            # Invalid schemas
            (
                {"http_scripts": {"url": "http://example.com"}},
                re.escape(
                    "{'url': 'http://example.com'} is not of type 'array'"
                ),
            ),
            (
                {"http_scripts": [{}]},
                re.escape("http_scripts.0: 'url' is a required property"),
            ),
            (
                {
                    "http_scripts": [
                        {"environments": {"ENV1": "value1", "ENV2": "value2"}}
                    ]
                },
                re.escape("http_scripts.0: 'url' is a required property"),
            ),
            (
                {"http_scripts": [{"invalidprop": True}]},
                re.escape(
                    "Additional properties are not allowed ('invalidprop"
                ),
            ),
        ),
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        if error_msg is None:
            validate_cloudconfig_schema(config, get_schema(), strict=True)
        else:
            with pytest.raises(SchemaValidationError, match=error_msg):
                validate_cloudconfig_schema(config, get_schema(), strict=True)
