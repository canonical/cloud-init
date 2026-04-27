# This file is part of cloud-init. See LICENSE file for license information.

"""Tests for cloudinit.log"""

import datetime
import io
import json
import logging
import time
from typing import cast

import pytest

from cloudinit import lifecycle, util
from cloudinit.analyze.dump import CLOUD_INIT_ASCTIME_FMT
from cloudinit.log import loggers


@pytest.fixture
def ci_logs():
    return io.StringIO()


@pytest.fixture
def log(ci_logs):
    # set up a logger like cloud-init does in setup_logging, but instead
    # of sys.stderr, we'll plug in a StringIO() object so we can see
    # what gets logged
    logging.Formatter.converter = time.gmtime
    ci_root = logging.getLogger()
    console = logging.StreamHandler(ci_logs)
    console.setFormatter(logging.Formatter(loggers.DEFAULT_LOG_FORMAT))
    console.setLevel(logging.DEBUG)
    ci_root.addHandler(console)
    ci_root.setLevel(logging.DEBUG)
    LOG = logging.getLogger("test_cloudinit_logger")
    return LOG


class TestCloudInitLogger:

    def test_logger_uses_gmtime(self, log, ci_logs):
        """Test that log message have timestamp in UTC (gmtime)"""

        # Log a message, extract the timestamp from the log entry
        # convert to datetime, and compare to a utc timestamp before
        # and after the logged message.

        # Due to loss of precision in the LOG timestamp, subtract and add
        # time to the utc stamps for comparison
        #
        # utc_before: 2017-08-23 14:19:42.569299
        # parsed dt : 2017-08-23 14:19:43.069000
        # utc_after : 2017-08-23 14:19:43.570064

        def remove_tz(_dt: datetime.datetime) -> datetime.datetime:
            """
            Removes the timezone object from an aware datetime dt without
            conversion of date and time data
            """
            return _dt.replace(tzinfo=None)

        utc_before = remove_tz(
            datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(0, 0.5)
        )
        log.error("Test message")
        utc_after = remove_tz(
            datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(0, 0.5)
        )

        # extract timestamp from log:
        # 2017-08-23 14:19:43,069 - test_log.py[ERROR]: Test message
        logstr = ci_logs.getvalue().splitlines()[0]
        timestampstr = logstr.split(" - ")[0]
        parsed_dt = datetime.datetime.strptime(
            timestampstr, CLOUD_INIT_ASCTIME_FMT
        )

        assert utc_before < parsed_dt
        assert parsed_dt < utc_after
        assert utc_before < utc_after
        assert utc_after > parsed_dt


class TestDeprecatedLogs:
    def test_deprecated_log_level(self, caplog):
        logger = cast(loggers.CustomLoggerType, logging.getLogger())
        logger.deprecated("deprecated message")
        assert "DEPRECATED" == caplog.records[0].levelname
        assert "deprecated message" in caplog.text

    def test_trace_log_level(self, caplog):
        logger = cast(loggers.CustomLoggerType, logging.getLogger())
        logger.setLevel(logging.NOTSET)
        logger.trace("trace message")
        assert "TRACE" == caplog.records[0].levelname
        assert "trace message" in caplog.text

    def test_security_log_level(self, caplog):
        logger = cast(loggers.CustomLoggerType, logging.getLogger())
        logger.setLevel(logging.NOTSET)
        logger.security("security message")
        assert "SECURITY" == caplog.records[0].levelname
        assert "security message" in caplog.text

    @pytest.mark.parametrize(
        "expected_log_level, deprecation_info_boundary",
        (
            pytest.param(
                "DEPRECATED",
                "19.2",
                id="test_same_deprecation_info_boundary_is_deprecated_level",
            ),
            pytest.param(
                "INFO",
                "19.1",
                id="test_lower_deprecation_info_boundary_is_info_level",
            ),
        ),
    )
    def test_deprecate_log_level_based_on_features(
        self,
        expected_log_level,
        deprecation_info_boundary,
        caplog,
        mocker,
        clear_deprecation_log,
    ):
        """Deprecation log level depends on key deprecation_version

        When DEPRECATION_INFO_BOUNDARY is set to a version number, and a key
        has a deprecated_version with a version greater than the boundary
        the log level is INFO instead of DEPRECATED. If
        DEPRECATION_INFO_BOUNDARY is set to the default, "devel", all
        deprecated keys are logged at level DEPRECATED.
        """
        mocker.patch.object(
            util.features,
            "DEPRECATION_INFO_BOUNDARY",
            deprecation_info_boundary,
        )
        lifecycle.deprecate(
            deprecated="some key",
            deprecated_version="19.2",
            extra_message="dont use it",
        )
        assert expected_log_level == caplog.records[0].levelname
        assert (
            "some key is deprecated in 19.2 and scheduled to be removed in"
            " 24.2" in caplog.text
        )

    def test_log_deduplication(self, caplog):
        loggers.define_extra_loggers()
        lifecycle.deprecate(
            deprecated="stuff",
            deprecated_version="19.1",
            extra_message=":)",
        )
        lifecycle.deprecate(
            deprecated="stuff",
            deprecated_version="19.1",
            extra_message=":)",
        )
        lifecycle.deprecate(
            deprecated="stuff",
            deprecated_version="19.1",
            extra_message=":)",
            schedule=6,
        )
        assert 2 == len(caplog.records)


