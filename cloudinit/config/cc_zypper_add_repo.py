#
#    Copyright (C) 2017 SUSE LLC.
#
# This file is part of cloud-init. See LICENSE file for license information.

"""zypper_add_repo: Add zypper repositories to the system"""

import os
from logging import Logger
from textwrap import dedent

import configobj

from cloudinit import log as logging
from cloudinit import util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.settings import PER_ALWAYS

distros = ["opensuse", "sles"]
MODULE_DESCRIPTION = """\
Zypper behavior can be configured using the ``config`` key, which will modify
``/etc/zypp/zypp.conf``. The configuration writer will only append the
provided configuration options to the configuration file. Any duplicate
options will be resolved by the way the zypp.conf INI file is parsed.

.. note::
    Setting ``configdir`` is not supported and will be skipped.

The ``repos`` key may be used to add repositories to the system. Beyond the
required ``id`` and ``baseurl`` attributions, no validation is performed
on the ``repos`` entries. It is assumed the user is familiar with the
zypper repository file format.
"""
meta: MetaSchema = {
    "id": "cc_zypper_add_repo",
    "name": "Zypper Add Repo",
    "title": "Configure zypper behavior and add zypper repositories",
    "description": MODULE_DESCRIPTION,
    "distros": distros,
    "examples": [
        dedent(
            """\
        zypper:
          repos:
            - id: opensuse-oss
              name: os-oss
              baseurl: http://dl.opensuse.org/dist/leap/v/repo/oss/
              enabled: 1
              autorefresh: 1
            - id: opensuse-oss-update
              name: os-oss-up
              baseurl: http://dl.opensuse.org/dist/leap/v/update
              # any setting per
              # https://en.opensuse.org/openSUSE:Standards_RepoInfo
              # enable and autorefresh are on by default
          config:
            reposdir: /etc/zypp/repos.dir
            servicesdir: /etc/zypp/services.d
            download.use_deltarpm: true
            # any setting in /etc/zypp/zypp.conf
    """
        )
    ],
    "frequency": PER_ALWAYS,
    "activate_by_schema_keys": ["zypper"],
}

__doc__ = get_meta_doc(meta)

LOG = logging.getLogger(__name__)


def _canonicalize_id(repo_id):
    repo_id = repo_id.replace(" ", "_")
    return repo_id


def _format_repo_value(val):
    if isinstance(val, bool):
        # zypp prefers 1/0
        return 1 if val else 0
    if isinstance(val, (list, tuple)):
        return "\n    ".join([_format_repo_value(v) for v in val])
    if not isinstance(val, str):
        return str(val)
    return val


def _format_repository_config(repo_id, repo_config):
    to_be = configobj.ConfigObj()
    to_be[repo_id] = {}
    # Do basic translation of the items -> values
    for (k, v) in repo_config.items():
        # For now assume that people using this know the format
        # of zypper repos  and don't verify keys/values further
        to_be[repo_id][k] = _format_repo_value(v)
    lines = to_be.write()
    return "\n".join(lines)


def _write_repos(repos, repo_base_path):
    """Write the user-provided repo definition files
    @param repos: A list of repo dictionary objects provided by the user's
        cloud config.
    @param repo_base_path: The directory path to which repo definitions are
        written.
    """

    if not repos:
        return
    valid_repos = {}
    for index, user_repo_config in enumerate(repos):
        # Skip on absent required keys
        missing_keys = set(["id", "baseurl"]).difference(set(user_repo_config))
        if missing_keys:
            LOG.warning(
                "Repo config at index %d is missing required config keys: %s",
                index,
                ",".join(missing_keys),
            )
            continue
        repo_id = user_repo_config.get("id")
        canon_repo_id = _canonicalize_id(repo_id)
        repo_fn_pth = os.path.join(repo_base_path, "%s.repo" % (canon_repo_id))
        if os.path.exists(repo_fn_pth):
            LOG.info(
                "Skipping repo %s, file %s already exists!",
                repo_id,
                repo_fn_pth,
            )
            continue
        elif repo_id in valid_repos:
            LOG.info(
                "Skipping repo %s, file %s already pending!",
                repo_id,
                repo_fn_pth,
            )
            continue

        # Do some basic key formatting
        repo_config = dict(
            (k.lower().strip().replace("-", "_"), v)
            for k, v in user_repo_config.items()
            if k and k != "id"
        )

        # Set defaults if not present
        for field in ["enabled", "autorefresh"]:
            if field not in repo_config:
                repo_config[field] = "1"

        valid_repos[repo_id] = (repo_fn_pth, repo_config)

    for (repo_id, repo_data) in valid_repos.items():
        repo_blob = _format_repository_config(repo_id, repo_data[-1])
        util.write_file(repo_data[0], repo_blob)


def _write_zypp_config(zypper_config):
    """Write to the default zypp configuration file /etc/zypp/zypp.conf"""
    if not zypper_config:
        return
    zypp_config = "/etc/zypp/zypp.conf"
    zypp_conf_content = util.load_file(zypp_config)
    new_settings = ["# Added via cloud.cfg"]
    for setting, value in zypper_config.items():
        if setting == "configdir":
            msg = "Changing the location of the zypper configuration is "
            msg += 'not supported, skipping "configdir" setting'
            LOG.warning(msg)
            continue
        if value:
            new_settings.append("%s=%s" % (setting, value))
    if len(new_settings) > 1:
        new_config = zypp_conf_content + "\n".join(new_settings)
    else:
        new_config = zypp_conf_content
    util.write_file(zypp_config, new_config)


def handle(
    name: str, cfg: Config, cloud: Cloud, log: Logger, args: list
) -> None:
    zypper_section = cfg.get("zypper")
    if not zypper_section:
        LOG.debug(
            "Skipping module named %s,"
            " no 'zypper' relevant configuration found",
            name,
        )
        return
    repos = zypper_section.get("repos")
    if not repos:
        LOG.debug(
            "Skipping module named %s, no 'repos' configuration found", name
        )
        return
    zypper_config = zypper_section.get("config", {})
    repo_base_path = zypper_config.get("reposdir", "/etc/zypp/repos.d/")

    _write_zypp_config(zypper_config)
    _write_repos(repos, repo_base_path)


# vi: ts=4 expandtab
