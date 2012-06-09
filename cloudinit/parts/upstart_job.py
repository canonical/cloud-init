import os

from cloudinit import util
from cloudinit.settings import (PER_ALWAYS, PER_INSTANCE)
from cloudinit import log as logging
from cloudinit import parts

LOG = logging.getLogger(__name__)


class UpstartJobPartHandler(parts.PartHandler):
    def __init__(self, upstart_dir):
        parts.PartHandler.__init__(self, PER_INSTANCE)
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
