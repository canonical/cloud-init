#part-handler
# vi: syntax=python ts=4

from cloudinit import log
from cloudinit import util
import os
import pathlib

LOG = log.getLogger(__name__)


def list_types():
# return a list of mime-types that are handled by this module
    LOG.debug("### in shell_script-per-instance.list_types() ...")
    return(["text/x-shellscript-per-instance"])


def handle_part(data, ctype, script_path, payload):
    if script_path is not None:
        LOG.debug("### in shell_script-per-instance.handle_part() ...")
        LOG.debug(f"### x-shellscript-per-instance.handle_part: script_path={script_path}")
        (folder, filename) = os.path.split(script_path)
        LOG.debug(f"### folder={folder} filename={filename}")
        path = f"/var/lib/cloud/scripts/per-instance/{filename}"
        LOG.debug(f"### path={path}")
        util.write_file(path, payload, 0o700)
