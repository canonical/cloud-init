# Copyright 2015 Canonical Ltd.
#
# This file is part of cloud-init. See LICENSE file for license information.

import re
from unittest import mock

import pytest

from cloudinit import reporting
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from cloudinit.reporting import events
from tests.unittests.helpers import skipUnlessJsonSchema


def _fake_registry():
    return mock.Mock(
        registered_items={"a": mock.MagicMock(), "b": mock.MagicMock()}
    )


class TestReportStartEvent:
    @mock.patch(
        "cloudinit.reporting.events.instantiated_handler_registry",
        new_callable=_fake_registry,
    )
    def test_report_start_event_passes_something_with_as_string_to_handlers(
        self, instantiated_handler_registry
    ):
        event_name, event_description = "my_test_event", "my description"
        events.report_start_event(event_name, event_description)
        expected_string_representation = ": ".join(
            ["start", event_name, event_description]
        )
        for (
            _,
            handler,
        ) in instantiated_handler_registry.registered_items.items():
            assert handler.publish_event.call_count == 1
            event = handler.publish_event.call_args[0][0]
            assert expected_string_representation == event.as_string()


class TestReportFinishEvent:
    def _report_finish_event(self, result=events.status.SUCCESS):
        event_name, event_description = "my_test_event", "my description"
        events.report_finish_event(
            event_name, event_description, duration=1.0, result=result
        )
        return event_name, event_description

    def assert_handlers_passed_object_with_as_string(
        self, handlers, expected_as_string
    ):
        for _, handler in handlers.items():
            assert handler.publish_event.call_count == 1
            event = handler.publish_event.call_args[0][0]
            assert expected_as_string == event.as_string()

    @mock.patch(
        "cloudinit.reporting.events.instantiated_handler_registry",
        new_callable=_fake_registry,
    )
    def test_report_finish_event_passes_something_with_as_string_to_handlers(
        self, instantiated_handler_registry
    ):
        event_name, event_description = self._report_finish_event()
        expected_string_representation = (
            f"finish: {event_name}: {events.status.SUCCESS}: "
            f"{event_description} (duration: 1.000s)"
        )
        self.assert_handlers_passed_object_with_as_string(
            instantiated_handler_registry.registered_items,
            expected_string_representation,
        )

    @mock.patch(
        "cloudinit.reporting.events.instantiated_handler_registry",
        new_callable=_fake_registry,
    )
    def test_reporting_successful_finish_has_sensible_string_repr(
        self, instantiated_handler_registry
    ):
        event_name, event_description = self._report_finish_event(
            result=events.status.SUCCESS
        )
        expected_string_representation = (
            f"finish: {event_name}: {events.status.SUCCESS}: "
            f"{event_description} (duration: 1.000s)"
        )
        self.assert_handlers_passed_object_with_as_string(
            instantiated_handler_registry.registered_items,
            expected_string_representation,
        )

    @mock.patch(
        "cloudinit.reporting.events.instantiated_handler_registry",
        new_callable=_fake_registry,
    )
    def test_reporting_unsuccessful_finish_has_sensible_string_repr(
        self, instantiated_handler_registry
    ):
        event_name, event_description = self._report_finish_event(
            result=events.status.FAIL
        )
        expected_string_representation = (
            f"finish: {event_name}: {events.status.FAIL}: "
            f"{event_description} (duration: 1.000s)"
        )
        self.assert_handlers_passed_object_with_as_string(
            instantiated_handler_registry.registered_items,
            expected_string_representation,
        )

    def test_invalid_result_raises_attribute_error(self):
        with pytest.raises(ValueError):
            self._report_finish_event("BOGUS")


