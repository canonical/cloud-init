# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Write Files: write arbitrary files"""

import base64
import os
from textwrap import dedent

from cloudinit.config.schema import (
    get_schema_doc, validate_cloudconfig_schema)
from cloudinit import log as logging
from cloudinit.settings import PER_INSTANCE
from cloudinit import util


frequency = PER_INSTANCE

DEFAULT_OWNER = "root:root"
DEFAULT_PERMS = 0o644
UNKNOWN_ENC = 'text/plain'

LOG = logging.getLogger(__name__)

distros = ['all']

# The schema definition for each cloud-config module is a strict contract for
# describing supported configuration parameters for each cloud-config section.
# It allows cloud-config to validate and alert users to invalid or ignored
# configuration options before actually attempting to deploy with said
# configuration.

supported_encoding_types = [
    'gz', 'gzip', 'gz+base64', 'gzip+base64', 'gz+b64', 'gzip+b64', 'b64',
    'base64']

schema = {
    'id': 'cc_write_files',
    'name': 'Write Files',
    'title': 'write arbitrary files',
    'description': dedent("""\
        Write out arbitrary content to files, optionally setting permissions.
        Parent folders in the path are created if absent.
        Content can be specified in plain text or binary. Data encoded with
        either base64 or binary gzip data can be specified and will be decoded
        before being written. For empty file creation, content can be omitted.

    .. note::
        if multiline data is provided, care should be taken to ensure that it
        follows yaml formatting standards. to specify binary data, use the yaml
        option ``!!binary``

    .. note::
        Do not write files under /tmp during boot because of a race with
        systemd-tmpfiles-clean that can cause temp files to get cleaned during
        the early boot process. Use /run/somedir instead to avoid race
        LP:1707222."""),
    'distros': distros,
    'examples': [
        dedent("""\
        # Write out base64 encoded content to /etc/sysconfig/selinux
        write_files:
        - encoding: b64
          content: CiMgVGhpcyBmaWxlIGNvbnRyb2xzIHRoZSBzdGF0ZSBvZiBTRUxpbnV4...
          owner: root:root
          path: /etc/sysconfig/selinux
          permissions: '0644'
        """),
        dedent("""\
        # Appending content to an existing file
        write_files:
        - content: |
            15 * * * * root ship_logs
          path: /etc/crontab
          append: true
        """),
        dedent("""\
        # Provide gziped binary content
        write_files:
        - encoding: gzip
          content: !!binary |
              H4sIAIDb/U8C/1NW1E/KzNMvzuBKTc7IV8hIzcnJVyjPL8pJ4QIA6N+MVxsAAAA=
          path: /usr/bin/hello
          permissions: '0755'
        """),
        dedent("""\
        # Create an empty file on the system
        write_files:
        - path: /root/CLOUD_INIT_WAS_HERE
        """)],
    'frequency': frequency,
    'type': 'object',
    'properties': {
        'write_files': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'path': {
                        'type': 'string',
                        'description': dedent("""\
                            Path of the file to which ``content`` is decoded
                            and written
                        """),
                    },
                    'content': {
                        'type': 'string',
                        'default': '',
                        'description': dedent("""\
                            Optional content to write to the provided ``path``.
                            When content is present and encoding is not '%s',
                            decode the content prior to writing. Default:
                            **''**
                        """ % UNKNOWN_ENC),
                    },
                    'owner': {
                        'type': 'string',
                        'default': DEFAULT_OWNER,
                        'description': dedent("""\
                            Optional owner:group to chown on the file. Default:
                            **{owner}**
                        """.format(owner=DEFAULT_OWNER)),
                    },
                    'permissions': {
                        'type': 'string',
                        'default': oct(DEFAULT_PERMS).replace('o', ''),
                        'description': dedent("""\
                            Optional file permissions to set on ``path``
                            represented as an octal string '0###'. Default:
                            **'{perms}'**
                        """.format(perms=oct(DEFAULT_PERMS).replace('o', ''))),
                    },
                    'encoding': {
                        'type': 'string',
                        'default': UNKNOWN_ENC,
                        'enum': supported_encoding_types,
                        'description': dedent("""\
                            Optional encoding type of the content. Default is
                            **text/plain** and no content decoding is
                            performed. Supported encoding types are:
                            %s.""" % ", ".join(supported_encoding_types)),
                    },
                    'append': {
                        'type': 'boolean',
                        'default': False,
                        'description': dedent("""\
                            Whether to append ``content`` to existing file if
                            ``path`` exists. Default: **false**.
                        """),
                    },
                },
                'required': ['path'],
                'additionalProperties': False
            },
        }
    }
}

__doc__ = get_schema_doc(schema)  # Supplement python help()


def handle(name, cfg, _cloud, log, _args):
    files = cfg.get('write_files')
    if not files:
        log.debug(("Skipping module named %s,"
                   " no/empty 'write_files' key in configuration"), name)
        return
    validate_cloudconfig_schema(cfg, schema)
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
        omode = 'ab' if util.get_cfg_option_bool(f_info, 'append') else 'wb'
        util.write_file(path, contents, omode=omode, mode=perms)
        util.chownbyname(path, u, g)


def decode_perms(perm, default):
    if perm is None:
        return default
    try:
        if isinstance(perm, (int, float)):
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
