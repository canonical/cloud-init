# This file is part of cloud-init. See LICENSE file for license information.

import base64
import datetime
from unittest import mock

import pytest
import requests

from cloudinit import version
from cloudinit.sources.azure import errors
from cloudinit.url_helper import UrlError


@pytest.fixture()
def agent_string():
    yield f"agent=Cloud-Init/{version.version_string()}"


@pytest.fixture()
def fake_utcnow():
    timestamp = datetime.datetime.utcnow()
    with mock.patch.object(errors, "datetime", autospec=True) as m:
        m.utcnow.return_value = timestamp
        yield timestamp


@pytest.fixture()
def fake_vm_id():
    vm_id = "fake-vm-id"
    with mock.patch.object(errors.identity, "query_vm_id", autospec=True) as m:
        m.return_value = vm_id
        yield vm_id


def quote_csv_value(value: str) -> str:
    """Match quoting behavior, if needed for given string."""
    if any([x in value for x in ("\n", "\r", "'")]):
        value = value.replace("'", "''")
        value = f"'{value}'"

    return value


@pytest.mark.parametrize("reason", ["foo", "foo bar", "foo'bar"])
@pytest.mark.parametrize(
    "supporting_data",
    [
        {},
        {
            "foo": "bar",
        },
        {
            "foo": "bar",
            "count": 4,
        },
        {
            "csvcheck": "",
        },
        {
            "csvcheck": "trailingspace ",
        },
        {
            "csvcheck": "\r\n",
        },
        {
            "csvcheck": "\n",
        },
        {
            "csvcheck": "\t",
        },
        {
            "csvcheck": "x\nx",
        },
        {
            "csvcheck": "x\rx",
        },
        {
            "csvcheck": '"',
        },
        {
            "csvcheck": '""',
        },
        {
            "csvcheck": "'",
        },
        {
            "csvcheck": "''",
        },
        {
            "csvcheck": "xx'xx'xx",
        },
        {
            "csvcheck": ",'|~!@#$%^&*()[]\\{}|;':\",./<>?x\nnew\r\nline",
        },
    ],
)
def test_reportable_errors(
    fake_utcnow,
    fake_vm_id,
    reason,
    supporting_data,
):
    error = errors.ReportableError(
        reason=reason,
        supporting_data=supporting_data,
    )

    data = [
        "result=error",
        quote_csv_value(f"reason={reason}"),
        f"agent=Cloud-Init/{version.version_string()}",
    ]
    data += [quote_csv_value(f"{k}={v}") for k, v in supporting_data.items()]
    data += [
        f"vm_id={fake_vm_id}",
        f"timestamp={fake_utcnow.isoformat()}",
        "documentation_url=https://aka.ms/linuxprovisioningerror",
    ]

    assert error.as_encoded_report() == "|".join(data)


def test_dhcp_lease():
    error = errors.ReportableErrorDhcpLease(duration=5.6, interface="foo")

    assert error.reason == "failure to obtain DHCP lease"
    assert error.supporting_data["duration"] == 5.6
    assert error.supporting_data["interface"] == "foo"


def test_dhcp_interface_not_found():
    error = errors.ReportableErrorDhcpInterfaceNotFound(duration=5.6)

    assert error.reason == "failure to find DHCP interface"
    assert error.supporting_data["duration"] == 5.6


@pytest.mark.parametrize(
    "exception,reason",
    [
        (
            UrlError(
                requests.ConnectionError(),
            ),
            "connection error querying IMDS",
        ),
        (
            UrlError(
                requests.ConnectTimeout(),
            ),
            "connection timeout querying IMDS",
        ),
        (
            UrlError(
                requests.ReadTimeout(),
            ),
            "read timeout querying IMDS",
        ),
        (
            UrlError(
                Exception(),
                code=404,
            ),
            "http error 404 querying IMDS",
        ),
        (
            UrlError(
                Exception(),
                code=500,
            ),
            "http error 500 querying IMDS",
        ),
        (
            UrlError(
                requests.HTTPError(),
                code=None,
            ),
            "unexpected error querying IMDS",
        ),
    ],
)
def test_imds_url_error(exception, reason):
    duration = 123.4
    fake_url = "fake://url"

    exception.url = fake_url
    error = errors.ReportableErrorImdsUrlError(
        exception=exception, duration=duration
    )

    assert error.reason == reason
    assert error.supporting_data["duration"] == duration
    assert error.supporting_data["exception"] == repr(exception)
    assert error.supporting_data["url"] == fake_url


def test_imds_metadata_parsing_exception():
    exception = ValueError("foobar")

    error = errors.ReportableErrorImdsMetadataParsingException(
        exception=exception
    )

    assert error.reason == "error parsing IMDS metadata"
    assert error.supporting_data["exception"] == repr(exception)


def test_unhandled_exception():
    source_error = None
    try:
        raise ValueError("my value error")
    except Exception as exception:
        source_error = exception

    error = errors.ReportableErrorUnhandledException(source_error)

    traceback_base64 = error.supporting_data["traceback_base64"]
    assert isinstance(traceback_base64, str)

    trace = base64.b64decode(traceback_base64).decode("utf-8")
    assert trace.startswith("Traceback")
    assert "raise ValueError" in trace
    assert trace.endswith("ValueError: my value error\n")

    quoted_value = quote_csv_value(f"exception={source_error!r}")
    assert f"|{quoted_value}|" in error.as_encoded_report()


def test_imds_invalid_metadata():
    key = "compute"
    value = "Running"
    error = errors.ReportableErrorImdsInvalidMetadata(key=key, value=value)

    assert error.reason == "invalid IMDS metadata for key=compute"
    assert error.supporting_data["key"] == key
    assert error.supporting_data["value"] == repr(value)
