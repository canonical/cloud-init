# This file is part of cloud-init. See LICENSE file for license information.
import base64
import json
import os
import re
import struct
import time
import zlib
from unittest import mock

from cloudinit import util
from cloudinit.reporting import events, instantiated_handler_registry
from cloudinit.reporting.handlers import HyperVKvpReportingHandler

# TODO: Importing `errors` here is a hack to avoid a circular import.
# Without it, we have a azure->errors->identity->azure import loop, but
# long term we should restructure these modules to avoid the issue.
from cloudinit.sources.azure import errors  # noqa: F401
from cloudinit.sources.helpers import azure
from tests.unittests.helpers import CiTestCase


class TestKvpEncoding(CiTestCase):
    def test_encode_decode(self):
        kvp = {"key": "key1", "value": "value1"}
        kvp_reporting = HyperVKvpReportingHandler()
        data = kvp_reporting._encode_kvp_item(kvp["key"], kvp["value"])
        self.assertEqual(len(data), kvp_reporting.HV_KVP_RECORD_SIZE)
        decoded_kvp = kvp_reporting._decode_kvp_item(data)
        self.assertEqual(kvp, decoded_kvp)


class TextKvpReporter(CiTestCase):
    def setUp(self):
        super(TextKvpReporter, self).setUp()
        self.tmp_file_path = self.tmp_path("kvp_pool_file")
        util.ensure_file(self.tmp_file_path)

    def test_events_with_higher_incarnation_not_over_written(self):
        reporter = HyperVKvpReportingHandler(kvp_file_path=self.tmp_file_path)
        self.assertEqual(0, len(list(reporter._iterate_kvps(0))))

        reporter.publish_event(
            events.ReportingEvent("foo", "name1", "description")
        )
        reporter.publish_event(
            events.ReportingEvent("foo", "name2", "description")
        )
        reporter.q.join()
        self.assertEqual(2, len(list(reporter._iterate_kvps(0))))

        reporter3 = HyperVKvpReportingHandler(kvp_file_path=self.tmp_file_path)
        reporter3.incarnation_no = reporter.incarnation_no - 1
        reporter3.publish_event(
            events.ReportingEvent("foo", "name3", "description")
        )
        reporter3.q.join()
        self.assertEqual(3, len(list(reporter3._iterate_kvps(0))))

    def test_finish_event_result_is_logged(self):
        reporter = HyperVKvpReportingHandler(kvp_file_path=self.tmp_file_path)
        reporter.publish_event(
            events.FinishReportingEvent(
                "name2", "description1", result=events.status.FAIL
            )
        )
        reporter.q.join()
        self.assertIn("FAIL", list(reporter._iterate_kvps(0))[0]["value"])

    def test_file_operation_issue(self):
        os.remove(self.tmp_file_path)
        reporter = HyperVKvpReportingHandler(kvp_file_path=self.tmp_file_path)
        reporter.publish_event(
            events.FinishReportingEvent(
                "name2", "description1", result=events.status.FAIL
            )
        )
        reporter.q.join()

    def test_event_very_long(self):
        reporter = HyperVKvpReportingHandler(kvp_file_path=self.tmp_file_path)
        description = "ab" * reporter.HV_KVP_AZURE_MAX_VALUE_SIZE
        long_event = events.FinishReportingEvent(
            "event_name", description, result=events.status.FAIL
        )
        reporter.publish_event(long_event)
        reporter.q.join()
        kvps = list(reporter._iterate_kvps(0))
        self.assertEqual(3, len(kvps))

        # restore from the kvp to see the content are all there
        full_description = ""
        for i in range(len(kvps)):
            msg_slice = json.loads(kvps[i]["value"])
            self.assertEqual(msg_slice["msg_i"], i)
            full_description += msg_slice["msg"]
        self.assertEqual(description, full_description)

    def test_not_truncate_kvp_file_modified_after_boot(self):
        with open(self.tmp_file_path, "wb+") as f:
            kvp = {"key": "key1", "value": "value1"}
            data = struct.pack(
                "%ds%ds"
                % (
                    HyperVKvpReportingHandler.HV_KVP_EXCHANGE_MAX_KEY_SIZE,
                    HyperVKvpReportingHandler.HV_KVP_EXCHANGE_MAX_VALUE_SIZE,
                ),
                kvp["key"].encode("utf-8"),
                kvp["value"].encode("utf-8"),
            )
            f.write(data)
        cur_time = time.time()
        os.utime(self.tmp_file_path, (cur_time, cur_time))

        # reset this because the unit test framework
        # has already polluted the class variable
        HyperVKvpReportingHandler._already_truncated_pool_file = False

        reporter = HyperVKvpReportingHandler(kvp_file_path=self.tmp_file_path)
        kvps = list(reporter._iterate_kvps(0))
        self.assertEqual(1, len(kvps))

    def test_truncate_stale_kvp_file(self):
        with open(self.tmp_file_path, "wb+") as f:
            kvp = {"key": "key1", "value": "value1"}
            data = struct.pack(
                "%ds%ds"
                % (
                    HyperVKvpReportingHandler.HV_KVP_EXCHANGE_MAX_KEY_SIZE,
                    HyperVKvpReportingHandler.HV_KVP_EXCHANGE_MAX_VALUE_SIZE,
                ),
                kvp["key"].encode("utf-8"),
                kvp["value"].encode("utf-8"),
            )
            f.write(data)

        # set the time ways back to make it look like
        # we had an old kvp file
        os.utime(self.tmp_file_path, (1000000, 1000000))

        # reset this because the unit test framework
        # has already polluted the class variable
        HyperVKvpReportingHandler._already_truncated_pool_file = False

        reporter = HyperVKvpReportingHandler(kvp_file_path=self.tmp_file_path)
        kvps = list(reporter._iterate_kvps(0))
        self.assertEqual(0, len(kvps))

    @mock.patch("cloudinit.distros.uses_systemd")
    @mock.patch("cloudinit.subp.subp")
    def test_get_boot_telemetry(self, m_subp, m_sysd):
        reporter = HyperVKvpReportingHandler(kvp_file_path=self.tmp_file_path)
        datetime_pattern = (
            r"\d{4}-[01]\d-[0-3]\dT[0-2]\d:[0-5]"
            r"\d:[0-5]\d\.\d+([+-][0-2]\d:[0-5]\d|Z)"
        )

        # get_boot_telemetry makes two subp calls to systemctl. We provide
        # a list of values that the subp calls should return
        m_subp.side_effect = [
            ("UserspaceTimestampMonotonic=1844838", ""),
            ("InactiveExitTimestampMonotonic=3068203", ""),
        ]
        m_sysd.return_value = True

        reporter.publish_event(azure.get_boot_telemetry())
        reporter.q.join()
        kvps = list(reporter._iterate_kvps(0))
        self.assertEqual(1, len(kvps))

        evt_msg = kvps[0]["value"]
        if not re.search("kernel_start=" + datetime_pattern, evt_msg):
            raise AssertionError("missing kernel_start timestamp")
        if not re.search("user_start=" + datetime_pattern, evt_msg):
            raise AssertionError("missing user_start timestamp")
        if not re.search("cloudinit_activation=" + datetime_pattern, evt_msg):
            raise AssertionError("missing cloudinit_activation timestamp")

    def test_get_system_info(self):
        reporter = HyperVKvpReportingHandler(kvp_file_path=self.tmp_file_path)
        pattern = r"[^=\s]+"

        reporter.publish_event(azure.get_system_info())
        reporter.q.join()
        kvps = list(reporter._iterate_kvps(0))
        self.assertEqual(1, len(kvps))
        evt_msg = kvps[0]["value"]

        # the most important information is cloudinit version,
        # kernel_version, and the distro variant. It is ok if
        # if the rest is not available
        if not re.search("cloudinit_version=" + pattern, evt_msg):
            raise AssertionError("missing cloudinit_version string")
        if not re.search("kernel_version=" + pattern, evt_msg):
            raise AssertionError("missing kernel_version string")
        if not re.search("variant=" + pattern, evt_msg):
            raise AssertionError("missing distro variant string")

    def test_report_diagnostic_event_without_logger_func(self):
        reporter = HyperVKvpReportingHandler(kvp_file_path=self.tmp_file_path)
        diagnostic_msg = "test_diagnostic"
        reporter.publish_event(azure.report_diagnostic_event(diagnostic_msg))
        reporter.q.join()
        kvps = list(reporter._iterate_kvps(0))
        self.assertEqual(1, len(kvps))
        evt_msg = kvps[0]["value"]

        if diagnostic_msg not in evt_msg:
            raise AssertionError("missing expected diagnostic message")

    def test_report_diagnostic_event_with_logger_func(self):
        reporter = HyperVKvpReportingHandler(kvp_file_path=self.tmp_file_path)
        logger_func = mock.MagicMock()
        diagnostic_msg = "test_diagnostic"
        reporter.publish_event(
            azure.report_diagnostic_event(
                diagnostic_msg, logger_func=logger_func
            )
        )
        reporter.q.join()
        kvps = list(reporter._iterate_kvps(0))
        self.assertEqual(1, len(kvps))
        evt_msg = kvps[0]["value"]

        if diagnostic_msg not in evt_msg:
            raise AssertionError("missing expected diagnostic message")
        logger_func.assert_called_once_with(diagnostic_msg)

    def test_report_compressed_event(self):
        reporter = HyperVKvpReportingHandler(kvp_file_path=self.tmp_file_path)
        try:
            instantiated_handler_registry.register_item("telemetry", reporter)
            event_desc = b"test_compressed"
            azure.report_compressed_event("compressed event", event_desc)

            self.validate_compressed_kvps(reporter, 1, [event_desc])
        finally:
            instantiated_handler_registry.unregister_item(
                "telemetry", force=False
            )

    def validate_compressed_kvps(self, reporter, count, values):
        reporter.q.join()
        kvps = list(reporter._iterate_kvps(0))
        compressed_count = 0
        for i in range(len(kvps)):
            kvp = kvps[i]
            kvp_value = kvp["value"]
            kvp_value_json = json.loads(kvp_value)
            evt_msg = kvp_value_json["msg"]
            evt_type = kvp_value_json["type"]
            if evt_type != azure.COMPRESSED_EVENT_TYPE:
                continue
            evt_msg_json = json.loads(evt_msg)
            evt_encoding = evt_msg_json["encoding"]
            evt_data = zlib.decompress(
                base64.decodebytes(evt_msg_json["data"].encode("ascii"))
            )

            self.assertLess(compressed_count, len(values))
            self.assertEqual(evt_data, values[compressed_count])
            self.assertEqual(evt_encoding, "gz+b64")
            compressed_count += 1
        self.assertEqual(compressed_count, count)

    def test_unique_kvp_key(self):
        reporter = HyperVKvpReportingHandler(kvp_file_path=self.tmp_file_path)
        evt1 = events.ReportingEvent(
            "event_type", "event_message", "event_description"
        )
        reporter.publish_event(evt1)

        evt2 = events.ReportingEvent(
            "event_type",
            "event_message",
            "event_description",
            timestamp=evt1.timestamp + 1,
        )
        reporter.publish_event(evt2)

        reporter.q.join()
        kvps = list(reporter._iterate_kvps(0))
        self.assertEqual(2, len(kvps))
        self.assertNotEqual(
            kvps[0]["key"], kvps[1]["key"], "duplicate keys for KVP entries"
        )

    def test_write_key(self):
        reporter = HyperVKvpReportingHandler(kvp_file_path=self.tmp_file_path)
        reporter.write_key("test-key", "test-value")
        assert list(reporter._iterate_kvps(0)) == [
            {"key": "test-key", "value": "test-value"}
        ]

    def test_write_key_truncates(self):
        reporter = HyperVKvpReportingHandler(kvp_file_path=self.tmp_file_path)

        value = "A" * 2000
        reporter.write_key("test-key", value)

        assert len(list(reporter._iterate_kvps(0))[0]["value"]) == 1023