class TestReportingEvent:
    def test_as_string(self):
        event_type, name, description = "test_type", "test_name", "test_desc"
        event = events.ReportingEvent(event_type, name, description)
        expected_string_representation = ": ".join(
            [event_type, name, description]
        )
        assert expected_string_representation == event.as_string()

    def test_as_dict(self):
        event_type, name, desc = "test_type", "test_name", "test_desc"
        event = events.ReportingEvent(event_type, name, desc)
        expected = {
            "event_type": event_type,
            "name": name,
            "description": desc,
            "origin": "cloudinit",
        }

        # allow for timestamp to differ, but must be present
        as_dict = event.as_dict()
        assert "timestamp" in as_dict
        del as_dict["timestamp"]

        assert expected == as_dict


class TestFinishReportingEvent:
    def test_as_has_result(self):
        result = events.status.SUCCESS
        name, desc = "test_name", "test_desc"
        event = events.FinishReportingEvent(
            name, desc, duration=1.5, result=result
        )
        ret = event.as_dict()
        assert "result" in ret
        assert ret["result"] == result

    def test_has_result_with_optional_post_files(self):
        result = events.status.SUCCESS
        name, desc, files = (
            "test_name",
            "test_desc",
            ["/really/fake/path/install.log"],
        )
        event = events.FinishReportingEvent(
            name, desc, duration=2.0, result=result, post_files=files
        )
        ret = event.as_dict()
        assert "result" in ret
        assert "files" in ret
        assert ret["result"] == result
        posted_install_log = ret["files"][0]
        assert "path" in posted_install_log
        assert "content" in posted_install_log
        assert "encoding" in posted_install_log
        assert posted_install_log["path"] == files[0]
        assert posted_install_log["encoding"] == "base64"

    def test_includes_duration_in_as_dict(self):
        event = events.FinishReportingEvent(
            "test_name", "test_desc", duration=1.234
        )
        ret = event.as_dict()
        assert "duration" in ret
        assert ret["duration"] == 1.234

    def test_includes_duration_in_as_string(self):
        event = events.FinishReportingEvent(
            "test_name", "test_desc", duration=1.234
        )
        string_repr = event.as_string()
        assert "(duration: 1.234s)" in string_repr


class TestLogHandler:
    @mock.patch.object(reporting.handlers.logging, "getLogger")
    def test_appropriate_logger_used(self, getLogger):
        event_type, event_name = "test_type", "test_name"
        event = events.ReportingEvent(event_type, event_name, "description")
        reporting.handlers.LogHandler().publish_event(event)
        assert getLogger.call_args_list == [
            mock.call(
                "cloudinit.reporting.{0}.{1}".format(event_type, event_name)
            )
        ]

    @mock.patch.object(reporting.handlers.logging, "getLogger")
    def test_single_log_message_at_info_published(self, getLogger):
        event = events.ReportingEvent("type", "name", "description")
        reporting.handlers.LogHandler().publish_event(event)
        assert getLogger.return_value.log.call_count == 1

    @mock.patch.object(reporting.handlers.logging, "getLogger")
    def test_log_message_uses_event_as_string(self, getLogger):
        event = events.ReportingEvent("type", "name", "description")
        reporting.handlers.LogHandler(level="INFO").publish_event(event)
        assert event.as_string() in getLogger.return_value.log.call_args[0][1]


class TestDefaultRegisteredHandler:
    def test_log_handler_registered_by_default(self):
        registered_items = (
            reporting.instantiated_handler_registry.registered_items
        )
        for _, item in registered_items.items():
            if isinstance(item, reporting.handlers.LogHandler):
                break
        else:
            pytest.fail("No reporting LogHandler registered by default.")


