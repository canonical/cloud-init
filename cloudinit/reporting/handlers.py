# This file is part of cloud-init. See LICENSE file for license information.

import abc
import fcntl
import json
import os
import queue
import struct
import threading
import time
import uuid
from datetime import datetime
from threading import Event
from typing import Union

from cloudinit import log as logging
from cloudinit import url_helper, util
from cloudinit.registry import DictRegistry

LOG = logging.getLogger(__name__)


class ReportException(Exception):
    pass


class ReportingHandler(metaclass=abc.ABCMeta):
    """Base class for report handlers.

    Implement :meth:`~publish_event` for controlling what
    the handler does with an event.
    """

    @abc.abstractmethod
    def publish_event(self, event):
        """Publish an event."""

    def flush(self):
        """Ensure ReportingHandler has published all events"""


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
            ".".join(["cloudinit", "reporting", event.event_type, event.name])
        )
        logger.log(self.level, event.as_string())


class PrintHandler(ReportingHandler):
    """Print the event as a string."""

    def publish_event(self, event):
        print(event.as_string())


class WebHookHandler(ReportingHandler):
    def __init__(
        self,
        endpoint,
        consumer_key=None,
        token_key=None,
        token_secret=None,
        consumer_secret=None,
        timeout=None,
        retries=None,
    ):
        super(WebHookHandler, self).__init__()

        if any([consumer_key, token_key, token_secret, consumer_secret]):
            oauth_helper = url_helper.OauthUrlHelper(
                consumer_key=consumer_key,
                token_key=token_key,
                token_secret=token_secret,
                consumer_secret=consumer_secret,
            )
            self.readurl = oauth_helper.readurl
        else:
            self.readurl = url_helper.readurl
        self.endpoint = endpoint
        self.timeout = timeout
        self.retries = retries
        self.ssl_details = util.fetch_ssl_details()

        self.flush_requested = Event()
        self.queue = queue.Queue()
        self.event_processor = threading.Thread(target=self.process_requests)
        self.event_processor.daemon = True
        self.event_processor.start()

    def process_requests(self):
        consecutive_failed = 0
        while True:
            if self.flush_requested.is_set() and consecutive_failed > 2:
                # At this point the main thread is waiting for the queue to
                # drain. If we have a queue of events piled up and recent
                # events have failed, lets not waste time trying to post
                # the rest, especially since a long timeout could block
                # cloud-init for quite a long time.
                LOG.warning(
                    "Multiple consecutive failures in WebHookHandler. "
                    "Cancelling all queued events."
                )
                while not self.queue.empty():
                    self.queue.get_nowait()
                    self.queue.task_done()
                consecutive_failed = 0
            args = self.queue.get(block=True)
            try:
                self.readurl(
                    args[0],
                    data=args[1],
                    timeout=args[2],
                    retries=args[3],
                    ssl_details=args[4],
                    log_req_resp=False,
                )
                consecutive_failed = 0
            except Exception as e:
                LOG.warning(
                    "Failed posting event: %s. This was caused by: %s",
                    args[1],
                    e,
                )
                consecutive_failed += 1
            finally:
                self.queue.task_done()

    def publish_event(self, event):
        event_data = event.as_dict()
        LOG.debug(
            "Queuing POST to %s, data: %s",
            self.endpoint,
            event_data,
        )
        self.queue.put(
            (
                self.endpoint,
                json.dumps(event_data),
                self.timeout,
                self.retries,
                self.ssl_details,
            )
        )

    def flush(self):
        self.flush_requested.set()
        LOG.debug("WebHookHandler flushing remaining events")
        self.queue.join()
        self.flush_requested.clear()


