# part-handler
# vi: syntax=python ts=4

import os
from cloudinit import log
from cloudinit import util
from cloudinit.handlers import Handler
from cloudinit.settings import PER_ALWAYS, PER_INSTANCE, PER_ONCE
LOG = log.getLogger(__name__)

pathMap = {
    PER_ALWAYS: 'per-boot',
    PER_INSTANCE: 'per-instance',
    PER_ONCE: 'per-once'
}

def get_script_folder_by_frequency (scripts_dir, freq):
    freqPath = pathMap[freq]
    folder = os.path.join(scripts_dir, freqPath)
    return folder

def write_script_by_frequency (script_path, payload, frequency, scripts_dir):
    filename = os.path.basename(script_path)
    filename = util.clean_filename(filename)
    folder = get_script_folder_by_frequency(scripts_dir, frequency)
    path = os.path.join(folder, filename)
    payload = util.dos2unix(payload)
    util.write_file(path, payload, 0o700)

### per-boot
class ShellScriptPerBootPartHandler(Handler):
    def __init__(self, paths, **_kwargs):
        Handler.__init__(self, PER_ALWAYS)
        self.scripts_dir = paths.get_ipath_cur('scripts')
        if 'script_path' in _kwargs:
            self.scripts_dir = paths.get_ipath_cur(_kwargs['script_path'])

    def list_types(self):
        return(["text/x-shellscript-per-boot"])

    def handle_part(self, data, ctype, script_path, payload):
        if script_path is not None:
            LOG.debug("script_path=%s", script_path)
            write_script_by_frequency(script_path, payload, PER_ALWAYS, self.scripts_dir)

### per-instance
class ShellScriptPerInstancePartHandler(Handler):
    def __init__(self, paths, **_kwargs):
        Handler.__init__(self, PER_INSTANCE)
        self.scripts_dir = paths.get_ipath_cur('scripts')
        if 'script_path' in _kwargs:
            self.scripts_dir = paths.get_ipath_cur(_kwargs['script_path'])

    def list_types(self):
        return(["text/x-shellscript-per-boot"])

    def handle_part(self, data, ctype, script_path, payload):
        if script_path is not None:
            LOG.debug("script_path=%s", script_path)
            write_script_by_frequency(script_path, payload, PER_INSTANCE, self.scripts_dir)

### per-once
class ShellScriptPerOncePartHandler(Handler):
    def __init__(self, paths, **_kwargs):
        Handler.__init__(self, PER_ONCE)
        self.scripts_dir = paths.get_ipath_cur('scripts')
        if 'script_path' in _kwargs:
            self.scripts_dir = paths.get_ipath_cur(_kwargs['script_path'])

    def list_types(self):
        return(["text/x-shellscript-per-boot"])

    def handle_part(self, data, ctype, script_path, payload):
        if script_path is not None:
            LOG.debug("script_path=%s", script_path)
            write_script_by_frequency(script_path, payload, PER_ONCE, self.scripts_dir)