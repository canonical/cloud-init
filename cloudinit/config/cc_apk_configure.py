# Copyright (c) 2020 Dermot Bradley
#
# Author: Dermot Bradley <dermot_bradley@yahoo.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Apk Configure: Configures apk repositories file."""

import logging

from cloudinit import temp_utils, templater, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.settings import PER_INSTANCE

LOG = logging.getLogger(__name__)


# If no mirror is specified then use this one
DEFAULT_MIRROR = "https://alpine.global.ssl.fastly.net/alpine"


REPOSITORIES_TEMPLATE = """\
## template:jinja
#
# Created by cloud-init
#
# This file is written on first boot of an instance
#

{{ alpine_baseurl }}/{{ alpine_version }}/main
{% if community_enabled -%}
{{ alpine_baseurl }}/{{ alpine_version }}/community
{% endif -%}
{% if testing_enabled -%}
{% if alpine_version != 'edge' %}
#
# Testing - using with non-Edge installation may cause problems!
#
{% endif %}
{{ alpine_baseurl }}/edge/testing
{% endif %}
{% if local_repo != '' %}

#
# Local repo
#
{{ local_repo }}/{{ alpine_version }}
{% endif %}

"""

meta: MetaSchema = {
    "id": "cc_apk_configure",
    "distros": ["alpine"],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": ["apk_repos"],
}  # type: ignore


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    """
    Call to handle apk_repos sections in cloud-config file.

    @param name: The module name "apk_configure" from cloud.cfg
    @param cfg: A nested dict containing the entire cloud config contents.
    @param cloud: The CloudInit object in use.
    @param log: Pre-initialized Python logger object to use for logging.
    @param _args: Any module arguments from cloud.cfg
    """

    # If there is no "apk_repos" section in the configuration
    # then do nothing.
    apk_section = cfg.get("apk_repos")
    if not apk_section:
        LOG.debug(
            "Skipping module named %s, no 'apk_repos' section found", name
        )
        return

    # If "preserve_repositories" is explicitly set to True in
    # the configuration do nothing.
    if util.get_cfg_option_bool(apk_section, "preserve_repositories", False):
        LOG.debug(
            "Skipping module named %s, 'preserve_repositories' is set", name
        )
        return

    # If there is no "alpine_repo" subsection of "apk_repos" present in the
    # configuration then do nothing, as at least "version" is required to
    # create valid repositories entries.
    alpine_repo = apk_section.get("alpine_repo")
    if not alpine_repo:
        LOG.debug(
            "Skipping module named %s, no 'alpine_repo' configuration found",
            name,
        )
        return

    # If there is no "version" value present in configuration then do nothing.
    alpine_version = alpine_repo.get("version")
    if not alpine_version:
        LOG.debug(
            "Skipping module named %s, 'version' not specified in alpine_repo",
            name,
        )
        return

    local_repo = apk_section.get("local_repo_base_url", "")

    _write_repositories_file(alpine_repo, alpine_version, local_repo)


def _write_repositories_file(alpine_repo, alpine_version, local_repo):
    """
    Write the /etc/apk/repositories file with the specified entries.

    @param alpine_repo: A nested dict of the alpine_repo configuration.
    @param alpine_version: A string of the Alpine version to use.
    @param local_repo: A string containing the base URL of a local repo.
    """

    repo_file = "/etc/apk/repositories"

    alpine_baseurl = alpine_repo.get("base_url", DEFAULT_MIRROR)

    params = {
        "alpine_baseurl": alpine_baseurl,
        "alpine_version": alpine_version,
        "community_enabled": alpine_repo.get("community_enabled"),
        "testing_enabled": alpine_repo.get("testing_enabled"),
        "local_repo": local_repo,
    }

    tfile = temp_utils.mkstemp(prefix="template_name-", suffix=".tmpl")
    template_fn = tfile[1]  # Filepath is second item in tuple
    util.write_file(template_fn, content=REPOSITORIES_TEMPLATE)

    LOG.debug("Generating Alpine repository configuration file: %s", repo_file)
    templater.render_to_file(template_fn, repo_file, params)
    # Clean up temporary template
    util.del_file(template_fn)
