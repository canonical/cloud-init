# Copyright (C) 2012 Canonical Ltd.
# Copyright (C) 2012, 2013 Hewlett-Packard Development Company, L.P.
# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import abc
import os
import six

from cloudinit.settings import (PER_ALWAYS, PER_INSTANCE, FREQUENCIES)

from cloudinit import importer
from cloudinit import log as logging
from cloudinit import type_utils
from cloudinit import util

LOG = logging.getLogger(__name__)

# Used as the content type when a message is not multipart
# and it doesn't contain its own content-type
NOT_MULTIPART_TYPE = "text/x-not-multipart"

# When none is assigned this gets used
OCTET_TYPE = 'application/octet-stream'

# Special content types that signal the start and end of processing
CONTENT_END = "__end__"
CONTENT_START = "__begin__"
CONTENT_SIGNALS = [CONTENT_START, CONTENT_END]

# Used when a part-handler type is encountered
# to allow for registration of new types.
PART_CONTENT_TYPES = ["text/part-handler"]
PART_HANDLER_FN_TMPL = 'part-handler-%03d'

# For parts without filenames
PART_FN_TPL = 'part-%03d'

# Different file beginnings to there content type
INCLUSION_TYPES_MAP = {
    '#include': 'text/x-include-url',
    '#include-once': 'text/x-include-once-url',
    '#!': 'text/x-shellscript',
    '#cloud-config': 'text/cloud-config',
    '#upstart-job': 'text/upstart-job',
    '#part-handler': 'text/part-handler',
    '#cloud-boothook': 'text/cloud-boothook',
    '#cloud-config-archive': 'text/cloud-config-archive',
    '#cloud-config-jsonp': 'text/cloud-config-jsonp',
}

# Sorted longest first
INCLUSION_SRCH = sorted(list(INCLUSION_TYPES_MAP.keys()),
                        key=(lambda e: 0 - len(e)))


@six.add_metaclass(abc.ABCMeta)
class Handler(object):

    def __init__(self, frequency, version=2):
        self.handler_version = version
        self.frequency = frequency

    def __repr__(self):
        return "%s: [%s]" % (type_utils.obj_name(self), self.list_types())

    @abc.abstractmethod
    def list_types(self):
        raise NotImplementedError()

    @abc.abstractmethod
    def handle_part(self, *args, **kwargs):
        raise NotImplementedError()


def run_part(mod, data, filename, payload, frequency, headers):
    mod_freq = mod.frequency
    if not (mod_freq == PER_ALWAYS or
            (frequency == PER_INSTANCE and mod_freq == PER_INSTANCE)):
        return
    # Sanity checks on version (should be an int convertable)
    try:
        mod_ver = mod.handler_version
        mod_ver = int(mod_ver)
    except (TypeError, ValueError, AttributeError):
        mod_ver = 1
    content_type = headers['Content-Type']
    try:
        LOG.debug("Calling handler %s (%s, %s, %s) with frequency %s",
                  mod, content_type, filename, mod_ver, frequency)
        if mod_ver == 3:
            # Treat as v. 3 which does get a frequency + headers
            mod.handle_part(data, content_type, filename,
                            payload, frequency, headers)
        elif mod_ver == 2:
            # Treat as v. 2 which does get a frequency
            mod.handle_part(data, content_type, filename,
                            payload, frequency)
        elif mod_ver == 1:
            # Treat as v. 1 which gets no frequency
            mod.handle_part(data, content_type, filename, payload)
        else:
            raise ValueError("Unknown module version %s" % (mod_ver))
    except Exception:
        util.logexc(LOG, "Failed calling handler %s (%s, %s, %s) with "
                    "frequency %s", mod, content_type, filename, mod_ver,
                    frequency)


def call_begin(mod, data, frequency):
    # Create a fake header set
    headers = {
        'Content-Type': CONTENT_START,
    }
    run_part(mod, data, None, None, frequency, headers)


def call_end(mod, data, frequency):
    # Create a fake header set
    headers = {
        'Content-Type': CONTENT_END,
    }
    run_part(mod, data, None, None, frequency, headers)


