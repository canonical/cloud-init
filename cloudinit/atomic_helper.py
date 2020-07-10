# This file is part of cloud-init. See LICENSE file for license information.

import json
import logging
import os
import stat
import tempfile

_DEF_PERMS = 0o644
LOG = logging.getLogger(__name__)


def write_file(filename, content, mode=_DEF_PERMS,
               omode="wb", preserve_mode=False):
    # open filename in mode 'omode', write content, set permissions to 'mode'

    if preserve_mode:
        try:
            file_stat = os.stat(filename)
            mode = stat.S_IMODE(file_stat.st_mode)
        except OSError:
            pass

    tf = None
    try:
        tf = tempfile.NamedTemporaryFile(dir=os.path.dirname(filename),
                                         delete=False, mode=omode)
        LOG.debug(
            "Atomically writing to file %s (via temporary file %s) - %s: [%o]"
            " %d bytes/chars",
            filename, tf.name, omode, mode, len(content))
        tf.write(content)
        tf.close()
        os.chmod(tf.name, mode)
        os.rename(tf.name, filename)
    except Exception as e:
        if tf is not None:
            os.unlink(tf.name)
        raise e


def write_json(filename, data, mode=_DEF_PERMS):
    # dump json representation of data to file filename.
    return write_file(
        filename, json.dumps(data, indent=1, sort_keys=True) + "\n",
        omode="w", mode=mode)

# vi: ts=4 expandtab
