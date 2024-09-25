# This file is part of cloud-init. See LICENSE file for license information.

import json
import logging
import os
import stat
import tempfile
from base64 import b64decode, b64encode

from cloudinit import performance, util

_DEF_PERMS = 0o644
LOG = logging.getLogger(__name__)


@performance.timed("Base64 decoding")
def b64d(source):
    """base64 decode data

    :param source: a bytes or str to decode
    :return: base64 as a decoded str if utf-8 encoded, otherwise bytes
    """
    decoded = b64decode(source)
    try:
        return decoded.decode("utf-8")
    except UnicodeDecodeError:
        return decoded


@performance.timed("Base64 encoding")
def b64e(source):
    """base64 encode data

    :param source: a bytes or str to decode
    :return: base64 encoded str
    """
    if not isinstance(source, bytes):
        source = source.encode("utf-8")
    return b64encode(source).decode("utf-8")


def write_file(
    filename, content, mode=_DEF_PERMS, omode="wb", preserve_mode=False
):
    """open filename in mode omode, write content, set permissions to mode"""

    with performance.Timed(f"Writing {filename}"):
        return _write_file(filename, content, mode, omode, preserve_mode)


def _write_file(
    filename, content, mode=_DEF_PERMS, omode="wb", preserve_mode=False
):
    if preserve_mode:
        try:
            file_stat = os.stat(filename)
            mode = stat.S_IMODE(file_stat.st_mode)
        except OSError:
            pass

    tf = None
    try:
        dirname = os.path.dirname(filename)
        util.ensure_dir(dirname)
        tf = tempfile.NamedTemporaryFile(dir=dirname, delete=False, mode=omode)
        LOG.debug(
            "Atomically writing to file %s (via temporary file %s) - %s: [%o]"
            " %d bytes/chars",
            filename,
            tf.name,
            omode,
            mode,
            len(content),
        )
        tf.write(content)
        tf.close()
        os.chmod(tf.name, mode)
        os.rename(tf.name, filename)
    except Exception as e:
        if tf is not None:
            os.unlink(tf.name)
        raise e


def json_serialize_default(_obj):
    """Handler for types which aren't json serializable."""
    try:
        return "ci-b64:{0}".format(b64e(_obj))
    except AttributeError:
        return "Warning: redacted unserializable type {0}".format(type(_obj))


@performance.timed("Dumping json")
def json_dumps(data):
    """Return data in nicely formatted json."""
    return json.dumps(
        data,
        indent=1,
        sort_keys=True,
        separators=(",", ": "),
        default=json_serialize_default,
    )


def write_json(filename, data, mode=_DEF_PERMS):
    # dump json representation of data to file filename.
    return write_file(
        filename,
        json_dumps(data) + "\n",
        omode="w",
        mode=mode,
    )
