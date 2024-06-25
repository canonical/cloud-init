# Copyright (C) 2009-2010 Canonical Ltd.
# Copyright (C) 2012, 2013 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
"""SSH Import ID: Import SSH id"""

import logging
import pwd

from cloudinit import subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.distros import ug_util
from cloudinit.settings import PER_INSTANCE

# https://launchpad.net/ssh-import-id

SSH_IMPORT_ID_BINARY = "ssh-import-id"

meta: MetaSchema = {
    "id": "cc_ssh_import_id",
    "distros": ["alpine", "cos", "debian", "ubuntu"],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": [],
}  # type: ignore

LOG = logging.getLogger(__name__)


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:

    if not is_key_in_nested_dict(cfg, "ssh_import_id"):
        LOG.debug(
            "Skipping module named ssh_import_id, no 'ssh_import_id'"
            " directives found."
        )
        return
    elif not subp.which(SSH_IMPORT_ID_BINARY):
        LOG.warning(
            "ssh-import-id is not installed, but module ssh_import_id is "
            "configured. Skipping module."
        )
        return

    # import for "user: XXXXX"
    if len(args) != 0:
        user = args[0]
        ids = []
        if len(args) > 1:
            ids = args[1:]

        import_ssh_ids(ids, user)
        return

    # import for cloudinit created users
    (users, _groups) = ug_util.normalize_users_groups(cfg, cloud.distro)
    elist = []
    for (user, user_cfg) in users.items():
        import_ids = []
        if user_cfg["default"]:
            import_ids = util.get_cfg_option_list(cfg, "ssh_import_id", [])
        else:
            try:
                import_ids = user_cfg["ssh_import_id"]
            except Exception:
                LOG.debug("User %s is not configured for ssh_import_id", user)
                continue

        try:
            import_ids = util.uniq_merge(import_ids)
            import_ids = [str(i) for i in import_ids]
        except Exception:
            LOG.debug(
                "User %s is not correctly configured for ssh_import_id", user
            )
            continue

        if not len(import_ids):
            continue

        try:
            import_ssh_ids(import_ids, user)
        except Exception as exc:
            util.logexc(
                LOG, "ssh-import-id failed for: %s %s", user, import_ids
            )
            elist.append(exc)

    if len(elist):
        raise elist[0]


def import_ssh_ids(ids, user):

    if not (user and ids):
        LOG.debug("empty user(%s) or ids(%s). not importing", user, ids)
        return

    try:
        pwd.getpwnam(user)
    except KeyError as exc:
        raise exc

    # TODO: We have a use case that involes setting a proxy value earlier
    # in boot and the user wants this env used when using ssh-import-id.
    # E.g.,:
    # bootcmd:
    #   - mkdir -p /etc/systemd/system/cloud-config.service.d
    #   - mkdir -p /etc/systemd/system/cloud-final.service.d
    # write_files:
    #   - content: |
    #       http_proxy=http://192.168.1.2:3128/
    #       https_proxy=http://192.168.1.2:3128/
    #     path: /etc/cloud/env
    #   - content: |
    #       [Service]
    #       EnvironmentFile=/etc/cloud/env
    #       PassEnvironment=https_proxy http_proxy
    #     path: /etc/systemd/system/cloud-config.service.d/override.conf
    #   - content: |
    #       [Service]
    #       EnvironmentFile=/etc/cloud/env
    #       PassEnvironment=https_proxy http_proxy
    #     path: /etc/systemd/system/cloud-final.service.d/override.conf
    #
    # I'm including the `--preserve-env` here as a one-off, but we should
    # have a better way of setting env earlier in boot and using it later.
    # Perhaps a 'set_env' module?
    if subp.which("sudo"):
        cmd = [
            "sudo",
            "--preserve-env=https_proxy",
            "-Hu",
            user,
            SSH_IMPORT_ID_BINARY,
        ] + ids
    elif subp.which("doas"):
        cmd = [
            "doas",
            "-u",
            user,
            SSH_IMPORT_ID_BINARY,
        ] + ids
    else:
        LOG.error("Neither sudo nor doas available! Unable to import SSH ids.")
        return
    LOG.debug("Importing SSH ids for user %s.", user)

    try:
        subp.subp(cmd, capture=False)
    except subp.ProcessExecutionError as exc:
        util.logexc(LOG, "Failed to run command to import %s SSH ids", user)
        raise exc


def is_key_in_nested_dict(config: dict, search_key: str) -> bool:
    """Search for key nested in config.

    Note: A dict embedded in a list of lists will not be found walked - but in
    this case we don't need it.
    """
    for config_key in config.keys():
        if search_key == config_key:
            return True
        if isinstance(config[config_key], dict):
            if is_key_in_nested_dict(config[config_key], search_key):
                return True
        if isinstance(config[config_key], list):
            # this code could probably be generalized to walking the whole
            # config by iterating lists in search of dictionaries
            for item in config[config_key]:
                if isinstance(item, dict):
                    if is_key_in_nested_dict(item, search_key):
                        return True
    return False
