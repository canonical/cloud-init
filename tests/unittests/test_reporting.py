# Copyright 2015 Canonical Ltd.
#
# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import reporting
from cloudinit.reporting import events
from cloudinit.reporting import handlers

import mock

from cloudinit.tests.helpers import TestCase


def _fake_registry():
    return mock.Mock(registered_items={'a': mock.MagicMock(),
                                       'b': mock.MagicMock()})


class TestReportStartEvent(TestCase):

    @mock.patch('cloudinit.reporting.events.instantiated_handler_registry',
                new_callable=_fake_registry)
    def test_report_start_event_passes_something_with_as_string_to_handlers(
            self, instantiated_handler_registry):
        event_name, event_description = 'my_test_event', 'my description'
        events.report_start_event(event_name, event_description)
        expected_string_representation = ': '.join(
            ['start', event_name, event_description])
        for _, handler in (
                instantiated_handler_registry.registered_items.items()):
            self.assertEqual(1, handler.publish_event.call_count)
            event = handler.publish_event.call_args[0][0]
            self.assertEqual(expected_string_representation, event.as_string())


class TestReportFinishEvent(TestCase):

    def _report_finish_event(self, result=events.status.SUCCESS):
        event_name, event_description = 'my_test_event', 'my description'
        events.report_finish_event(
            event_name, event_description, result=result)
        return event_name, event_description

    def assertHandlersPassedObjectWithAsString(
            self, handlers, expected_as_string):
        for _, handler in handlers.items():
            self.assertEqual(1, handler.publish_event.call_count)
            event = handler.publish_event.call_args[0][0]
            self.assertEqual(expected_as_string, event.as_string())

    @mock.patch('cloudinit.reporting.events.instantiated_handler_registry',
                new_callable=_fake_registry)
    def test_report_finish_event_passes_something_with_as_string_to_handlers(
            self, instantiated_handler_registry):
        event_name, event_description = self._report_finish_event()
        expected_string_representation = ': '.join(
            ['finish', event_name, events.status.SUCCESS,
             event_description])
        self.assertHandlersPassedObjectWithAsString(
            instantiated_handler_registry.registered_items,
            expected_string_representation)

    @mock.patch('cloudinit.reporting.events.instantiated_handler_registry',
                new_callable=_fake_registry)
    def test_reporting_successful_finish_has_sensible_string_repr(
            self, instantiated_handler_registry):
        event_name, event_description = self._report_finish_event(
            result=events.status.SUCCESS)
        expected_string_representation = ': '.join(
            ['finish', event_name, events.status.SUCCESS,
             event_description])
        self.assertHandlersPassedObjectWithAsString(
            instantiated_handler_registry.registered_items,
            expected_string_representation)

    @mock.patch('cloudinit.reporting.events.instantiated_handler_registry',
                new_callable=_fake_registry)
    def test_reporting_unsuccessful_finish_has_sensible_string_repr(
            self, instantiated_handler_registry):
        event_name, event_description = self._report_finish_event(
            result=events.status.FAIL)
        expected_string_representation = ': '.join(
            ['finish', event_name, events.status.FAIL, event_description])
        self.assertHandlersPassedObjectWithAsString(
            instantiated_handler_registry.registered_items,
            expected_string_representation)

    def test_invalid_result_raises_attribute_error(self):
        self.assertRaises(ValueError, self._report_finish_event, ("BOGUS",))


class TestReportingEvent(TestCase):

    def test_as_string(self):
        event_type, name, description = 'test_type', 'test_name', 'test_desc'
        event = events.ReportingEvent(event_type, name, description)
        expected_string_representation = ': '.join(
            [event_type, name, description])
        self.assertEqual(expected_string_representation, event.as_string())

    def test_as_dict(self):
        event_type, name, desc = 'test_type', 'test_name', 'test_desc'
        event = events.ReportingEvent(event_type, name, desc)
        expected = {'event_type': event_type, 'name': name,
                    'description': desc, 'origin': 'cloudinit'}

        # allow for timestamp to differ, but must be present
        as_dict = event.as_dict()
        self.assertIn('timestamp', as_dict)
        del as_dict['timestamp']

        self.assertEqual(expected, as_dict)


class TestFinishReportingEvent(TestCase):
    def test_as_has_result(self):
        result = events.status.SUCCESS
        name, desc = 'test_name', 'test_desc'
        event = events.FinishReportingEvent(name, desc, result)
        ret = event.as_dict()
        self.assertTrue('result' in ret)
        self.assertEqual(ret['result'], result)


class TestBaseReportingHandler(TestCase):

    def test_base_reporting_handler_is_abstract(self):
        regexp = r".*abstract.*publish_event.*"
        self.assertRaisesRegex(TypeError, regexp, handlers.ReportingHandler)


