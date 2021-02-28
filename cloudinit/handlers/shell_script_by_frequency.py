# part-handler
# vi: syntax=python ts=4

import os
from cloudinit import log
from cloudinit import util

LOG = log.getLogger(__name__)


def get_script_path_by_frequency ()

class ShellScriptPartHandler(handlers.Handler):
    prefixes = ['#!']

    def __init__(self, paths, **_kwargs):
        handlers.Handler.__init__(self, PER_ALWAYS)
        self.script_dir = paths.get_ipath_cur('scripts')
        if 'script_path' in _kwargs:
            self.script_dir = paths.get_ipath_cur(_kwargs['script_path'])

    def handle_part(self, data, ctype, filename, payload, frequency):
        if ctype in handlers.CONTENT_SIGNALS:
            # TODO(harlowja): maybe delete existing things here
            return

        filename = util.clean_filename(filename)
        payload = util.dos2unix(payload)
        path = os.path.join(self.script_dir, filename)
        util.write_file(path, payload, 0o700)


### per-boot
class ShellScriptPerBootPartHandler(handlers.Handler):

    def __init__(self, paths, **_kwargs):
        handlers.Handler.__init__(self, PER_BOOstT)
        self.script_dir = paths.get_ipath_cur('scripts')
        if 'script_path' in _kwargs:
            self.script_dir = paths.get_ipath_cur(_kwargs['script_path'])

    def list_types():
        return(["text/x-shellscript-per-boot"])

    def handle_part(self, data, ctype, script_path, payload):
        if script_path is not None:
            LOG.debug("script_path=%s", script_path)
            (folder, filename) = os.path.split(script_path)
            LOG.debug("folder=%s filename=%s", folder, filename)
            path = f"/var/lib/cloud/scripts/per-boot/{filename}"
            LOG.debug("path=%s", path)
            util.write_file(path, payload, 0o700)

### per-instance


### per-once

