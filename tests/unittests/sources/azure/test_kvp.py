# This file is part of cloud-init. See LICENSE file for license information.

from datetime import datetime
from unittest import mock

import pytest

from cloudinit import version
from cloudinit.sources.azure import errors, kvp


@pytest.fixture()
def fake_utcnow():
    timestamp = datetime.utcnow()
    with mock.patch.object(kvp, "datetime", autospec=True) as m:
        m.utcnow.return_value = timestamp
        yield timestamp


@pytest.fixture
def fake_vm_id(mocker):
    vm_id = "foo"
    mocker.patch(
        "cloudinit.sources.azure.identity.query_vm_id", return_value=vm_id
    )
    yield vm_id


@pytest.fixture
def telemetry_reporter(tmp_path):
    kvp_file_path = tmp_path / "kvp_pool_file"
    kvp_file_path.write_bytes(b"")
    reporter = kvp.handlers.HyperVKvpReportingHandler(
        kvp_file_path=str(kvp_file_path)
    )

    kvp.instantiated_handler_registry.register_item("telemetry", reporter)
    yield reporter
    kvp.instantiated_handler_registry.unregister_item("telemetry")


class TestReportFailureToHost:
    def test_report_failure_to_host(self, caplog, telemetry_reporter, mocker):
        mocker.patch(
            "cloudinit.sources.azure.identity.query_vm_id", return_value="foo"
        )
        error = errors.ReportableError(reason="test")
        assert kvp.report_failure_to_host(error) is True
        assert (
            "KVP handler not enabled, skipping host report." not in caplog.text
        )

        report = {
            "key": "PROVISIONING_REPORT",
            "value": error.as_encoded_report(),
        }
        assert report in list(telemetry_reporter._iterate_kvps(0))

    def test_report_skipped_without_telemetry(self, caplog, mocker):
        mocker.patch(
            "cloudinit.sources.azure.identity.query_vm_id", return_value="foo"
        )
        error = errors.ReportableError(reason="test")

        assert kvp.report_failure_to_host(error) is False
        assert "KVP handler not enabled, skipping host report." in caplog.text


class TestReportSuccessToHost:
    def test_report_success_to_host(
        self, caplog, fake_utcnow, fake_vm_id, telemetry_reporter
    ):
        assert kvp.report_success_to_host() is True
        assert (
            "KVP handler not enabled, skipping host report." not in caplog.text
        )

        report_value = errors.encode_report(
            [
                "result=success",
                f"agent=Cloud-Init/{version.version_string()}",
                f"timestamp={fake_utcnow.isoformat()}",
                f"vm_id={fake_vm_id}",
            ]
        )

        report = {
            "key": "PROVISIONING_REPORT",
            "value": report_value,
        }
        assert report in list(telemetry_reporter._iterate_kvps(0))

    def test_report_skipped_without_telemetry(self, caplog, mocker):
        mocker.patch(
            "cloudinit.sources.azure.identity.query_vm_id", return_value="foo"
        )
        assert kvp.report_success_to_host() is False
        assert "KVP handler not enabled, skipping host report." in caplog.text
