# Copyright (C) 2012 Canonical Ltd.
#
# Author: Ben Howard <ben.howard@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""
Users and Groups
----------------
**Summary:** configure users and groups

This module configures users and groups. For more detailed information on user
options, see the ``Including users and groups`` config example.

Groups to add to the system can be specified as a list under the ``groups``
key. Each entry in the list should either contain a the group name as a string,
or a dictionary with the group name as the key and a list of users who should
be members of the group as the value. **Note**: Groups are added before users,
so any users in a group list must already exist on the system.

The ``users`` config key takes a list of users to configure. The first entry in
this list is used as the default user for the system. To preserve the standard
default user for the distro, the string ``default`` may be used as the first
entry of the ``users`` list. Each entry in the ``users`` list, other than a
``default`` entry, should be a dictionary of options for the user. Supported
config keys for an entry in ``users`` are as follows:

    - ``name``: The user's login name
    - ``expiredate``: Optional. Date on which the user's login will be
      disabled. Default: none
    - ``gecos``: Optional. Comment about the user, usually a comma-separated
      string of real name and contact information. Default: none
    - ``groups``: Optional. Additional groups to add the user to. Default: none
    - ``homedir``: Optional. Home dir for user. Default is ``/home/<username>``
    - ``inactive``: Optional. Mark user inactive. Default: false
    - ``lock_passwd``: Optional. Disable password login. Default: true
    - ``no_create_home``: Optional. Do not create home directory. Default:
      false
    - ``no_log_init``: Optional. Do not initialize lastlog and faillog for
      user. Default: false
    - ``no_user_group``: Optional. Do not create group named after user.
      Default: false
    - ``passwd``: Hash of user password
    - ``primary_group``: Optional. Primary group for user. Default to new group
      named after user.
    - ``selinux_user``: Optional. SELinux user for user's login. Default to
      default SELinux user.
    - ``shell``: Optional. The user's login shell. The default is to set no
      shell, which results in a system-specific default being used.
    - ``snapuser``: Optional. Specify an email address to create the user as
      a Snappy user through ``snap create-user``. If an Ubuntu SSO account is
      associated with the address, username and SSH keys will be requested from
      there. Default: none
    - ``ssh_authorized_keys``: Optional. List of ssh keys to add to user's
      authkeys file. Default: none
    - ``ssh_import_id``: Optional. SSH id to import for user. Default: none
    - ``sudo``: Optional. Sudo rule to use, list of sudo rules to use or False.
      Default: none. An absence of sudo key, or a value of none or false
      will result in no sudo rules being written for the user.
    - ``system``: Optional. Create user as system user with no home directory.
      Default: false
    - ``uid``: Optional. The user's ID. Default: The next available value.

.. note::
    Specifying a hash of a user's password with ``passwd`` is a security risk
    if the cloud-config can be intercepted. SSH authentication is preferred.

.. note::
    If specifying a sudo rule for a user, ensure that the syntax for the rule
    is valid, as it is not checked by cloud-init.

**Internal name:** ``cc_users_groups``

**Module frequency:** per instance

**Supported distros:** all

**Config keys**::

    groups:
        - <group>: [<user>, <user>]
        - <group>

    users:
        - default
        # User explicitly omitted from sudo permission; also default behavior.
        - name: <some_restricted_user>
          sudo: false
        - name: <username>
          expiredate: <date>
          gecos: <comment>
          groups: <additional groups>
          homedir: <home directory>
          inactive: <true/false>
          lock_passwd: <true/false>
          no_create_home: <true/false>
          no_log_init: <true/false>
          no_user_group: <true/false>
          passwd: <password>
          primary_group: <primary group>
          selinux_user: <selinux username>
          shell: <shell path>
          snapuser: <email>
          ssh_authorized_keys:
              - <key>
              - <key>
          ssh_import_id: <id>
          sudo: <sudo config>
          system: <true/false>
          uid: <user id>
"""

# Ensure this is aliased to a name not 'distros'
# since the module attribute 'distros'
# is a list of distros that are supported, not a sub-module
from cloudinit.distros import ug_util

from cloudinit.settings import PER_INSTANCE

frequency = PER_INSTANCE


def handle(name, cfg, cloud, _log, _args):
    (users, groups) = ug_util.normalize_users_groups(cfg, cloud.distro)
    for (name, members) in groups.items():
        cloud.distro.create_group(name, members)
    for (user, config) in users.items():
        cloud.distro.create_user(user, **config)

# vi: ts=4 expandtab
