import os

from cloudinit import importer
from cloudinit import log as logging
from cloudinit.constants import (PER_INSTANCE, PER_ALWAYS)

LOG = logging.getLogger(__name__)


def handler_register(mod, part_handlers, data, frequency=per_instance):
    if not hasattr(mod, "handler_version"):
        setattr(mod, "handler_version", 1)

    for mtype in mod.list_types():
        part_handlers[mtype] = mod

    handler_call_begin(mod, data, frequency)
    return(mod)


def handler_call_begin(mod, data, frequency):
    handler_handle_part(mod, data, "__begin__", None, None, frequency)


def handler_call_end(mod, data, frequency):
    handler_handle_part(mod, data, "__end__", None, None, frequency)


def handler_handle_part(mod, data, ctype, filename, payload, frequency):
    # only add the handler if the module should run
    modfreq = getattr(mod, "frequency", per_instance)
    if not (modfreq == per_always or
            (frequency == per_instance and modfreq == per_instance)):
        return
    try:
        if mod.handler_version == 1:
            mod.handle_part(data, ctype, filename, payload)
        else:
            mod.handle_part(data, ctype, filename, payload, frequency)
    except:
        util.logexc(log)
        traceback.print_exc(file=sys.stderr)


def partwalker_handle_handler(pdata, _ctype, _filename, payload):
    curcount = pdata['handlercount']
    modname = 'part-handler-%03d' % curcount
    frequency = pdata['frequency']

    modfname = modname + ".py"
    util.write_file("%s/%s" % (pdata['handlerdir'], modfname), payload, 0600)

    try:
        mod = __import__(modname)
        handler_register(mod, pdata['handlers'], pdata['data'], frequency)
        pdata['handlercount'] = curcount + 1
    except:
        util.logexc(log)
        traceback.print_exc(file=sys.stderr)


def partwalker_callback(pdata, ctype, filename, payload):
    # data here is the part_handlers array and then the data to pass through
    if ctype == "text/part-handler":
        if 'handlercount' not in pdata:
            pdata['handlercount'] = 0
        partwalker_handle_handler(pdata, ctype, filename, payload)
        return
    if ctype not in pdata['handlers']:
        if ctype == "text/x-not-multipart":
            # Extract the first line or 24 bytes for displaying in the log
            start = payload.split("\n", 1)[0][:24]
            if start < payload:
                details = "starting '%s...'" % start.encode("string-escape")
            else:
                details = repr(payload)
            log.warning("Unhandled non-multipart userdata %s", details)
        return
    handler_handle_part(pdata['handlers'][ctype], pdata['data'],
        ctype, filename, payload, pdata['frequency'])


class InternalPartHandler:
    freq = per_instance
    mtypes = []
    handler_version = 1
    handler = None

    def __init__(self, handler, mtypes, frequency, version=2):
        self.handler = handler
        self.mtypes = mtypes
        self.frequency = frequency
        self.handler_version = version

    def __repr__(self):
        return("InternalPartHandler: [%s]" % self.mtypes)

    def list_types(self):
        return(self.mtypes)

    def handle_part(self, data, ctype, filename, payload, frequency):
        return(self.handler(data, ctype, filename, payload, frequency))