class TestReportingConfiguration:
    @mock.patch.object(reporting, "instantiated_handler_registry")
    def test_empty_configuration_doesnt_add_handlers(
        self, instantiated_handler_registry
    ):
        reporting.update_configuration({})
        assert instantiated_handler_registry.register_item.call_count == 0

    @mock.patch.object(
        reporting, "instantiated_handler_registry", reporting.DictRegistry()
    )
    @mock.patch.object(reporting, "available_handlers")
    def test_looks_up_handler_by_type_and_adds_it(self, available_handlers):
        handler_type_name = "test_handler"
        handler_cls = mock.Mock()
        available_handlers.registered_items = {handler_type_name: handler_cls}
        handler_name = "my_test_handler"
        reporting.update_configuration(
            {handler_name: {"type": handler_type_name}}
        )
        assert reporting.instantiated_handler_registry.registered_items == {
            handler_name: handler_cls.return_value
        }

    @mock.patch.object(
        reporting, "instantiated_handler_registry", reporting.DictRegistry()
    )
    @mock.patch.object(reporting, "available_handlers")
    def test_uses_non_type_parts_of_config_dict_as_kwargs(
        self, available_handlers
    ):
        handler_type_name = "test_handler"
        handler_cls = mock.Mock()
        available_handlers.registered_items = {handler_type_name: handler_cls}
        extra_kwargs = {"foo": "bar", "bar": "baz"}
        handler_config = extra_kwargs.copy()
        handler_config.update({"type": handler_type_name})
        handler_name = "my_test_handler"
        reporting.update_configuration({handler_name: handler_config})
        assert (
            reporting.instantiated_handler_registry.registered_items[
                handler_name
            ]
            == handler_cls.return_value
        )
        assert handler_cls.call_args_list == [mock.call(**extra_kwargs)]

    @mock.patch.object(
        reporting, "instantiated_handler_registry", reporting.DictRegistry()
    )
    @mock.patch.object(reporting, "available_handlers")
    def test_handler_config_not_modified(self, available_handlers):
        handler_type_name = "test_handler"
        handler_cls = mock.Mock()
        available_handlers.registered_items = {handler_type_name: handler_cls}
        handler_config = {"type": handler_type_name, "foo": "bar"}
        expected_handler_config = handler_config.copy()
        reporting.update_configuration({"my_test_handler": handler_config})
        assert expected_handler_config == handler_config

    @mock.patch.object(
        reporting, "instantiated_handler_registry", reporting.DictRegistry()
    )
    @mock.patch.object(reporting, "available_handlers")
    def test_handlers_removed_if_falseish_specified(self, available_handlers):
        handler_type_name = "test_handler"
        handler_cls = mock.Mock()
        available_handlers.registered_items = {handler_type_name: handler_cls}
        handler_name = "my_test_handler"
        reporting.update_configuration(
            {handler_name: {"type": handler_type_name}}
        )
        assert (
            len(reporting.instantiated_handler_registry.registered_items) == 1
        )
        reporting.update_configuration({handler_name: None})
        assert (
            len(reporting.instantiated_handler_registry.registered_items) == 0
        )


