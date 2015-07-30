# Copyright 2015 Canonical Ltd.
# This file is part of cloud-init.  See LICENCE file for license information.
#
# vi: ts=4 expandtab
"""
cloud-init reporting framework

The reporting framework is intended to allow all parts of cloud-init to
report events in a structured manner.
"""

import abc
import logging

from cloudinit.registry import DictRegistry


FINISH_EVENT_TYPE = 'finish'
START_EVENT_TYPE = 'start'

DEFAULT_CONFIG = {
    'logging': {'type': 'log'},
    'print': {'type': 'print'},
}


class _nameset(set):
    def __getattr__(self, name):
        if name in self:
            return name
        raise AttributeError

status = _nameset(("SUCCESS", "WARN", "FAIL"))

instantiated_handler_registry = DictRegistry()
available_handlers = DictRegistry()


class ReportingEvent(object):
    """Encapsulation of event formatting."""

    def __init__(self, event_type, name, description):
        self.event_type = event_type
        self.name = name
        self.description = description

    def as_string(self):
        """The event represented as a string."""
        return '{0}: {1}: {2}'.format(
            self.event_type, self.name, self.description)


class FinishReportingEvent(ReportingEvent):

    def __init__(self, name, description, result=None):
        super(FinishReportingEvent, self).__init__(
            FINISH_EVENT_TYPE, name, description)
        if result is None:
            result = status.SUCCESS
        self.result = result
        if result not in status:
            raise ValueError("Invalid result: %s" % result)

    def as_string(self):
        return '{0}: {1}: {2}: {3}'.format(
            self.event_type, self.name, self.result, self.description)


class ReportingHandler(object):

    @abc.abstractmethod
    def publish_event(self, event):
        raise NotImplementedError


class LogHandler(ReportingHandler):
    """Publishes events to the cloud-init log at the ``INFO`` log level."""

    def publish_event(self, event):
        """Publish an event to the ``INFO`` log level."""
        logger = logging.getLogger(
            '.'.join([__name__, event.event_type, event.name]))
        logger.info(event.as_string())


class PrintHandler(ReportingHandler):
    def publish_event(self, event):
        print(event.as_string())


def add_configuration(config):
    for handler_name, handler_config in config.items():
        handler_config = handler_config.copy()
        cls = available_handlers.registered_items[handler_config.pop('type')]
        instance = cls(**handler_config)
        instantiated_handler_registry.register_item(handler_name, instance)


def report_event(event):
    """Report an event to all registered event handlers.

    This should generally be called via one of the other functions in
    the reporting module.

    :param event_type:
        The type of the event; this should be a constant from the
        reporting module.
    """
    for _, handler in instantiated_handler_registry.registered_items.items():
        handler.publish_event(event)


def report_finish_event(event_name, event_description, result):
    """Report a "finish" event.

    See :py:func:`.report_event` for parameter details.
    """
    event = FinishReportingEvent(event_name, event_description, result)
    return report_event(event)


def report_start_event(event_name, event_description):
    """Report a "start" event.

    :param event_name:
        The name of the event; this should be a topic which events would
        share (e.g. it will be the same for start and finish events).

    :param event_description:
        A human-readable description of the event that has occurred.
    """
    event = ReportingEvent(START_EVENT_TYPE, event_name, event_description)
    return report_event(event)


class ReportStack(object):
    def __init__(self, name, description, parent=None, reporting=None,
                 exc_result=None):
        self.parent = parent
        self.reporting = reporting
        self.name = name
        self.description = description

        if exc_result is None:
            exc_result = status.FAIL
        self.exc_result = exc_result

        if reporting is None:
            # if reporting is specified respect it, otherwise use parent's value
            if parent:
                reporting = parent.reporting
            else:
                reporting = True
        if parent:
            self.fullname = '/'.join((name, parent.fullname,))
        else:
            self.fullname = self.name
        self.children = {}

    def __enter__(self):
        self.exception = None
        if self.reporting:
            report_start_event(self.fullname, self.description)
        if self.parent:
            self.parent.children[self.name] = (None, None)
        return self

    def childrens_finish_info(self, result=None, description=None):
        for result in (status.FAIL, status.WARN):
            for name, (value, msg) in self.children.items():
                if value == result:
                    return (result, "[" + name + "]" + msg)
        if result is None:
            result = status.SUCCESS
        if description is None:
            description = self.description
        return (result, description)

    def finish_info(self, exc):
        # return tuple of description, and value
        if exc:
            # by default, exceptions are fatal
            return (self.exc_result, self.description)
        return self.childrens_finish_info()

    def __exit__(self, exc_type, exc_value, traceback):
        self.exception = exc_value
        (result, msg) = self.finish_info(exc_value)
        if self.parent:
            self.parent.children[self.name] = (result, msg)
        if self.reporting:
            report_finish_event(self.fullname, msg, result)

        
available_handlers.register_item('log', LogHandler)
available_handlers.register_item('print', PrintHandler)
add_configuration(DEFAULT_CONFIG)
