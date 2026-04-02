# Copyright (C) 2012 Canonical Ltd.
#
# Author: Ben Howard <ben.howard@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Users and Groups: Configure users and groups"""

import logging
from typing import List, Union

from cloudinit import lifecycle
from cloudinit.cloud import Cloud

# Ensure this is aliased to a name not 'distros'
# since the module attribute 'distros'
# is a list of distros that are supported, not a sub-module
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.distros import ug_util
from cloudinit.settings import PER_INSTANCE

meta: MetaSchema = {
    "id": "cc_users_groups",
    "distros": ["all"],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": [],
}

LOG = logging.getLogger(__name__)

# NO_HOME and NEED_HOME are mutually exclusive options
NO_HOME = ("no_create_home", "system")
NEED_HOME = ("ssh_authorized_keys", "ssh_import_id", "ssh_redirect_user")


def _normalize_user_groups(
    user: str, groups: Union[str, List[str], dict]
) -> List[str]:
    if not groups:
        return []

    if isinstance(groups, str):
        return [group.strip() for group in groups.split(",") if group.strip()]

    if isinstance(groups, dict):
        lifecycle.deprecate(
            deprecated=f"The user {user} has a 'groups' config value "
            "of type dict",
            deprecated_version="22.3",
            extra_message="Use a comma-delimited string or "
            "array instead: group1,group2.",
        )
        return list(groups)

    if isinstance(groups, list):
        if not all(isinstance(group, str) for group in groups):
            raise TypeError(
                f"Not creating user {user}. 'groups' must contain only "
                "string values."
            )
        return groups
    raise TypeError(
        f"Not creating user {user}. 'groups' must be a string, list, or dict."
    )


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    (users, groups) = ug_util.normalize_users_groups(cfg, cloud.distro)
    (default_user, _user_config) = ug_util.extract_default(users)
    cloud_keys = cloud.get_public_ssh_keys() or []

    for name, members in groups.items():
        cloud.distro.create_group(name, members)

    for user, config in users.items():
        user_groups = _normalize_user_groups(user, config.pop("groups", []))

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

        cloud.distro.create_user(user, groups=user_groups, **config)
