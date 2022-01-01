import os
from cloudinit import log
from cloudinit import util
from cloudinit.handlers import Handler
from cloudinit.settings import PER_ALWAYS, PER_INSTANCE, PER_ONCE
LOG = log.getLogger(__name__)

# cloudinit/settings.py defines PER_*** frequency constants. It makes sense to
# use them here, instead of hardcodes, and map them to the 'per-***' frequency-
# specific folders in /v/l/c/scripts. It might make sense to expose this at a
# higher level or in a more general module -- eg maybe in cloudinit/settings.py
# itself -- but for now it's here.
pathMap = {
    PER_ALWAYS: 'per-boot',
    PER_INSTANCE: 'per-instance',
    PER_ONCE: 'per-once'
}


def get_script_folder_by_frequency(freq, scripts_dir):
    """Return the frequency-specific subfolder for a given frequency constant
       and parent folder."""
    freqPath = pathMap[freq]
    folder = os.path.join(scripts_dir, freqPath)
    return folder


def write_script_by_frequency(script_path, payload, frequency, scripts_dir):
    """Given a filename, a payload, a frequency, and a scripts folder, write
       the payload to the correct frequency-specific path"""
    print('write_script_by_frequency()')
    filename = os.path.basename(script_path)
    filename = util.clean_filename(filename)
    folder = get_script_folder_by_frequency(frequency, scripts_dir)
    path = os.path.join(folder, filename)
    payload = util.dos2unix(payload)
    print(f'Writing payload to {path}')
    util.write_file(path, payload, 0o700)


class ShellScriptByFreqPartHandler(Handler):
    """Common base class for the frequency-specific script handlers."""
    prefixes = ["text/x-shellscript-per-boot",
                "text/x-shellscript-per-instance",
                "text/x-shellscript-per-once"]

    def __init__(self, freq, paths, **_kwargs):
        print("ShellScriptByFreqPartHandler: c'tor()")
        Handler.__init__(self, freq)
        self.scripts_dir = paths.get_cpath('scripts')
        if 'script_path' in _kwargs:
            self.scripts_dir = paths.get_cpath(_kwargs['script_path'])

    def handle_part(self, data, ctype, script_path, payload, frequency):
        print("ShellScriptByFreqPartHandler.handle_part()")
        if script_path is not None:
            LOG.debug("script_path=%s", script_path)
            filename = os.path.basename(script_path)
            filename = util.clean_filename(filename)
            write_script_by_frequency(script_path, payload, self.frequency,
                                      self.scripts_dir)
