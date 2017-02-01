# This file is part of cloud-init. See LICENSE file for license information.

import json
import os
import tempfile

_DEF_PERMS = 0o644


def write_file(filename, content, mode=_DEF_PERMS, omode="wb"):
    # open filename in mode 'omode', write content, set permissions to 'mode'
    tf = None
    try:
        tf = tempfile.NamedTemporaryFile(dir=os.path.dirname(filename),
                                         delete=False, mode=omode)
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
