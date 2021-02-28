# part-handler
# vi: syntax=python ts=4

import os
from cloudinit import log
from cloudinit import util
from cloudinit import handlers
from cloudinit.settings import PER_ALWAYS, PER_INSTANCE, PER_ONCE
from cloudinit.cmd.devel import read_cfg_paths
LOG = log.getLogger(__name__)

pathMap = {
    PER_ALWAYS: 'per-boot',
    PER_INSTANCE: 'per-instance',
    PER_ONCE: 'per-once'
}

def get_script_folder_by_frequency (freq):
    freqPath = pathMap[freq]
    ci_paths = read_cfg_paths()
    scripts_dir = ci_paths.get_cpath('scripts')   # defaults to /var/lib/cloud/ + scripts
    folder = os.path.join(scripts_dir, freqPath)
    return folder

def write_script_by_frequency (script_path, payload, frequency):
    filename = os.path.basename(script_path)
    filename = util.clean_filename(filename)
    folder = get_script_folder_by_frequency(frequency)
    path = os.path.join(folder, filename)
    payload = util.dos2unix(payload)
    util.write_file(path, payload, 0o700)

### per-boot
class ShellScriptPerBootPartHandler(handlers.Handler):
    def __init__(self, paths, **_kwargs):
        handlers.Handler.__init__(self, PER_ALWAYS)

    def list_types(self):
        return(["text/x-shellscript-per-boot"])

    def handle_part(self, data, ctype, script_path, payload):
        if script_path is not None:
            LOG.debug("script_path=%s", script_path)
            write_script_by_frequency(script_path, payload, PER_ALWAYS)

### per-instance
class ShellScriptPerInstancePartHandler(handlers.Handler):
    def __init__(self, paths, **_kwargs):
        handlers.Handler.__init__(self, PER_INSTANCE)

    def list_types(self):
        return(["text/x-shellscript-per-boot"])

    def handle_part(self, data, ctype, script_path, payload):
        if script_path is not None:
            LOG.debug("script_path=%s", script_path)
            write_script_by_frequency(script_path, payload, PER_INSTANCE)

### per-once
class ShellScriptPerOPncePartHandler(handlers.Handler):
    def __init__(self, paths, **_kwargs):
        handlers.Handler.__init__(self, PER_ONCE)

    def list_types(self):
        return(["text/x-shellscript-per-boot"])

    def handle_part(self, data, ctype, script_path, payload):
        if script_path is not None:
            LOG.debug("script_path=%s", script_path)
            write_script_by_frequency(script_path, payload, PER_ONCE)