class TestReportingEventStack:
    @mock.patch("cloudinit.reporting.events.report_finish_event")
    @mock.patch("cloudinit.reporting.events.report_start_event")
    def test_start_and_finish_success(self, report_start, report_finish):
        with events.ReportEventStack(name="myname", description="mydesc"):
            pass
        assert report_start.call_args_list == [mock.call("myname", "mydesc")]
        assert report_finish.call_args_list == [
            mock.call(
                "myname",
                "mydesc",
                duration=mock.ANY,
                result=events.status.SUCCESS,
                post_files=[],
            )
        ]

    @mock.patch("cloudinit.reporting.events.report_finish_event")
    @mock.patch("cloudinit.reporting.events.report_start_event")
    def test_finish_exception_defaults_fail(self, report_start, report_finish):
        name = "myname"
        desc = "mydesc"
        try:
            with events.ReportEventStack(name, description=desc):
                raise ValueError("This didnt work")
        except ValueError:
            pass
        assert report_start.call_args_list == [mock.call(name, desc)]
        assert report_finish.call_args_list == [
            mock.call(
                name,
                desc,
                duration=mock.ANY,
                result=events.status.FAIL,
                post_files=[],
            )
        ]

    @mock.patch("cloudinit.reporting.events.report_finish_event")
    @mock.patch("cloudinit.reporting.events.report_start_event")
    def test_result_on_exception_used(self, report_start, report_finish):
        name = "myname"
        desc = "mydesc"
        try:
            with events.ReportEventStack(
                name, desc, result_on_exception=events.status.WARN
            ):
                raise ValueError("This didnt work")
        except ValueError:
            pass
        assert report_start.call_args_list == [mock.call(name, desc)]
        assert report_finish.call_args_list == [
            mock.call(
                name,
                desc,
                duration=mock.ANY,
                result=events.status.WARN,
                post_files=[],
            )
        ]

    @mock.patch("cloudinit.reporting.events.report_start_event")
    def test_child_fullname_respects_parent(self, report_start):
        parent_name = "topname"
        c1_name = "c1name"
        c2_name = "c2name"
        c2_expected_fullname = "/".join([parent_name, c1_name, c2_name])
        c1_expected_fullname = "/".join([parent_name, c1_name])

        parent = events.ReportEventStack(parent_name, "topdesc")
        c1 = events.ReportEventStack(c1_name, "c1desc", parent=parent)
        c2 = events.ReportEventStack(c2_name, "c2desc", parent=c1)
        with c1:
            report_start.assert_called_with(c1_expected_fullname, "c1desc")
            with c2:
                report_start.assert_called_with(c2_expected_fullname, "c2desc")

    @mock.patch("cloudinit.reporting.events.report_finish_event")
    def test_child_result_bubbles_up(self, report_finish):
        parent = events.ReportEventStack("topname", "topdesc")
        child = events.ReportEventStack("c_name", "c_desc", parent=parent)
        with parent:
            with child:
                child.result = events.status.WARN

        report_finish.assert_called_with(
            "topname",
            "topdesc",
            duration=mock.ANY,
            result=events.status.WARN,
            post_files=[],
        )

    @mock.patch("cloudinit.reporting.events.report_finish_event")
    def test_message_used_in_finish(self, report_finish):
        with events.ReportEventStack("myname", "mydesc", message="mymessage"):
            pass
        assert report_finish.call_args_list == [
            mock.call(
                "myname",
                "mymessage",
                duration=mock.ANY,
                result=events.status.SUCCESS,
                post_files=[],
            )
        ]

    @mock.patch("cloudinit.reporting.events.report_finish_event")
    def test_message_updatable(self, report_finish):
        with events.ReportEventStack("myname", "mydesc") as c:
            c.message = "all good"
        assert report_finish.call_args_list == [
            mock.call(
                "myname",
                "all good",
                duration=mock.ANY,
                result=events.status.SUCCESS,
                post_files=[],
            )
        ]

    @mock.patch("cloudinit.reporting.events.report_start_event")
    @mock.patch("cloudinit.reporting.events.report_finish_event")
    def test_reporting_disabled_does_not_report_events(
        self, report_start, report_finish
    ):
        with events.ReportEventStack("a", "b", reporting_enabled=False):
            pass
        assert report_start.call_count == 0
        assert report_finish.call_count == 0

    @mock.patch("cloudinit.reporting.events.report_start_event")
    @mock.patch("cloudinit.reporting.events.report_finish_event")
    def test_reporting_child_default_to_parent(
        self, report_start, report_finish
    ):
        parent = events.ReportEventStack(
            "pname", "pdesc", reporting_enabled=False
        )
        child = events.ReportEventStack("cname", "cdesc", parent=parent)
        with parent:
            with child:
                pass
        assert report_start.call_count == 0
        assert report_finish.call_count == 0

    def test_reporting_event_has_sane_repr(self):
        myrep = events.ReportEventStack(
            "fooname", "foodesc", reporting_enabled=True
        ).__repr__()
        assert "fooname" in myrep
        assert "foodesc" in myrep
        assert "True" in myrep

    def test_set_invalid_result_raises_value_error(self):
        f = events.ReportEventStack("myname", "mydesc")
        with pytest.raises(ValueError):
            f.result = "BOGUS"


