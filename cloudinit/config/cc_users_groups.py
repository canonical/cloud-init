# Copyright (C) 2012 Canonical Ltd.
#
# Author: Ben Howard <ben.howard@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"Users and Groups: Configure users and groups"

from logging import Logger
from textwrap import dedent

from cloudinit import log as logging
from cloudinit.cloud import Cloud

# Ensure this is aliased to a name not 'distros'
# since the module attribute 'distros'
# is a list of distros that are supported, not a sub-module
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.distros import ug_util
from cloudinit.settings import PER_INSTANCE

MODULE_DESCRIPTION = """\
This module configures users and groups. For more detailed information on user
options, see the :ref:`Including users and groups<yaml_examples>` config
example.

Groups to add to the system can be specified under the ``groups`` key as
a string of comma-separated groups to create, or a list. Each item in
the list should either contain a string of a single group to create,
or a dictionary with the group name as the key and string of a single user as
a member of that group or a list of users who should be members of the group.

.. note::
   Groups are added before users, so any users in a group list must
   already exist on the system.

Users to add can be specified as a string or list under the ``users`` key.
Each entry in the list should either be a string or a dictionary. If a string
is specified, that string can be comma-separated usernames to create or the
reserved string ``default`` which represents the primary admin user used to
access the system. The ``default`` user varies per distribution and is
generally configured in ``/etc/cloud/cloud.cfg`` by the ``default_user`` key.

Each ``users`` dictionary item must contain either a ``name`` or ``snapuser``
key, otherwise it will be ignored. Omission of ``default`` as the first item
in the ``users`` list skips creation the default user. If no ``users`` key is
provided the default behavior is to create the default user via this config::

 users:
 - default

.. note::
    Specifying a hash of a user's password with ``passwd`` is a security risk
    if the cloud-config can be intercepted. SSH authentication is preferred.

.. note::
    If specifying a sudo rule for a user, ensure that the syntax for the rule
    is valid, as it is not checked by cloud-init.

.. note::
    Most of these configuration options will not be honored if the user
    already exists. The following options are the exceptions; they are applied
    to already-existing users: ``plain_text_passwd``, ``hashed_passwd``,
    ``lock_passwd``, ``sudo``, ``ssh_authorized_keys``, ``ssh_redirect_user``.

The ``user`` key can be used to override the ``default_user`` configuration
defined in ``/etc/cloud/cloud.cfg``. The ``user`` value should be a dictionary
which supports the same config keys as the ``users`` dictionary items.
"""

meta: MetaSchema = {
    "id": "cc_users_groups",
    "name": "Users and Groups",
    "title": "Configure users and groups",
    "description": MODULE_DESCRIPTION,
    "distros": ["all"],
    "examples": [
        dedent(
            """\
        # Add the ``default_user`` from /etc/cloud/cloud.cfg.
        # This is also the default behavior of cloud-init when no `users` key
        # is provided.
        users:
        - default
        """
        ),
        dedent(
            """\
        # Add the 'admingroup' with members 'root' and 'sys' and an empty
        # group cloud-users.
        groups:
        - admingroup: [root,sys]
        - cloud-users
        """
        ),
        dedent(
            """\
        # Skip creation of the <default> user and only create newsuper.
        # Password-based login is rejected, but the github user TheRealFalcon
        # and the launchpad user falcojr can SSH as newsuper. The default
        # shell for newsuper is bash instead of system default.
        users:
        - name: newsuper
          gecos: Big Stuff
          groups: users, admin
          sudo: ALL=(ALL) NOPASSWD:ALL
          shell: /bin/bash
          lock_passwd: true
          ssh_import_id:
            - lp:falcojr
            - gh:TheRealFalcon
        """
        ),
        dedent(
            """\
        # On a system with SELinux enabled, add youruser and set the
        # SELinux user to 'staff_u'. When omitted on SELinux, the system will
        # select the configured default SELinux user.
        users:
        - default
        - name: youruser
          selinux_user: staff_u
        """
        ),
        dedent(
            """\
        # To redirect a legacy username to the <default> user for a
        # distribution, ssh_redirect_user will accept an SSH connection and
        # emit a message telling the client to ssh as the <default> user.
        # SSH clients will get the message:
        users:
        - default
        - name: nosshlogins
          ssh_redirect_user: true
        """
        ),
        dedent(
            """\
        # Override any ``default_user`` config in /etc/cloud/cloud.cfg with
        # supplemental config options.
        # This config will make the default user to mynewdefault and change
        # the user to not have sudo rights.
        ssh_import_id: [chad.smith]
        user:
          name: mynewdefault
          sudo: null
        """
        ),
    ],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": [],
}

__doc__ = get_meta_doc(meta)

LOG = logging.getLogger(__name__)

# NO_HOME and NEED_HOME are mutually exclusive options
NO_HOME = ("no_create_home", "system")
NEED_HOME = ("ssh_authorized_keys", "ssh_import_id", "ssh_redirect_user")


def handle(
    name: str, cfg: Config, cloud: Cloud, log: Logger, args: list
) -> None:
    (users, groups) = ug_util.normalize_users_groups(cfg, cloud.distro)
    (default_user, _user_config) = ug_util.extract_default(users)
    cloud_keys = cloud.get_public_ssh_keys() or []

    for (name, members) in groups.items():
        cloud.distro.create_group(name, members)

    for (user, config) in users.items():

        no_home = [key for key in NO_HOME if config.get(key)]
        need_home = [key for key in NEED_HOME if config.get(key)]
        if no_home and need_home:
            raise ValueError(
                f"Not creating user {user}. Key(s) {', '.join(need_home)}"
                f" cannot be provided with {', '.join(no_home)}"
            )

        ssh_redirect_user = config.pop("ssh_redirect_user", False)
        if ssh_redirect_user:
            if "ssh_authorized_keys" in config or "ssh_import_id" in config:
                raise ValueError(
                    "Not creating user %s. ssh_redirect_user cannot be"
                    " provided with ssh_import_id or ssh_authorized_keys"
                    % user
                )
            if ssh_redirect_user not in (True, "default"):
                raise ValueError(
                    "Not creating user %s. Invalid value of"
                    " ssh_redirect_user: %s. Expected values: true, default"
                    " or false." % (user, ssh_redirect_user)
                )
            if default_user is None:
                LOG.warning(
                    "Ignoring ssh_redirect_user: %s for %s."
                    " No default_user defined."
                    " Perhaps missing cloud configuration users: "
                    " [default, ..].",
                    ssh_redirect_user,
                    user,
                )
            else:
                config["ssh_redirect_user"] = default_user
                config["cloud_public_ssh_keys"] = cloud_keys

        cloud.distro.create_user(user, **config)


# vi: ts=4 expandtab
