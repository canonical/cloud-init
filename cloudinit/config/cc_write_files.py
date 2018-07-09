# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""
Write Files
-----------
**Summary:** write arbitrary files

Write out arbitrary content to files, optionally setting permissions. Content
can be specified in plain text or binary. Data encoded with either base64 or
binary gzip data can be specified and will be decoded before being written.

.. note::
    if multiline data is provided, care should be taken to ensure that it
    follows yaml formatting standards. to specify binary data, use the yaml
    option ``!!binary``

.. note::
    Do not write files under /tmp during boot because of a race with
    systemd-tmpfiles-clean that can cause temp files to get cleaned during
    the early boot process. Use /run/somedir instead to avoid race LP:1707222.

**Internal name:** ``cc_write_files``

**Module frequency:** per instance

**Supported distros:** all

**Config keys**::

    write_files:
        - encoding: b64
          content: CiMgVGhpcyBmaWxlIGNvbnRyb2xzIHRoZSBzdGF0ZSBvZiBTRUxpbnV4...
          owner: root:root
          path: /etc/sysconfig/selinux
          permissions: '0644'
        - content: |
            # My new /etc/sysconfig/samba file

            SMDBOPTIONS="-D"
          path: /etc/sysconfig/samba
        - content: !!binary |
            f0VMRgIBAQAAAAAAAAAAAAIAPgABAAAAwARAAAAAAABAAAAAAAAAAJAVAAAAAA
            AEAAHgAdAAYAAAAFAAAAQAAAAAAAAABAAEAAAAAAAEAAQAAAAAAAwAEAAAAAAA
            AAAAAAAAAwAAAAQAAAAAAgAAAAAAAAACQAAAAAAAAAJAAAAAAAAcAAAAAAAAAB
            ...
          path: /bin/arch
          permissions: '0555'
"""

import base64
import os
import six

from cloudinit import log as logging
from cloudinit.settings import PER_INSTANCE
from cloudinit import util


frequency = PER_INSTANCE

DEFAULT_OWNER = "root:root"
DEFAULT_PERMS = 0o644
UNKNOWN_ENC = 'text/plain'

LOG = logging.getLogger(__name__)


def handle(name, cfg, _cloud, log, _args):
    files = cfg.get('write_files')
    if not files:
        log.debug(("Skipping module named %s,"
                   " no/empty 'write_files' key in configuration"), name)
        return
    write_files(name, files)


def canonicalize_extraction(encoding_type):
    if not encoding_type:
        encoding_type = ''
    encoding_type = encoding_type.lower().strip()
    if encoding_type in ['gz', 'gzip']:
        return ['application/x-gzip']
    if encoding_type in ['gz+base64', 'gzip+base64', 'gz+b64', 'gzip+b64']:
        return ['application/base64', 'application/x-gzip']
    # Yaml already encodes binary data as base64 if it is given to the
    # yaml file as binary, so those will be automatically decoded for you.
    # But the above b64 is just for people that are more 'comfortable'
    # specifing it manually (which might be a possiblity)
    if encoding_type in ['b64', 'base64']:
        return ['application/base64']
    if encoding_type:
        LOG.warning("Unknown encoding type %s, assuming %s",
                    encoding_type, UNKNOWN_ENC)
    return [UNKNOWN_ENC]


def write_files(name, files):
    if not files:
        return

    for (i, f_info) in enumerate(files):
        path = f_info.get('path')
        if not path:
            LOG.warning("No path provided to write for entry %s in module %s",
                        i + 1, name)
            continue
        path = os.path.abspath(path)
        extractions = canonicalize_extraction(f_info.get('encoding'))
        contents = extract_contents(f_info.get('content', ''), extractions)
        (u, g) = util.extract_usergroup(f_info.get('owner', DEFAULT_OWNER))
        perms = decode_perms(f_info.get('permissions'), DEFAULT_PERMS)
        util.write_file(path, contents, mode=perms)
        util.chownbyname(path, u, g)


def decode_perms(perm, default):
    if perm is None:
        return default
    try:
        if isinstance(perm, six.integer_types + (float,)):
            # Just 'downcast' it (if a float)
            return int(perm)
        else:
            # Force to string and try octal conversion
            return int(str(perm), 8)
    except (TypeError, ValueError):
        reps = []
        for r in (perm, default):
            try:
                reps.append("%o" % r)
            except TypeError:
                reps.append("%r" % r)
        LOG.warning(
            "Undecodable permissions %s, returning default %s", *reps)
        return default


def extract_contents(contents, extraction_types):
    result = contents
    for t in extraction_types:
        if t == 'application/x-gzip':
            result = util.decomp_gzip(result, quiet=False, decode=False)
        elif t == 'application/base64':
            result = base64.b64decode(result)
        elif t == UNKNOWN_ENC:
            pass
    return result

# vi: ts=4 expandtab
