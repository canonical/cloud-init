# vi: ts=4 expandtab
#
#    Copyright (C) 2012 Canonical Ltd.
#    Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#    Copyright (C) 2012 Yahoo! Inc.
#
#    Author: Scott Moser <scott.moser@canonical.com>
#    Author: Juerg Haefliger <juerg.haefliger@hp.com>
#    Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License version 3, as
#    published by the Free Software Foundation.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.


import os
import glob

import email

from email.mime.base import MIMEBase

from cloudinit import importer
from cloudinit import log as logging
from cloudinit import util

from cloudinit.settings import (PER_ALWAYS, PER_INSTANCE)

LOG = logging.getLogger(__name__)

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

# Used as the content type when a message is not multipart
# and it doesn't contain its own content-type
NOT_MULTIPART_TYPE = "text/x-not-multipart"
OCTET_TYPE = 'application/octet-stream'

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
}

# Sorted longest first
INCLUSION_SRCH = sorted(INCLUSION_TYPES_MAP.keys(), key=(lambda e: 0 - len(e)))


class PartHandler(object):
    def __init__(self, frequency, version=2):
        self.handler_version = version
        self.frequency = frequency

    def __repr__(self):
        return "%s: [%s]" % (self.__class__.__name__, self.list_types())

    def list_types(self):
        raise NotImplementedError()

    def handle_part(self, data, ctype, filename, payload, frequency):
        return self._handle_part(data, ctype, filename, payload, frequency)

    def _handle_part(self, data, ctype, filename, payload, frequency):
        raise NotImplementedError()


def fixup_module(mod, def_freq=PER_INSTANCE):
    if not hasattr(mod, "handler_version"):
        setattr(mod, "handler_version", 1)
    if not hasattr(mod, 'list_types'):
        def empty_types():
            return []
        setattr(mod, 'list_types', empty_types)
    if not hasattr(mod, 'frequency'):
        setattr(mod, 'frequency', def_freq)
    if not hasattr(mod, 'handle_part'):
        def empty_handler(_data, _ctype, _filename, _payload):
            pass
        setattr(mod, 'handle_part', empty_handler)
    return mod


def run_part(mod, data, ctype, filename, payload, frequency):
    mod_freq = mod.frequency
    if not (mod_freq == PER_ALWAYS or
            (frequency == PER_INSTANCE and mod_freq == PER_INSTANCE)):
        return
    mod_ver = mod.handler_version
    try:
        if mod_ver == 1:
            mod.handle_part(data, ctype, filename, payload)
        else:
            mod.handle_part(data, ctype, filename, payload, frequency)
    except:
        LOG.exception(("Failed calling mod %s (%s, %s, %s)"
                     " with frequency %s"), mod, ctype, filename,
                     mod_ver, frequency)


def call_begin(mod, data, frequency):
    run_part(mod, data, CONTENT_START, None, None, frequency)


def call_end(mod, data, frequency):
    run_part(mod, data, CONTENT_END, None, None, frequency)


def walker_handle_handler(pdata, _ctype, _filename, payload):
    curcount = pdata['handlercount']
    modname = PART_HANDLER_FN_TMPL % (curcount)
    frequency = pdata['frequency']
    modfname = os.path.join(pdata['handlerdir'], "%s.py" % (modname))
    # TODO: Check if path exists??
    util.write_file(modfname, payload, 0600)
    handlers = pdata['handlers']
    try:
        mod = fixup_module(importer.import_module(modname))
        handlers.register(mod)
        call_begin(mod, pdata['data'], frequency)
        pdata['handlercount'] = curcount + 1
    except:
        LOG.exception("Failed at registered python file: %s", modfname)


def walker_callback(pdata, ctype, filename, payload):
    if ctype in PART_CONTENT_TYPES:
        walker_handle_handler(pdata, ctype, filename, payload)
        return
    handlers = pdata['handlers']
    if ctype not in handlers:
        if ctype == NOT_MULTIPART_TYPE:
            # Extract the first line or 24 bytes for displaying in the log
            start = payload.split("\n", 1)[0][:24]
            if start < payload:
                details = "starting '%s...'" % start.encode("string-escape")
            else:
                details = repr(payload)
            LOG.warning("Unhandled non-multipart userdata: %s", details)
        return
    run_part(handlers[ctype], pdata['data'], ctype, filename,
             payload, pdata['frequency'])


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

        callback(data, ctype, filename, part.get_payload(decode=True))
        partnum = partnum + 1


# Coverts a raw string into a mime message
def convert_string(raw_data, headers=None):
    if not raw_data:
        raw_data = ''
    if not headers:
        headers = {}
    data = util.decomp_str(raw_data)
    if "mime-version:" in data[0:4096].lower():
        msg = email.message_from_string(data)
        for (key, val) in headers.items():
            if key in msg:
                msg.replace_header(key, val)
            else:
                msg[key] = val
    else:
        mtype = headers.get("Content-Type", NOT_MULTIPART_TYPE)
        maintype, subtype = mtype.split("/", 1)
        msg = MIMEBase(maintype, subtype, *headers)
        msg.set_payload(data)
    return msg


def type_from_starts_with(payload, default=None):
    for text in INCLUSION_SRCH:
        if payload.startswith(text):
            return INCLUSION_TYPES_MAP[text]
    return default