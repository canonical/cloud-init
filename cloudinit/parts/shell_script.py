import os

from cloudinit import util
from cloudinit.settings import (PER_ALWAYS, PER_INSTANCE)
from cloudinit import log as logging
from cloudinit import parts

LOG = logging.getLogger(__name__)


class ShellScriptPartHandler(parts.PartHandler):

    def __init__(self, script_dir):
        parts.PartHandler.__init__(self, PER_ALWAYS)
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