def walker_handle_handler(pdata, _ctype, _filename, payload):
    curcount = pdata['handlercount']
    modname = PART_HANDLER_FN_TMPL % (curcount)
    frequency = pdata['frequency']
    modfname = os.path.join(pdata['handlerdir'], "%s" % (modname))
    if not modfname.endswith(".py"):
        modfname = "%s.py" % (modfname)
    # TODO(harlowja): Check if path exists??
    util.write_file(modfname, payload, 0o600)
    handlers = pdata['handlers']
    try:
        mod = fixup_handler(importer.import_module(modname))
        call_begin(mod, pdata['data'], frequency)
        # Only register and increment after the above have worked, so we don't
        # register if it fails starting.
        handlers.register(mod, initialized=True)
        pdata['handlercount'] = curcount + 1
    except Exception:
        util.logexc(LOG, "Failed at registering python file: %s (part "
                    "handler %s)", modfname, curcount)


def _extract_first_or_bytes(blob, size):
    # Extract the first line or upto X symbols for text objects
    # Extract first X bytes for binary objects
    try:
        if isinstance(blob, six.string_types):
            start = blob.split("\n", 1)[0]
        else:
            # We want to avoid decoding the whole blob (it might be huge)
            # By taking 4*size bytes we guarantee to decode size utf8 chars
            start = blob[:4 * size].decode(errors='ignore').split("\n", 1)[0]
        if len(start) >= size:
            start = start[:size]
    except UnicodeDecodeError:
        # Bytes array doesn't contain text so return chunk of raw bytes
        start = blob[0:size]
    return start


def _escape_string(text):
    try:
        return text.encode("string_escape")
    except (LookupError, TypeError):
        try:
            # Unicode (and Python 3's str) doesn't support string_escape...
            return text.encode('unicode_escape')
        except TypeError:
            # Give up...
            pass
    except AttributeError:
        # We're in Python3 and received blob as text
        # No escaping is needed because bytes are printed
        # as 'b\xAA\xBB' automatically in Python3
        pass
    return text


def walker_callback(data, filename, payload, headers):
    content_type = headers['Content-Type']
    if content_type in data.get('excluded'):
        LOG.debug('content_type "%s" is excluded', content_type)
        return

    if content_type in PART_CONTENT_TYPES:
        walker_handle_handler(data, content_type, filename, payload)
        return
    handlers = data['handlers']
    if content_type in handlers:
        run_part(handlers[content_type], data['data'], filename,
                 payload, data['frequency'], headers)
    elif payload:
        # Extract the first line or 24 bytes for displaying in the log
        start = _extract_first_or_bytes(payload, 24)
        details = "'%s...'" % (_escape_string(start))
        if content_type == NOT_MULTIPART_TYPE:
            LOG.warning("Unhandled non-multipart (%s) userdata: %s",
                        content_type, details)
        else:
            LOG.warning("Unhandled unknown content-type (%s) userdata: %s",
                        content_type, details)
    else:
        LOG.debug("Empty payload of type %s", content_type)


# Callback is a function that will be called with
# (data, content_type, filename, payload)
def walk(msg, callback, data):
    partnum = 0
    for part in msg.walk():
        # multipart/* are just containers
        if part.get_content_maintype() == 'multipart':
            continue

        ctype = part.get_content_type()
        if ctype is None:
            ctype = OCTET_TYPE

        filename = part.get_filename()
        if not filename:
            filename = PART_FN_TPL % (partnum)

        headers = dict(part)
        LOG.debug(headers)
        headers['Content-Type'] = ctype
        payload = util.fully_decoded_payload(part)
        callback(data, filename, payload, headers)
        partnum = partnum + 1


def fixup_handler(mod, def_freq=PER_INSTANCE):
    if not hasattr(mod, "handler_version"):
        setattr(mod, "handler_version", 1)
    if not hasattr(mod, 'frequency'):
        setattr(mod, 'frequency', def_freq)
    else:
        freq = mod.frequency
        if freq and freq not in FREQUENCIES:
            LOG.warning("Handler %s has an unknown frequency %s", mod, freq)
    return mod


def type_from_starts_with(payload, default=None):
    try:
        payload_lc = util.decode_binary(payload).lower()
    except UnicodeDecodeError:
        return default
    payload_lc = payload_lc.lstrip()
    for text in INCLUSION_SRCH:
        if payload_lc.startswith(text):
            return INCLUSION_TYPES_MAP[text]
    return default

# vi: ts=4 expandtab
