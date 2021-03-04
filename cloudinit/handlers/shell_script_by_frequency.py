# part-handler
# vi: syntax=python ts=4

import os
from cloudinit import log
from cloudinit import util
from cloudinit.handlers import Handler
from cloudinit.settings import PER_ALWAYS, PER_INSTANCE, PER_ONCE
LOG = log.getLogger(__name__)

# cloutinit/settings.py defines PER_*** frequency constants. It makes sense to
# use them here, instead hardcodes, and map them to the 'per-***' frequency-
# specific folders in /v/l/c/scripts. It might make sense to expose this at a
# higher level or in a more general module -- eg maybe in cloudinit/settings.py
# itself -- but for now it's here.
pathMap = {
    PER_ALWAYS: 'per-boot',
    PER_INSTANCE: 'per-instance',
    PER_ONCE: 'per-once'
}


# Using pathMap (defined above), return the frequency-specific subfolder for a
# given frequency constant and parent folder.
def get_script_folder_by_frequency(freq, scripts_dir):
    freqPath = pathMap[freq]
    folder = os.path.join(scripts_dir, freqPath)
    return folder


# Given a filename, a payload, a frequency, and a scripts folder, write the
# payload to the correct frequency-specific paths
def write_script_by_frequency(script_path, payload, frequency, scripts_dir):
    filename = os.path.basename(script_path)
    filename = util.clean_filename(filename)
    folder = get_script_folder_by_frequency(frequency, scripts_dir)
    path = os.path.join(folder, filename)
    payload = util.dos2unix(payload)
    util.write_file(path, payload, 0o700)


# per-boot
class ShellScriptPerBootPartHandler(Handler):
    def __init__(self, paths, **_kwargs):
        Handler.__init__(self, PER_ALWAYS)
        self.scripts_dir = paths.get_cpath('scripts')
        if 'script_path' in _kwargs:
            self.scripts_dir = paths.get_cpath(_kwargs['script_path'])

    def list_types(self):
        return(["text/x-shellscript-per-boot"])

    def handle_part(self, data, ctype, script_path, payload, frequency):
        if script_path is not None:
            LOG.debug("script_path=%s", script_path)
            filename = os.path.basename(script_path)
            filename = util.clean_filename(filename)
            write_script_by_frequency(script_path, payload, PER_ALWAYS,
                                      self.scripts_dir)


# per-instance
class ShellScriptPerInstancePartHandler(Handler):
    def __init__(self, paths, **_kwargs):
        Handler.__init__(self, PER_INSTANCE)
        self.scripts_dir = paths.get_cpath('scripts')
        if 'script_path' in _kwargs:
            self.scripts_dir = paths.get_cpath(_kwargs['script_path'])

    def list_types(self):
        return(["text/x-shellscript-per-boot"])

    def handle_part(self, data, ctype, script_path, payload, frequency):
        if script_path is not None:
            LOG.debug("script_path=%s", script_path)
            filename = os.path.basename(script_path)
            filename = util.clean_filename(filename)
            write_script_by_frequency(filename, payload, PER_INSTANCE,
                                      self.scripts_dir)


# per-once
class ShellScriptPerOncePartHandler(Handler):
    def __init__(self, paths, **_kwargs):
        Handler.__init__(self, PER_ONCE)
        self.scripts_dir = paths.get_cpath('scripts')
        if 'script_path' in _kwargs:
            self.scripts_dir = paths.get_cpath(_kwargs['script_path'])

    def list_types(self):
        return(["text/x-shellscript-per-boot"])

    def handle_part(self, data, ctype, script_path, payload, frequency):
        if script_path is not None:
            LOG.debug("script_path=%s", script_path)
            filename = os.path.basename(script_path)
            filename = util.clean_filename(filename)
            write_script_by_frequency(script_path, payload, PER_ONCE,
                                      self.scripts_dir)
