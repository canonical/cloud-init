# vi: ts=4 expandtab

import abc
import logging
import oauthlib.oauth1 as oauth1

import six

from cloudinit.registry import DictRegistry
from cloudinit import url_helper
from cloudinit import util


@six.add_metaclass(abc.ABCMeta)
class ReportingHandler(object):
    """Base class for report handlers.

    Implement :meth:`~publish_event` for controlling what
    the handler does with an event.
    """

    @abc.abstractmethod
    def publish_event(self, event):
        """Publish an event to the ``INFO`` log level."""


class LogHandler(ReportingHandler):
    """Publishes events to the cloud-init log at the ``INFO`` log level."""

    def publish_event(self, event):
        """Publish an event to the ``INFO`` log level."""
        logger = logging.getLogger(
            '.'.join(['cloudinit', 'reporting', event.event_type, event.name]))
        logger.info(event.as_string())


class WebHookHandler(ReportingHandler):
    def __init__(self, endpoint, consumer_key=None, token_key=None,
                 token_secret=None, consumer_secret=None, timeout=None,
                 retries=None):
        super(WebHookHandler, self).__init__()

        if any(consumer_key, token_key, token_secret, consumer_secret):
            self.oauth_helper = url_helper.OauthHelper(
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
        return readurl(
            self.endpoint, data=event.as_dict(),
            timeout=self.timeout,
            retries=self.retries, ssl_details=self.ssl_details)


available_handlers = DictRegistry()
available_handlers.register_item('log', LogHandler)
