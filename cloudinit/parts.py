import os

from cloudinit import util
from cloudinit.settings import (PER_ALWAYS, PER_INSTANCE)
from cloudinit import log as logging

LOG = logging.getLogger(__name__)

CONTENT_END = "__end__"
CONTENT_START = "__begin__"
PART_CONTENT_TYPES = ["text/part-handler"]
PART_HANDLER_FN_TMPL = 'part-handler-%03d'


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


class BootHookPartHandler(PartHandler):
    def __init__(self, boothook_dir, instance_id):
        PartHandler.__init__(self, PER_ALWAYS)
        self.boothook_dir = boothook_dir
        self.instance_id = instance_id

    def list_types(self):
        return ['text/cloud-boothook']
    
    def _handle_part(self, _data, ctype, filename, payload, _frequency):
        if ctype in [CONTENT_START, CONTENT_END]:
            return

        filename = util.clean_filename(filename)
        payload = util.dos2unix(payload)
        prefix = "#cloud-boothook"
        start = 0
        if payload.startswith(prefix):
            start = len(prefix) + 1

        filepath = os.path.join(self.boothook_dir, filename)
        util.write_file(filepath, payload[start:], 0700)
        try:
            env = os.environ.copy()
            env['INSTANCE_ID'] = str(self.instance_id)
            util.subp([filepath], env=env)
        except util.ProcessExecutionError as e:
            LOG.error("Boothooks script %s returned %s", filepath, e.exit_code)
        except Exception as e:
            LOG.error("Boothooks unknown exception %s when running %s", e, filepath)


class UpstartJobPartHandler(PartHandler):
    def __init__(self, upstart_dir):
        PartHandler.__init__(self, PER_INSTANCE)
        self.upstart_dir = upstart_dir

    def list_types(self):
        return ['text/upstart-job']

    def _handle_part(self, _data, ctype, filename, payload, frequency):
        if ctype in [CONTENT_START, CONTENT_END]:
            return

        filename = utils.clean_filename(filename)
        (name, ext) = os.path.splitext(filename)
        ext = ext.lower()
        if ext != ".conf":
            filename = filename + ".conf"

        payload = util.dos2unix(payload)
        util.write_file(os.path.join(self.upstart_dir, filename), payload, 0644)


class ShellScriptPartHandler(PartHandler):

    def __init__(self, script_dir):
        PartHandler.__init__(self, PER_ALWAYS)
        self.script_dir = script_dir

    def list_types(self):
        return ['text/x-shellscript']

    def _handle_part(self, _data, ctype, filename, payload, _frequency):
        if ctype in [CONTENT_START, CONTENT_END]:
            # maybe delete existing things here
            return

        filename = util.clean_filename(filename)
        payload = util.dos2unix(payload)
        util.write_file(os.path.join(self.script_dir, filename), payload, 0700)


class CloudConfigPartHandler(PartHandler):
    def __init__(self, cloud_fn):
        PartHandler.__init__(self, PER_ALWAYS)
        self.cloud_buf = []
        self.cloud_fn = cloud_fn

    def list_types(self):
        return ['text/cloud-config']

    def _handle_part(self, _data, ctype, filename, payload, _frequency):
        if ctype == CONTENT_START:
            self.cloud_buf = []
            return

        if ctype == CONTENT_END:
            payload = "\n".join(self.cloud_buf)
            util.write_file(self.cloud_fn, payload, 0600)
            self.cloud_buf = []
            return

        filename = util.clean_filename(filename)
        entry = "\n".join(["#%s" % (filename), str(payload)])
        self.config_buf.append(entry)


def fixup_module(mod):
    if not hasattr(mod, "handler_version"):
        setattr(mod, "handler_version", 1)
    if not hasattr(mod, 'list_types'):
        def empty_types():
            return []
        setattr(mod, 'list_types', empty_types)
    if not hasattr(mod, frequency):
        setattr(mod, 'frequency', PER_INSTANCE)
    if not hasattr(mod, 'handle_part'):
        def empty_handler(data, ctype, filename, payload):
            pass
        setattr(mod, 'handle_part', empty_handler)
    return mod


def find_module_files(root_dir):
    entries = dict()
    for fname in glob.glob(os.path.join(root_dir, "*.py")):
        if not os.path.isfile(fname):
            continue
        modname = os.path.basename(fname)[0:-3]
        entries[fname] = modname
    return entries


def run_part(mod, data, ctype, filename, payload, frequency):
    # only add the handler if the module should run
    mod_freq = getattr(mod, "frequency")
    if not (mod_freq == PER_ALWAYS or
            (frequency == PER_INSTANCE and mod_freq == PER_INSTANCE)):
        return
    try:
        mod_ver = getattr(mod, 'handler_version')
        if mod_ver == 1:
            mod.handle_part(data, ctype, filename, payload)
        else:
            mod.handle_part(data, ctype, filename, payload, frequency)
    except:
        LOG.exception("Failed calling mod %s (%s, %s, %s) with frequency %s", mod, ctype, filename, mod_ver, frequency)


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
        LOG.exception("Failed at registered python file %s", modfname)


def walker_callback(pdata, ctype, filename, payload):
    # data here is the part_handlers array and then the data to pass through
    if ctype in PART_CONTENT_TYPES:
        walker_handle_handler(pdata, ctype, filename, payload)
        return
    handlers = pdata['handlers']
    if ctype not in handlers:
        if ctype == "text/x-not-multipart":
            # Extract the first line or 24 bytes for displaying in the log
            start = payload.split("\n", 1)[0][:24]
            if start < payload:
                details = "starting '%s...'" % start.encode("string-escape")
            else:
                details = repr(payload)
            LOG.warning("Unhandled non-multipart userdata: %s", details)
        return
    run_part(handlers[ctype], pdata['data'], ctype, filename, payload, pdata['frequency'])