def test_logger_prints_to_stderr(capsys, caplog):
    message = "to stdout"
    loggers.setup_basic_logging()
    logging.getLogger().warning(message)
    assert message in capsys.readouterr().err


class TestSecurityLogs:
    def test_logger_prints_security_as_json_lines(
        self, tmp_path, capsys, caplog
    ):
        """Security logs accepts dict as payload and logs JSON lines."""
        log_file = tmp_path / "cloud-init-output.log"
        loggers.setup_basic_logging()
        root = cast(loggers.CustomLoggerType, logging.getLogger())
        loggers.setup_security_logging(root=root, log_file=str(log_file))
        message = {"key": "value"}  # Security logs expect python dict
        root.security(message)
        logged_event = json.loads(log_file.read_text())
        assert logged_event.pop("datetime"), "Missing expected datetime in log"
        assert logged_event == message
        # SECURITY level logs are not reflected to stderr
        assert "" == capsys.readouterr().err

    def test_logger_requires_dict_payload(self, tmp_path, capsys):
        """Security logs will error when payload message is not a dict.

        Future-proofing additional call-sites from calling
        LOG.security("non-dict payload")
        """
        log_file = tmp_path / "cloud-init-output.log"
        loggers.setup_basic_logging()
        root = cast(loggers.CustomLoggerType, logging.getLogger())
        loggers.setup_security_logging(root=root, log_file=str(log_file))
        root.security("some non-dict payload")
        # Invalid security payloads are not logged and don't crash cloud-init.
        assert "" == log_file.read_text()

    def test_setup_security_logging_idempotent(self, tmp_path):
        """Multiple setup_security_logging calls do not duplicate handlers."""
        log_file = str(tmp_path / "sec.log")
        root = logging.getLogger()
        loggers.setup_security_logging(root=root, log_file=log_file)
        loggers.setup_security_logging(root=root, log_file=log_file)
        security_handlers = [
            h
            for h in root.handlers
            if isinstance(h, logging.FileHandler)
            and h.baseFilename == log_file
        ]
        assert len(security_handlers) == 1

    def test_setup_security_logging_oserror_is_silent(self, mocker):
        """setup_security_logging silent return on unwritable log."""
        mocker.patch(
            "cloudinit.log.loggers.logging.FileHandler",
            side_effect=OSError("Permission denied"),
        )
        root = logging.getLogger()
        handlers_before = list(root.handlers)
        loggers.setup_security_logging(root=root, log_file="/any/path")
        # No new handler should have been attached.
        assert root.handlers == handlers_before

    def test_security_formatter_datetime_iso8601(self, tmp_path):
        """SecurityFormatter logs an ISO-8601 timestamp with offset."""
        import re

        log_file = tmp_path / "sec.log"
        loggers.setup_basic_logging()
        root = cast(loggers.CustomLoggerType, logging.getLogger())
        loggers.setup_security_logging(root=root, log_file=str(log_file))
        root.security({"event": "test"})
        logged = json.loads(log_file.read_text())
        # e.g. 2026-04-24T16:20:43.123+00:00
        iso8601_ms_tz = re.compile(
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+00:00$"
        )
        assert iso8601_ms_tz.match(
            logged["datetime"]
        ), f"Unexpected datetime format: {logged['datetime']}"

    def test_security_only_filter_passes_security_records(self):
        """SecurityOnlyFilter allows only SECURITY-level records through."""
        f = loggers.SecurityOnlyFilter()
        sec_record = logging.LogRecord(
            "test", loggers.SECURITY, "", 0, {}, (), None
        )
        warn_record = logging.LogRecord(
            "test", logging.WARNING, "", 0, "msg", (), None
        )
        assert f.filter(sec_record) is True
        assert f.filter(warn_record) is False

    def test_no_security_filter_blocks_security_records(self):
        """NoSecurityFilter blocks SECURITY-level records and passes others."""
        f = loggers.NoSecurityFilter()
        sec_record = logging.LogRecord(
            "test", loggers.SECURITY, "", 0, {}, (), None
        )
        warn_record = logging.LogRecord(
            "test", logging.WARNING, "", 0, "msg", (), None
        )
        assert f.filter(sec_record) is False
        assert f.filter(warn_record) is True

    def test_security_logs_absent_from_regular_stderr(self, tmp_path, capsys):
        """SECURITY records absent on stderr after setup_basic_logging."""
        log_file = tmp_path / "sec.log"
        loggers.setup_basic_logging()
        root = cast(loggers.CustomLoggerType, logging.getLogger())
        loggers.setup_security_logging(root=root, log_file=str(log_file))
        root.security({"event": "should-not-be-on-stderr"})
        assert "should-not-be-on-stderr" not in capsys.readouterr().err
