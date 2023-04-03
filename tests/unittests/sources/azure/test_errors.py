# This file is part of cloud-init. See LICENSE file for license information.

import base64
import datetime

import pytest

from cloudinit import version
from cloudinit.sources.azure import errors


@pytest.fixture()
def agent_string():
    yield f"agent=Cloud-Init/{version.version_string()}"


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
@pytest.mark.parametrize(
    "vm_id", [None, "527c2691-029f-fe4c-b1f4-a4da7ebac2cf"]
)
def test_reportable_errors(
    agent_string,
    monkeypatch,
    reason,
    supporting_data,
    vm_id,
):
    monkeypatch.setattr(errors, "query_vm_id", lambda: vm_id)
    timestamp = datetime.datetime.utcnow()

    error = errors.ReportableError(
        reason=reason,
        supporting_data=supporting_data,
        timestamp=timestamp,
    )

    description_parts = [
        "PROVISIONING_ERROR: error=PROVISIONING_FAILED_CLOUDINIT",
        quote_csv_value(f"reason={reason}"),
        agent_string,
        "documentation_url=https://aka.ms/linuxprovisioningerror",
        f"timestamp={timestamp.isoformat()}",
    ]

    if vm_id:
        description_parts.append(f"vm_id={vm_id}")

    if supporting_data:
        description_parts.extend(
            [quote_csv_value(f"{k}={v}") for k, v in supporting_data.items()]
        )

    assert error.as_description() == "|".join(description_parts)


@pytest.mark.parametrize(
    "vm_id", [None, "527c2691-029f-fe4c-b1f4-a4da7ebac2cf"]
)
def test_unhandled_exception(monkeypatch, vm_id):
    monkeypatch.setattr(errors, "query_vm_id", lambda: vm_id)
    source_error = None
    try:
        raise ValueError("my value error")
    except Exception as exception:
        source_error = exception

    error = errors.ReportableErrorUnhandledException(source_error)
    trace = base64.b64decode(error.supporting_data["traceback_base64"]).decode(
        "utf-8"
    )

    quoted_value = quote_csv_value(f"exception={source_error!r}")
    assert f"|{quoted_value}|" in error.as_description()
    assert trace.startswith("Traceback")
    assert "raise ValueError" in trace
    assert trace.endswith("ValueError: my value error\n")
