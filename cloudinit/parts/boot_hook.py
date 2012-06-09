import os

from cloudinit import util
from cloudinit.settings import (PER_ALWAYS, PER_INSTANCE)
from cloudinit import log as logging
from cloudinit import parts

LOG = logging.getLogger(__name__)



class BootHookPartHandler(parts.PartHandler):
    def __init__(self, boothook_dir, instance_id):
        parts.PartHandler.__init__(self, PER_ALWAYS)
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

