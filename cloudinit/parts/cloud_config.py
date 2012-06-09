import os

from cloudinit import util
from cloudinit.settings import (PER_ALWAYS, PER_INSTANCE)
from cloudinit import log as logging
from cloudinit import parts

LOG = logging.getLogger(__name__)



class CloudConfigPartHandler(parts.PartHandler):
    def __init__(self, cloud_fn):
        parts.PartHandler.__init__(self, PER_ALWAYS)
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


