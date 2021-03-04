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


# This is purely to allow packaging args up into a single object to please
# pylint and avoid 'too many positional args' complaints. I'd be happy to
# have an alernative.
class ShellScriptByFreqPartHandler(Handler):
    def __init__(self, paths, freq, **_kwargs):
        Handler.__init__(self, freq)
        self.scripts_dir = paths.get_cpath('scripts')
        if 'script_path' in _kwargs:
            self.scripts_dir = paths.get_cpath(_kwargs['script_path'])

    def handle_part(self, data, ctype, script_path, payload, frequency):
        if script_path is not None:
            LOG.debug("script_path=%s", script_path)
            filename = os.path.basename(script_path)
            filename = util.clean_filename(filename)
            write_script_by_frequency(script_path, payload, PER_ALWAYS,
                                      self.scripts_dir)


# per-boot
class ShellScriptPerBootPartHandler(ShellScriptByFreqPartHandler):
    def __init__(self, paths, **_kwargs):
        # pylint: disable=too-many-function-args
        ShellScriptByFreqPartHandler.__init__(self, paths, PER_ALWAYS,
                                              **_kwargs)

    def list_types(self):
        return(["text/x-shellscript-per-boot"])


# per-instance
class ShellScriptPerInstancePartHandler(ShellScriptByFreqPartHandler):
    def __init__(self, paths, **_kwargs):
        # pylint: disable=too-many-function-args
        ShellScriptByFreqPartHandler.__init__(self, paths, PER_INSTANCE,
                                              **_kwargs)

    def list_types(self):
        # pylint: disable=too-many-function-args
        return(["text/x-shellscript-per-boot"])


# per-once
class ShellScriptPerOncePartHandler(ShellScriptByFreqPartHandler):
    def __init__(self, paths, **_kwargs):
        # pylint: disable=too-many-function-args
        ShellScriptByFreqPartHandler.__init__(self, paths, PER_ONCE,
                                              **_kwargs)

    def list_types(self):
        return(["text/x-shellscript-per-boot"])