class HyperVKvpReportingHandler(ReportingHandler):
    """
    Reports events to a Hyper-V host using Key-Value-Pair exchange protocol
    and can be used to obtain high level diagnostic information from the host.

    To use this facility, the KVP user-space daemon (hv_kvp_daemon) has to be
    running. It reads the kvp_file when the host requests the guest to
    enumerate the KVP's.

    This reporter collates all events for a module (origin|name) in a single
    json string in the dictionary.

    For more information, see
    https://technet.microsoft.com/en-us/library/dn798287.aspx#Linux%20guests
    """

    HV_KVP_EXCHANGE_MAX_VALUE_SIZE = 2048
    # The maximum value size expected in Azure
    HV_KVP_AZURE_MAX_VALUE_SIZE = 1024
    HV_KVP_EXCHANGE_MAX_KEY_SIZE = 512
    HV_KVP_RECORD_SIZE = (
        HV_KVP_EXCHANGE_MAX_KEY_SIZE + HV_KVP_EXCHANGE_MAX_VALUE_SIZE
    )
    EVENT_PREFIX = "CLOUD_INIT"
    MSG_KEY = "msg"
    RESULT_KEY = "result"
    DESC_IDX_KEY = "msg_i"
    JSON_SEPARATORS = (",", ":")
    KVP_POOL_FILE_GUEST = "/var/lib/hyperv/.kvp_pool_1"
    _already_truncated_pool_file = False

    def __init__(self, kvp_file_path=KVP_POOL_FILE_GUEST, event_types=None):
        super(HyperVKvpReportingHandler, self).__init__()
        self._kvp_file_path = kvp_file_path
        HyperVKvpReportingHandler._truncate_guest_pool_file(
            self._kvp_file_path
        )

        self._event_types = event_types
        self.q = queue.Queue()
        self.incarnation_no = self._get_incarnation_no()
        self.event_key_prefix = "{0}|{1}".format(
            self.EVENT_PREFIX, self.incarnation_no
        )
        self.publish_thread = threading.Thread(
            target=self._publish_event_routine
        )
        self.publish_thread.daemon = True
        self.publish_thread.start()

    @classmethod
    def _truncate_guest_pool_file(cls, kvp_file):
        """
        Truncate the pool file if it has not been truncated since boot.
        This should be done exactly once for the file indicated by
        KVP_POOL_FILE_GUEST constant above. This method takes a filename
        so that we can use an arbitrary file during unit testing.
        Since KVP is a best-effort telemetry channel we only attempt to
        truncate the file once and only if the file has not been modified
        since boot. Additional truncation can lead to loss of existing
        KVPs.
        """
        if cls._already_truncated_pool_file:
            return
        boot_time = time.time() - float(util.uptime())
        try:
            if os.path.getmtime(kvp_file) < boot_time:
                with open(kvp_file, "w"):
                    pass
        except (OSError, IOError) as e:
            LOG.warning("failed to truncate kvp pool file, %s", e)
        finally:
            cls._already_truncated_pool_file = True

    def _get_incarnation_no(self):
        """
        use the time passed as the incarnation number.
        the incarnation number is the number which are used to
        distinguish the old data stored in kvp and the new data.
        """
        uptime_str = util.uptime()
        try:
            return int(time.time() - float(uptime_str))
        except ValueError:
            LOG.warning("uptime '%s' not in correct format.", uptime_str)
            return 0

    def _iterate_kvps(self, offset):
        """iterate the kvp file from the current offset."""
        with open(self._kvp_file_path, "rb") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.seek(offset)
            record_data = f.read(self.HV_KVP_RECORD_SIZE)
            while len(record_data) == self.HV_KVP_RECORD_SIZE:
                kvp_item = self._decode_kvp_item(record_data)
                yield kvp_item
                record_data = f.read(self.HV_KVP_RECORD_SIZE)
            fcntl.flock(f, fcntl.LOCK_UN)

    def _event_key(self, event):
        """
        the event key format is:
        CLOUD_INIT|<incarnation number>|<event_type>|<event_name>|<uuid>
        [|subevent_index]
        """
        return "{0}|{1}|{2}|{3}".format(
            self.event_key_prefix, event.event_type, event.name, uuid.uuid4()
        )

    def _encode_kvp_item(self, key, value):
        data = struct.pack(
            "%ds%ds"
            % (
                self.HV_KVP_EXCHANGE_MAX_KEY_SIZE,
                self.HV_KVP_EXCHANGE_MAX_VALUE_SIZE,
            ),
            key.encode("utf-8"),
            value.encode("utf-8"),
        )
        return data

    def _decode_kvp_item(self, record_data):
        record_data_len = len(record_data)
        if record_data_len != self.HV_KVP_RECORD_SIZE:
            raise ReportException(
                "record_data len not correct {0} {1}.".format(
                    record_data_len, self.HV_KVP_RECORD_SIZE
                )
            )
        k = (
            record_data[0 : self.HV_KVP_EXCHANGE_MAX_KEY_SIZE]
            .decode("utf-8")
            .strip("\x00")
        )
        v = (
            record_data[
                self.HV_KVP_EXCHANGE_MAX_KEY_SIZE : self.HV_KVP_RECORD_SIZE
            ]
            .decode("utf-8")
            .strip("\x00")
        )

        return {"key": k, "value": v}

    def _append_kvp_item(self, record_data):
        with open(self._kvp_file_path, "ab") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            for data in record_data:
                f.write(data)
            f.flush()
            fcntl.flock(f, fcntl.LOCK_UN)

    def _break_down(self, key, meta_data, description):
        del meta_data[self.MSG_KEY]
        des_in_json = json.dumps(description)
        des_in_json = des_in_json[1 : (len(des_in_json) - 1)]
        i = 0
        result_array = []
        message_place_holder = '"' + self.MSG_KEY + '":""'
        while True:
            meta_data[self.DESC_IDX_KEY] = i
            meta_data[self.MSG_KEY] = ""
            data_without_desc = json.dumps(
                meta_data, separators=self.JSON_SEPARATORS
            )
            room_for_desc = (
                self.HV_KVP_AZURE_MAX_VALUE_SIZE - len(data_without_desc) - 8
            )
            value = data_without_desc.replace(
                message_place_holder,
                '"{key}":"{desc}"'.format(
                    key=self.MSG_KEY, desc=des_in_json[:room_for_desc]
                ),
            )
            subkey = "{}|{}".format(key, i)
            result_array.append(self._encode_kvp_item(subkey, value))
            i += 1
            des_in_json = des_in_json[room_for_desc:]
            if len(des_in_json) == 0:
                break
        return result_array

    def _encode_event(self, event):
        """
        encode the event into kvp data bytes.
        if the event content reaches the maximum length of kvp value.
        then it would be cut to multiple slices.
        """
        key = self._event_key(event)
        meta_data = {
            "name": event.name,
            "type": event.event_type,
            "ts": (
                datetime.utcfromtimestamp(event.timestamp).isoformat() + "Z"
            ),
        }
        if hasattr(event, self.RESULT_KEY):
            meta_data[self.RESULT_KEY] = event.result
        meta_data[self.MSG_KEY] = event.description
        value = json.dumps(meta_data, separators=self.JSON_SEPARATORS)
        # if it reaches the maximum length of kvp value,
        # break it down to slices.
        # this should be very corner case.
        if len(value) > self.HV_KVP_AZURE_MAX_VALUE_SIZE:
            return self._break_down(key, meta_data, event.description)
        else:
            data = self._encode_kvp_item(key, value)
            return [data]

    def _publish_event_routine(self):
        while True:
            items_from_queue = 0
            try:
                event = self.q.get(block=True)
                items_from_queue += 1
                encoded_data = []
                while event is not None:
                    encoded_data += self._encode_event(event)
                    try:
                        # get all the rest of the events in the queue
                        event = self.q.get(block=False)
                        items_from_queue += 1
                    except queue.Empty:
                        event = None
                try:
                    self._append_kvp_item(encoded_data)
                except (OSError, IOError) as e:
                    LOG.warning("failed posting events to kvp, %s", e)
                finally:
                    for _ in range(items_from_queue):
                        self.q.task_done()
            # when main process exits, q.get() will through EOFError
            # indicating we should exit this thread.
            except EOFError:
                return

    # since the saving to the kvp pool can be a time costing task
    # if the kvp pool already contains a chunk of data,
    # so defer it to another thread.
    def publish_event(self, event):
        if not self._event_types or event.event_type in self._event_types:
            self.q.put(event)

    def flush(self):
        LOG.debug("HyperVReportingHandler flushing remaining events")
        self.q.join()


# Type[ReportingHandler] doesn't work here because each class has different
# call args. Protocols in python 3.8 can probably make this simpler.
HandlerType = Union[
    ReportingHandler,
    LogHandler,
    PrintHandler,
    WebHookHandler,
    HyperVKvpReportingHandler,
]

available_handlers = DictRegistry()
available_handlers.register_item("log", LogHandler)
available_handlers.register_item("print", PrintHandler)
available_handlers.register_item("webhook", WebHookHandler)
available_handlers.register_item("hyperv", HyperVKvpReportingHandler)
