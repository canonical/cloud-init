# This file is part of cloud-init. See LICENSE file for license information.

import base64
import datetime
from unittest import mock

import pytest

from cloudinit import version
from cloudinit.sources.azure import errors


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

    assert error.as_description() == "|".join(data)


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
    assert f"|{quoted_value}|" in error.as_description()