class TestLogHandler(TestCase):

    @mock.patch.object(reporting.handlers.logging, 'getLogger')
    def test_appropriate_logger_used(self, getLogger):
        event_type, event_name = 'test_type', 'test_name'
        event = events.ReportingEvent(event_type, event_name, 'description')
        reporting.handlers.LogHandler().publish_event(event)
        self.assertEqual(
            [mock.call(
                'cloudinit.reporting.{0}.{1}'.format(event_type, event_name))],
            getLogger.call_args_list)

    @mock.patch.object(reporting.handlers.logging, 'getLogger')
    def test_single_log_message_at_info_published(self, getLogger):
        event = events.ReportingEvent('type', 'name', 'description')
        reporting.handlers.LogHandler().publish_event(event)
        self.assertEqual(1, getLogger.return_value.log.call_count)

    @mock.patch.object(reporting.handlers.logging, 'getLogger')
    def test_log_message_uses_event_as_string(self, getLogger):
        event = events.ReportingEvent('type', 'name', 'description')
        reporting.handlers.LogHandler(level="INFO").publish_event(event)
        self.assertIn(event.as_string(),
                      getLogger.return_value.log.call_args[0][1])


class TestDefaultRegisteredHandler(TestCase):

    def test_log_handler_registered_by_default(self):
        registered_items = (
            reporting.instantiated_handler_registry.registered_items)
        for _, item in registered_items.items():
            if isinstance(item, reporting.handlers.LogHandler):
                break
        else:
            self.fail('No reporting LogHandler registered by default.')


class TestReportingConfiguration(TestCase):

    @mock.patch.object(reporting, 'instantiated_handler_registry')
    def test_empty_configuration_doesnt_add_handlers(
            self, instantiated_handler_registry):
        reporting.update_configuration({})
        self.assertEqual(
            0, instantiated_handler_registry.register_item.call_count)

    @mock.patch.object(
        reporting, 'instantiated_handler_registry', reporting.DictRegistry())
    @mock.patch.object(reporting, 'available_handlers')
    def test_looks_up_handler_by_type_and_adds_it(self, available_handlers):
        handler_type_name = 'test_handler'
        handler_cls = mock.Mock()
        available_handlers.registered_items = {handler_type_name: handler_cls}
        handler_name = 'my_test_handler'
        reporting.update_configuration(
            {handler_name: {'type': handler_type_name}})
        self.assertEqual(
            {handler_name: handler_cls.return_value},
            reporting.instantiated_handler_registry.registered_items)

    @mock.patch.object(
        reporting, 'instantiated_handler_registry', reporting.DictRegistry())
    @mock.patch.object(reporting, 'available_handlers')
    def test_uses_non_type_parts_of_config_dict_as_kwargs(
            self, available_handlers):
        handler_type_name = 'test_handler'
        handler_cls = mock.Mock()
        available_handlers.registered_items = {handler_type_name: handler_cls}
        extra_kwargs = {'foo': 'bar', 'bar': 'baz'}
        handler_config = extra_kwargs.copy()
        handler_config.update({'type': handler_type_name})
        handler_name = 'my_test_handler'
        reporting.update_configuration({handler_name: handler_config})
        self.assertEqual(
            handler_cls.return_value,
            reporting.instantiated_handler_registry.registered_items[
                handler_name])
        self.assertEqual([mock.call(**extra_kwargs)],
                         handler_cls.call_args_list)

    @mock.patch.object(
        reporting, 'instantiated_handler_registry', reporting.DictRegistry())
    @mock.patch.object(reporting, 'available_handlers')
    def test_handler_config_not_modified(self, available_handlers):
        handler_type_name = 'test_handler'
        handler_cls = mock.Mock()
        available_handlers.registered_items = {handler_type_name: handler_cls}
        handler_config = {'type': handler_type_name, 'foo': 'bar'}
        expected_handler_config = handler_config.copy()
        reporting.update_configuration({'my_test_handler': handler_config})
        self.assertEqual(expected_handler_config, handler_config)

    @mock.patch.object(
        reporting, 'instantiated_handler_registry', reporting.DictRegistry())
    @mock.patch.object(reporting, 'available_handlers')
    def test_handlers_removed_if_falseish_specified(self, available_handlers):
        handler_type_name = 'test_handler'
        handler_cls = mock.Mock()
        available_handlers.registered_items = {handler_type_name: handler_cls}
        handler_name = 'my_test_handler'
        reporting.update_configuration(
            {handler_name: {'type': handler_type_name}})
        self.assertEqual(
            1, len(reporting.instantiated_handler_registry.registered_items))
        reporting.update_configuration({handler_name: None})
        self.assertEqual(
            0, len(reporting.instantiated_handler_registry.registered_items))