class TestStatusAccess:
    def test_invalid_status_access_raises_value_error(self):
        with pytest.raises(AttributeError):
            getattr(events.status, "BOGUS")


@skipUnlessJsonSchema()
class TestReportingSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        [
            # GOOD: Minimum valid parameters
            ({"reporting": {"a": {"type": "print"}}}, None),
            ({"reporting": {"a": {"type": "log"}}}, None),
            (
                {
                    "reporting": {
                        "a": {"type": "webhook", "endpoint": "http://a"}
                    }
                },
                None,
            ),
            ({"reporting": {"a": {"type": "hyperv"}}}, None),
            # GOOD: All valid parameters
            ({"reporting": {"a": {"type": "log", "level": "WARN"}}}, None),
            (
                {
                    "reporting": {
                        "a": {
                            "type": "webhook",
                            "endpoint": "http://a",
                            "timeout": 1,
                            "retries": 1,
                            "consumer_key": "somekey",
                            "token_key": "somekey",
                            "token_secret": "somesecret",
                            "consumer_secret": "somesecret",
                        }
                    }
                },
                None,
            ),
            (
                {
                    "reporting": {
                        "a": {
                            "type": "hyperv",
                            "kvp_file_path": "/some/path",
                            "event_types": ["a", "b"],
                        }
                    }
                },
                None,
            ),
            # GOOD: All combined together
            (
                {
                    "reporting": {
                        "a": {"type": "print"},
                        "b": {"type": "log", "level": "WARN"},
                        "c": {
                            "type": "webhook",
                            "endpoint": "http://a",
                            "timeout": 1,
                            "retries": 1,
                            "consumer_key": "somekey",
                            "token_key": "somekey",
                            "token_secret": "somesecret",
                            "consumer_secret": "somesecret",
                        },
                        "d": {
                            "type": "hyperv",
                            "kvp_file_path": "/some/path",
                            "event_types": ["a", "b"],
                        },
                    }
                },
                None,
            ),
            # BAD: no top level objects
            ({"reporting": "a"}, "'a' is not of type 'object'"),
            ({"reporting": {"a": "b"}}, "'b' is not of type 'object'"),
            # BAD: invalid type
            (
                {"reporting": {"a": {"type": "b"}}},
                re.escape("'b' is not one of ['log']"),
            ),
            # BAD: invalid additional properties
            (
                {"reporting": {"a": {"type": "print", "a": "b"}}},
                "'a' was unexpected",
            ),
            (
                {"reporting": {"a": {"type": "log", "a": "b"}}},
                "'a' was unexpected",
            ),
            (
                {
                    "reporting": {
                        "a": {
                            "type": "webhook",
                            "endpoint": "http://a",
                            "a": "b",
                        }
                    }
                },
                "'a' was unexpected",
            ),
            (
                {"reporting": {"a": {"type": "hyperv", "a": "b"}}},
                "'a' was unexpected",
            ),
            # BAD: missing required properties
            ({"reporting": {"a": {"level": "FATAL"}}}, "'type' is a required"),
            (
                {"reporting": {"a": {"endpoint": "http://a"}}},
                "'type' is a required",
            ),
            (
                {"reporting": {"a": {"kvp_file_path": "/a/b"}}},
                "'endpoint' is a required",
            ),
            (
                {"reporting": {"a": {"type": "webhook"}}},
                "'endpoint' is a required",
            ),
        ],
    )
    def test_schema_validation(self, config, error_msg):
        if error_msg is None:
            validate_cloudconfig_schema(config, get_schema(), strict=True)
        else:
            with pytest.raises(SchemaValidationError, match=error_msg):
                validate_cloudconfig_schema(config, get_schema(), strict=True)
