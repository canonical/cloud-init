# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.reporting import events
from cloudinit.reporting import handlers

import json
import os

from cloudinit import util
from cloudinit.tests.helpers import CiTestCase


class TestKvpEncoding(CiTestCase):
    def test_encode_decode(self):
        kvp = {'key': 'key1', 'value': 'value1'}
        kvp_reporting = handlers.HyperVKvpReportingHandler()
        data = kvp_reporting._encode_kvp_item(kvp['key'], kvp['value'])
        self.assertEqual(len(data), kvp_reporting.HV_KVP_RECORD_SIZE)
        decoded_kvp = kvp_reporting._decode_kvp_item(data)
        self.assertEqual(kvp, decoded_kvp)


class TextKvpReporter(CiTestCase):
    def setUp(self):
        super(TextKvpReporter, self).setUp()
        self.tmp_file_path = self.tmp_path('kvp_pool_file')
        util.ensure_file(self.tmp_file_path)

    def test_event_type_can_be_filtered(self):
        reporter = handlers.HyperVKvpReportingHandler(
            kvp_file_path=self.tmp_file_path,
            event_types=['foo', 'bar'])

        reporter.publish_event(
            events.ReportingEvent('foo', 'name', 'description'))
        reporter.publish_event(
            events.ReportingEvent('some_other', 'name', 'description3'))
        reporter.q.join()

        kvps = list(reporter._iterate_kvps(0))
        self.assertEqual(1, len(kvps))

        reporter.publish_event(
            events.ReportingEvent('bar', 'name', 'description2'))
        reporter.q.join()
        kvps = list(reporter._iterate_kvps(0))
        self.assertEqual(2, len(kvps))

        self.assertIn('foo', kvps[0]['key'])
        self.assertIn('bar', kvps[1]['key'])
        self.assertNotIn('some_other', kvps[0]['key'])
        self.assertNotIn('some_other', kvps[1]['key'])

    def test_events_are_over_written(self):
        reporter = handlers.HyperVKvpReportingHandler(
            kvp_file_path=self.tmp_file_path)

        self.assertEqual(0, len(list(reporter._iterate_kvps(0))))

        reporter.publish_event(
            events.ReportingEvent('foo', 'name1', 'description'))
        reporter.publish_event(
            events.ReportingEvent('foo', 'name2', 'description'))
        reporter.q.join()
        self.assertEqual(2, len(list(reporter._iterate_kvps(0))))

        reporter2 = handlers.HyperVKvpReportingHandler(
            kvp_file_path=self.tmp_file_path)
        reporter2.incarnation_no = reporter.incarnation_no + 1
        reporter2.publish_event(
            events.ReportingEvent('foo', 'name3', 'description'))
        reporter2.q.join()

        self.assertEqual(2, len(list(reporter2._iterate_kvps(0))))

    def test_events_with_higher_incarnation_not_over_written(self):
        reporter = handlers.HyperVKvpReportingHandler(
            kvp_file_path=self.tmp_file_path)

        self.assertEqual(0, len(list(reporter._iterate_kvps(0))))

        reporter.publish_event(
            events.ReportingEvent('foo', 'name1', 'description'))
        reporter.publish_event(
            events.ReportingEvent('foo', 'name2', 'description'))
        reporter.q.join()
        self.assertEqual(2, len(list(reporter._iterate_kvps(0))))

        reporter3 = handlers.HyperVKvpReportingHandler(
            kvp_file_path=self.tmp_file_path)
        reporter3.incarnation_no = reporter.incarnation_no - 1
        reporter3.publish_event(
            events.ReportingEvent('foo', 'name3', 'description'))
        reporter3.q.join()
        self.assertEqual(3, len(list(reporter3._iterate_kvps(0))))

    def test_finish_event_result_is_logged(self):
        reporter = handlers.HyperVKvpReportingHandler(
            kvp_file_path=self.tmp_file_path)
        reporter.publish_event(
            events.FinishReportingEvent('name2', 'description1',
                                        result=events.status.FAIL))
        reporter.q.join()
        self.assertIn('FAIL', list(reporter._iterate_kvps(0))[0]['value'])

    def test_file_operation_issue(self):
        os.remove(self.tmp_file_path)
        reporter = handlers.HyperVKvpReportingHandler(
            kvp_file_path=self.tmp_file_path)
        reporter.publish_event(
            events.FinishReportingEvent('name2', 'description1',
                                        result=events.status.FAIL))
        reporter.q.join()

    def test_event_very_long(self):
        reporter = handlers.HyperVKvpReportingHandler(
            kvp_file_path=self.tmp_file_path)
        description = 'ab' * reporter.HV_KVP_EXCHANGE_MAX_VALUE_SIZE
        long_event = events.FinishReportingEvent(
            'event_name',
            description,
            result=events.status.FAIL)
        reporter.publish_event(long_event)
        reporter.q.join()
        kvps = list(reporter._iterate_kvps(0))
        self.assertEqual(3, len(kvps))

        # restore from the kvp to see the content are all there
        full_description = ''
        for i in range(len(kvps)):
            msg_slice = json.loads(kvps[i]['value'])
            self.assertEqual(msg_slice['msg_i'], i)
            full_description += msg_slice['msg']
        self.assertEqual(description, full_description)
