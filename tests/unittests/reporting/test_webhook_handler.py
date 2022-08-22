# This file is part of cloud-init. See LICENSE file for license information.
import time
from contextlib import suppress
from unittest.mock import PropertyMock

import pytest
import responses

from cloudinit.reporting import flush_events
from cloudinit.reporting.events import report_start_event
from cloudinit.reporting.handlers import WebHookHandler


class TestWebHookHandler:
    @pytest.fixture(autouse=True)
    def setup(self, mocker):
        handler = WebHookHandler(endpoint="http://localhost")
        m_registered_items = mocker.patch(
            "cloudinit.registry.DictRegistry.registered_items",
            new_callable=PropertyMock,
        )
        m_registered_items.return_value = {"webhook": handler}

    @responses.activate
    def test_webhook_handler(self, caplog):
        """Test the happy path."""
        responses.add(responses.POST, "http://localhost", status=200)
        report_start_event("name", "description")
        flush_events()
        assert 1 == caplog.text.count(
            "Read from http://localhost (200, 0b) after 1 attempts"
        )

    @responses.activate
    def test_404(self, caplog):
        """Test failure"""
        responses.add(responses.POST, "http://localhost", status=404)
        report_start_event("name", "description")
        flush_events()
        assert 1 == caplog.text.count("Failed posting event")

    @responses.activate
    def test_background_processing(self, caplog):
        """Test that processing happens in background.

        In the non-flush case, ensure that the event is still posted.
        Since the event is posted in the background, wait while looping.
        """
        responses.add(responses.POST, "http://localhost", status=200)
        report_start_event("name", "description")
        start_time = time.time()
        while time.time() - start_time < 3:
            with suppress(AssertionError):
                assert (
                    "Read from http://localhost (200, 0b) after 1 attempts"
                    in caplog.text
                )
                break
        else:
            pytest.fail("Never got expected log message")

    @responses.activate
    @pytest.mark.parametrize(
        "num_failures,expected_log_count,expected_cancel",
        [(2, 2, False), (3, 3, True), (50, 3, True)],
    )
    def test_failures_cancel_flush(
        self, caplog, num_failures, expected_log_count, expected_cancel
    ):
        """Test that too many failures will cancel further processing on flush.

        2 messages should not cancel on flush
        3 or more should cancel on flush
        The number of received messages will be based on how many have
        been processed before the flush was initiated.
        """
        responses.add(responses.POST, "http://localhost", status=404)
        for _ in range(num_failures):
            report_start_event("name", "description")
        flush_events()
        # Force a context switch. Without this, it's possible that the
        # expected log message hasn't made it to the log file yet
        time.sleep(0.01)

        # If we've pushed a bunch of messages, any number could have been
        # processed before we get to the flush.
        assert (
            expected_log_count
            <= caplog.text.count("Failed posting event")
            <= num_failures
        )
        cancelled_message = (
            "Multiple consecutive failures in WebHookHandler. "
            "Cancelling all queued events"
        )
        if expected_cancel:
            assert cancelled_message in caplog.text
        else:
            assert cancelled_message not in caplog.text

    @responses.activate
    def test_multiple_failures_no_flush(self, caplog):
        """Test we don't cancel posting if flush hasn't been requested.

        Since processing happens in the background, wait in a loop
        for all messages to be posted
        """
        responses.add(responses.POST, "http://localhost", status=404)
        for _ in range(10):
            report_start_event("name", "description")
        start_time = time.time()
        while time.time() - start_time < 3:
            with suppress(AssertionError):
                assert 10 == caplog.text.count("Failed posting event")
                break
            time.sleep(0.01)  # Force context switch
        else:
            pytest.fail(
                "Expected 20 failures, only got "
                f"{caplog.text.count('Failed posting event')}"
            )
