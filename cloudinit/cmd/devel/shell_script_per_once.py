# part-handler
# vi: syntax=python ts=4

import os
from cloudinit import log
from cloudinit import util

LOG = log.getLogger(__name__)


def list_types():
    # return a list of mime-types that are handled by this module
    LOG.debug("in shell_script-per-once.list_types() ...")
    return(["text/x-shellscript-per-once"])


def handle_part(data, ctype, script_path, payload):
    if script_path is not None:
        LOG.info("in shell_script-per-once.handle_part() ...")
        LOG.debug("script_path=%s", script_path)
        (folder, filename) = os.path.split(script_path)
        LOG.debug("folder=%s filename=%s", folder, filename)
        path = f"/var/lib/cloud/scripts/per-once/{filename}"
        LOG.debug("path=%s", path)
        util.write_file(path, payload, 0o700)
