# This file is part of cloud-init. See LICENSE file for license information.

from datetime import datetime, timezone
from unittest import mock

import pytest

from cloudinit import version
from cloudinit.sources.azure import errors, kvp


@pytest.fixture()
def fake_utcnow():
    timestamp = datetime.now(timezone.utc)
    with mock.patch.object(kvp, "datetime", autospec=True) as m:
        m.now.return_value = timestamp
        yield timestamp


@pytest.fixture
def fake_vm_id(mocker):
    vm_id = "foo"
    mocker.patch(
        "cloudinit.sources.azure.kvp.identity.query_vm_id", return_value=vm_id
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
    def test_report_via_kvp(self, caplog, fake_vm_id, telemetry_reporter):
        error = errors.ReportableError(reason="test")
        encoded_report = error.as_encoded_report(vm_id="fake-vm-id")

        assert kvp.report_via_kvp(encoded_report) is True
        assert (
            "KVP handler not enabled, skipping host report." not in caplog.text
        )

        report = {
            "key": "PROVISIONING_REPORT",
            "value": encoded_report,
        }
        assert report in list(telemetry_reporter._iterate_kvps(0))

    def test_report_skipped_without_telemetry(self, caplog):
        assert kvp.report_via_kvp("test report") is False
        assert "KVP handler not enabled, skipping host report." in caplog.text


class TestReportSuccessToHost:
    def test_report_success_to_host(
        self, caplog, fake_utcnow, fake_vm_id, telemetry_reporter
    ):
        assert kvp.report_success_to_host(vm_id=fake_vm_id) is True
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

    def test_report_skipped_without_telemetry(self, caplog):
        assert kvp.report_success_to_host(vm_id="fake") is False
        assert "KVP handler not enabled, skipping host report." in caplog.text


class TestGetKvpHandler:
    def test_vm_id_set_by_get_kvp_handler(
        self, telemetry_reporter, fake_vm_id
    ):
        """Test get_kvp_handler sets vm_id on the handler."""
        handler = kvp.get_kvp_handler()
        assert handler is telemetry_reporter

        # get_kvp_handler() should have set vm_id via identity.query_vm_id()
        assert handler.vm_id == fake_vm_id

        with mock.patch(
            "cloudinit.sources.azure.kvp.identity.query_vm_id",
            side_effect=AssertionError("should not be called twice"),
        ):
            handler_again = kvp.get_kvp_handler()
            assert handler_again.vm_id == fake_vm_id

    def test_handles_vm_id_lookup_failure(self, telemetry_reporter, mocker):
        """Test handler gracefully handles identity.query_vm_id failure."""
        mocker.patch(
            "cloudinit.sources.azure.kvp.identity.query_vm_id",
            side_effect=RuntimeError("boom"),
        )
        # Also mock DMI to fail so we get ZERO_GUID
        mocker.patch(
            "cloudinit.reporting.handlers.dmi.read_dmi_data",
            return_value=None,
        )

        handler = kvp.get_kvp_handler()
        assert handler is telemetry_reporter
        # Falls back to DMI, which returns None, so stays ZERO_GUID
        assert (
            handler.vm_id == kvp.handlers.HyperVKvpReportingHandler.ZERO_GUID
        )