class TestReportingEventStack(TestCase):
    @mock.patch('cloudinit.reporting.events.report_finish_event')
    @mock.patch('cloudinit.reporting.events.report_start_event')
    def test_start_and_finish_success(self, report_start, report_finish):
        with events.ReportEventStack(name="myname", description="mydesc"):
            pass
        self.assertEqual(
            [mock.call('myname', 'mydesc')], report_start.call_args_list)
        self.assertEqual(
            [mock.call('myname', 'mydesc', events.status.SUCCESS,
                       post_files=[])],
            report_finish.call_args_list)

    @mock.patch('cloudinit.reporting.events.report_finish_event')
    @mock.patch('cloudinit.reporting.events.report_start_event')
    def test_finish_exception_defaults_fail(self, report_start, report_finish):
        name = "myname"
        desc = "mydesc"
        try:
            with events.ReportEventStack(name, description=desc):
                raise ValueError("This didnt work")
        except ValueError:
            pass
        self.assertEqual([mock.call(name, desc)], report_start.call_args_list)
        self.assertEqual(
            [mock.call(name, desc, events.status.FAIL, post_files=[])],
            report_finish.call_args_list)

    @mock.patch('cloudinit.reporting.events.report_finish_event')
    @mock.patch('cloudinit.reporting.events.report_start_event')
    def test_result_on_exception_used(self, report_start, report_finish):
        name = "myname"
        desc = "mydesc"
        try:
            with events.ReportEventStack(
                    name, desc, result_on_exception=events.status.WARN):
                raise ValueError("This didnt work")
        except ValueError:
            pass
        self.assertEqual([mock.call(name, desc)], report_start.call_args_list)
        self.assertEqual(
            [mock.call(name, desc, events.status.WARN, post_files=[])],
            report_finish.call_args_list)

    @mock.patch('cloudinit.reporting.events.report_start_event')
    def test_child_fullname_respects_parent(self, report_start):
        parent_name = "topname"
        c1_name = "c1name"
        c2_name = "c2name"
        c2_expected_fullname = '/'.join([parent_name, c1_name, c2_name])
        c1_expected_fullname = '/'.join([parent_name, c1_name])

        parent = events.ReportEventStack(parent_name, "topdesc")
        c1 = events.ReportEventStack(c1_name, "c1desc", parent=parent)
        c2 = events.ReportEventStack(c2_name, "c2desc", parent=c1)
        with c1:
            report_start.assert_called_with(c1_expected_fullname, "c1desc")
            with c2:
                report_start.assert_called_with(c2_expected_fullname, "c2desc")

    @mock.patch('cloudinit.reporting.events.report_finish_event')
    @mock.patch('cloudinit.reporting.events.report_start_event')
    def test_child_result_bubbles_up(self, report_start, report_finish):
        parent = events.ReportEventStack("topname", "topdesc")
        child = events.ReportEventStack("c_name", "c_desc", parent=parent)
        with parent:
            with child:
                child.result = events.status.WARN

        report_finish.assert_called_with(
            "topname", "topdesc", events.status.WARN, post_files=[])

    @mock.patch('cloudinit.reporting.events.report_finish_event')
    def test_message_used_in_finish(self, report_finish):
        with events.ReportEventStack("myname", "mydesc",
                                     message="mymessage"):
            pass
        self.assertEqual(
            [mock.call("myname", "mymessage", events.status.SUCCESS,
                       post_files=[])],
            report_finish.call_args_list)

    @mock.patch('cloudinit.reporting.events.report_finish_event')
    def test_message_updatable(self, report_finish):
        with events.ReportEventStack("myname", "mydesc") as c:
            c.message = "all good"
        self.assertEqual(
            [mock.call("myname", "all good", events.status.SUCCESS,
                       post_files=[])],
            report_finish.call_args_list)

    @mock.patch('cloudinit.reporting.events.report_start_event')
    @mock.patch('cloudinit.reporting.events.report_finish_event')
    def test_reporting_disabled_does_not_report_events(
            self, report_start, report_finish):
        with events.ReportEventStack("a", "b", reporting_enabled=False):
            pass
        self.assertEqual(report_start.call_count, 0)
        self.assertEqual(report_finish.call_count, 0)

    @mock.patch('cloudinit.reporting.events.report_start_event')
    @mock.patch('cloudinit.reporting.events.report_finish_event')
    def test_reporting_child_default_to_parent(
            self, report_start, report_finish):
        parent = events.ReportEventStack(
            "pname", "pdesc", reporting_enabled=False)
        child = events.ReportEventStack("cname", "cdesc", parent=parent)
        with parent:
            with child:
                pass
            pass
        self.assertEqual(report_start.call_count, 0)
        self.assertEqual(report_finish.call_count, 0)

    def test_reporting_event_has_sane_repr(self):
        myrep = events.ReportEventStack("fooname", "foodesc",
                                        reporting_enabled=True).__repr__()
        self.assertIn("fooname", myrep)
        self.assertIn("foodesc", myrep)
        self.assertIn("True", myrep)

    def test_set_invalid_result_raises_value_error(self):
        f = events.ReportEventStack("myname", "mydesc")
        self.assertRaises(ValueError, setattr, f, "result", "BOGUS")


class TestStatusAccess(TestCase):
    def test_invalid_status_access_raises_value_error(self):
        self.assertRaises(AttributeError, getattr, events.status, "BOGUS")

# vi: ts=4 expandtab
