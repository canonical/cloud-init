# Copyright (C) 2021 TODO
#
# Author: TODO
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Defer writing certain files like files defined in the Users & Groups module"""

from textwrap import dedent

from cloudinit.config.schema import validate_cloudconfig_schema
from cloudinit import log as logging
from cloudinit.settings import PER_INSTANCE
from cloudinit import util
from cloudinit.config.cc_write_files import ( schema as write_files_schema, write_files )
from cloudinit.distros import ug_util


frequency = PER_INSTANCE

DEFAULT_OWNER = ":"
DEFAULT_PERMS = '0600'
UNKNOWN_ENC = 'text/plain'

LOG = logging.getLogger(__name__)

distros = ['all']

schema = {
    'id': 'cc_write_deferred_files',
    'name': 'Write Deferred Files',
    'title': 'write certain files, whose creation as been deferred, during final stage',
    'description': dedent("""\
        This module is heavily based on `'Write Files' <write-files>`__, but
        the list of files being created, is gathered from other parts of the
        configuration. Therefore, the same options are available, but, depending
        on where a file is defined, certain attributes may be inferred.
        
        See the respective module documentation for details:
        
            - `Users and Groups`_
    `"""),
    'distros': distros,
    'examples': [
        dedent("""\
        # Extend ~/.profile after user (and probably the file itself) has been created
        users:
        - name: 'alice'
          files:
          - path: '/home/alice/.profile'
            content: |
              PATH="/usr/local/opt/python37/bin:$PATH"
            append: true
        """)
    ],
    'frequency': frequency,
    'type': 'object',
    'properties': {
        'users': {
            'type': ['array'],
            'items': {
                'type': ['string', 'object'],
                'additionalProperties': True,
                'properties': {
                    'name': {
                        'type': 'string',
                        'description': 'name of the user'
                    },
                    'files': util.mergemanydict([
                        {
                            'type': ['array'],
                            'items': {
                                'type': 'object',
                                'properties': {
                                    'owner': {
                                        'type': 'string',
                                        'default': DEFAULT_OWNER,
                                        'description': dedent("""\
                                            Optional group to chown on the file (user is ignored). Default:
                                            **user:user**
                                        """),
                                    },
                                    'permissions': {
                                        'type': 'string',
                                        'default': DEFAULT_PERMS,
                                        'description': dedent("""\
                                            Optional file permissions to set on ``path``
                                            represented as an octal string '0###'. Default:
                                            **'{perms}'**
                                        """.format(perms=DEFAULT_PERMS)),
                                    }
                                }
                            }
                        },
                        write_files_schema.get('properties').get('write_files')
                    ])
                }
            }
        }
    }
}

# Not exposed, because related modules should document this behaviour
__doc__ = None


def handle(name, cfg, cloud, log, _args):
    validate_cloudconfig_schema(cfg, schema)
    file_list = extract_deferred_files(cfg, cloud)
    if len(file_list) <= 0:
        log.debug(("Skipping module named %s,"
                   " no deferred file writing in configuration"), name)
        return
    write_files(name, file_list)


def extract_deferred_files(cfg, cloud):
    deferred_files = []

    (users, _) = ug_util.normalize_users_groups(cfg, cloud.distro)
    for (user, config) in users.items():
        user_files = config.get('files', [])
        for file in user_files:
            (_, file_owner_group) = util.extract_usergroup(file.get('owner', DEFAULT_OWNER))
            if file_owner_group is None:
               file_owner_group = user
            file['owner'] = "{u}:{g}".format(u=user, g=file_owner_group)
            file['permissions'] = config.get('permissions', DEFAULT_PERMS)
            deferred_files.append(file)

    return deferred_files


# vi: ts=4 expandtab
