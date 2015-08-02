import abc
import logging

from cloudinit.registry import DictRegistry


class ReportingHandler(object):

    @abc.abstractmethod
    def publish_event(self, event):
        raise NotImplementedError


class LogHandler(ReportingHandler):
    """Publishes events to the cloud-init log at the ``INFO`` log level."""

    def publish_event(self, event):
        """Publish an event to the ``INFO`` log level."""
        logger = logging.getLogger(
            '.'.join(['cloudinit', 'reporting', event.event_type, event.name]))
        logger.info(event.as_string())


class StderrHandler(ReportingHandler):
    def publish_event(self, event):
        #sys.stderr.write(event.as_string() + "\n")
        print(event.as_string())


available_handlers = DictRegistry()
available_handlers.register_item('log', LogHandler)
available_handlers.register_item('print', StderrHandler)
