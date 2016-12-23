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
be members of the group as the value.

The ``users`` config key takes a list of users to configure. The first entry in
this list is used as the default user for the system. To preserve the standard
default user for the distro, the string ``default`` may be used as the first
entry of the ``users`` list. Each entry in the ``users`` list, other than a
``default`` entry, should be a dictionary of options for the user. Supported
config keys for an entry in ``users`` are as follows:

    - ``name``: The user's login name
    - ``homedir``: Optional. Home dir for user. Default is ``/home/<username>``
    - ``primary-group``: Optional. Primary group for user. Default to new group
      named after user.
    - ``groups``: Optional. Additional groups to add the user to. Default: none
    - ``selinux-user``: Optional. SELinux user for user's login. Default to
      default SELinux user.
    - ``lock_passwd``: Optional. Disable password login. Default: true
    - ``inactive``: Optional. Mark user inactive. Default: false
    - ``passwd``: Hash of user password
    - ``no-create-home``: Optional. Do not create home directory. Default:
      false
    - ``no-user-group``: Optional. Do not create group named after user.
      Default: false
    - ``no-log-init``: Optional. Do not initialize lastlog and faillog for
      user. Default: false
    - ``ssh-import-id``: Optional. SSH id to import for user. Default: none
    - ``ssh-autorized-keys``: Optional. List of ssh keys to add to user's
      authkeys file. Default: none
    - ``sudo``: Optional. Sudo rule to use, or list of sudo rules to use.
      Default: none.
    - ``system``: Optional. Create user as system user with no home directory.
      Default: false

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
        - ubuntu: [foo, bar]
        - cloud-users

    users:
        - default
        - name: <username>
          gecos: <real name>
          primary-group: <primary group>
          groups: <additional groups>
          selinux-user: <selinux username>
          expiredate: <date>
          ssh-import-id: <none/id>
          lock_passwd: <true/false>
          passwd: <password>
          sudo: <sudo config>
          inactive: <true/false>
          system: <true/false>
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
