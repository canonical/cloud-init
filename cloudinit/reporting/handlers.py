# This file is part of cloud-init. See LICENSE file for license information.

import abc
import json
import six

from cloudinit import log as logging
from cloudinit.registry import DictRegistry
from cloudinit import (url_helper, util)


LOG = logging.getLogger(__name__)


@six.add_metaclass(abc.ABCMeta)
class ReportingHandler(object):
    """Base class for report handlers.

    Implement :meth:`~publish_event` for controlling what
    the handler does with an event.
    """

    @abc.abstractmethod
    def publish_event(self, event):
        """Publish an event."""


class LogHandler(ReportingHandler):
    """Publishes events to the cloud-init log at the ``DEBUG`` log level."""

    def __init__(self, level="DEBUG"):
        super(LogHandler, self).__init__()
        if isinstance(level, int):
            pass
        else:
            input_level = level
            try:
                level = getattr(logging, level.upper())
            except Exception:
                LOG.warning("invalid level '%s', using WARN", input_level)
                level = logging.WARN
        self.level = level

    def publish_event(self, event):
        logger = logging.getLogger(
            '.'.join(['cloudinit', 'reporting', event.event_type, event.name]))
        logger.log(self.level, event.as_string())


class PrintHandler(ReportingHandler):
    """Print the event as a string."""

    def publish_event(self, event):
        print(event.as_string())


class WebHookHandler(ReportingHandler):
    def __init__(self, endpoint, consumer_key=None, token_key=None,
                 token_secret=None, consumer_secret=None, timeout=None,
                 retries=None):
        super(WebHookHandler, self).__init__()

        if any([consumer_key, token_key, token_secret, consumer_secret]):
            self.oauth_helper = url_helper.OauthUrlHelper(
                consumer_key=consumer_key, token_key=token_key,
                token_secret=token_secret, consumer_secret=consumer_secret)
        else:
            self.oauth_helper = None
        self.endpoint = endpoint
        self.timeout = timeout
        self.retries = retries
        self.ssl_details = util.fetch_ssl_details()

    def publish_event(self, event):
        if self.oauth_helper:
            readurl = self.oauth_helper.readurl
        else:
            readurl = url_helper.readurl
        try:
            return readurl(
                self.endpoint, data=json.dumps(event.as_dict()),
                timeout=self.timeout,
                retries=self.retries, ssl_details=self.ssl_details)
        except Exception:
            LOG.warning("failed posting event: %s", event.as_string())


available_handlers = DictRegistry()
available_handlers.register_item('log', LogHandler)
available_handlers.register_item('print', PrintHandler)
available_handlers.register_item('webhook', WebHookHandler)

# vi: ts=4 expandtab
