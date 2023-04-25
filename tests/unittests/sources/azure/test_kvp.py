# This file is part of cloud-init. See LICENSE file for license information.


import pytest

from cloudinit.sources.azure import errors, kvp


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


class TestReportFailureViaKvp:
    def test_report_failure_via_kvp(self, caplog, telemetry_reporter):
        error = errors.ReportableError(reason="test")
        assert kvp.report_failure_via_kvp(error) is True
        assert (
            "KVP handler not enabled, skipping host report." not in caplog.text
        )

        report = {
            "key": "PROVISIONING_REPORT",
            "value": error.as_description(),
        }
        assert report in list(telemetry_reporter._iterate_kvps(0))

    def test_report_skipped_without_telemetry(self, caplog):
        error = errors.ReportableError(reason="test")

        assert kvp.report_failure_via_kvp(error) is False
        assert "KVP handler not enabled, skipping host report." in caplog.text


class TestReportSuccessViaKvp:
    def test_report_success_via_kvp(self, caplog, telemetry_reporter):
        assert kvp.report_success_via_kvp() is True
        assert (
            "KVP handler not enabled, skipping host report." not in caplog.text
        )

        report = {
            "key": "PROVISIONING_REPORT",
            "value": "result=success",
        }
        assert report in list(telemetry_reporter._iterate_kvps(0))

    def test_report_skipped_without_telemetry(self, caplog):
        assert kvp.report_success_via_kvp() is False
        assert "KVP handler not enabled, skipping host report." in caplog.text
