# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"Yum Add Repo: Add yum repository configuration to the system"

import io
import os
from configparser import ConfigParser
from logging import Logger
from textwrap import dedent

from cloudinit import util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.settings import PER_INSTANCE

MODULE_DESCRIPTION = """\
Add yum repository configuration to ``/etc/yum.repos.d``. Configuration files
are named based on the opaque dictionary key under the ``yum_repos`` they are
specified with. If a config file already exists with the same name as a config
entry, the config entry will be skipped.
"""

distros = [
    "almalinux",
    "centos",
    "cloudlinux",
    "eurolinux",
    "fedora",
    "mariner",
    "openEuler",
    "openmandriva",
    "photon",
    "rhel",
    "rocky",
    "virtuozzo",
]

COPR_BASEURL = (
    "https://download.copr.fedorainfracloud.org/results/@cloud-init/"
    "cloud-init-dev/epel-8-$basearch/"
)
COPR_GPG_URL = (
    "https://download.copr.fedorainfracloud.org/results/@cloud-init/"
    "cloud-init-dev/pubkey.gpg"
)
EPEL_TESTING_BASEURL = (
    "https://download.copr.fedorainfracloud.org/results/@cloud-init/"
    "cloud-init-dev/pubkey.gpg"
)

meta: MetaSchema = {
    "id": "cc_yum_add_repo",
    "name": "Yum Add Repo",
    "title": "Add yum repository configuration to the system",
    "description": MODULE_DESCRIPTION,
    "distros": distros,
    "examples": [
        dedent(
            """\
            yum_repos:
              my_repo:
                baseurl: http://blah.org/pub/epel/testing/5/$basearch/
            yum_repo_dir: /store/custom/yum.repos.d
            """
        ),
        dedent(
            f"""\
            # Enable cloud-init upstream's daily testing repo for EPEL 8 to
            # install latest cloud-init from tip of `main` for testing.
            yum_repos:
              cloud-init-daily:
                name: Copr repo for cloud-init-dev owned by @cloud-init
                baseurl: {COPR_BASEURL}
                type: rpm-md
                skip_if_unavailable: true
                gpgcheck: true
                gpgkey: {COPR_GPG_URL}
                enabled_metadata: 1
            """
        ),
        dedent(
            f"""\
            # Add the file /etc/yum.repos.d/epel_testing.repo which can then
            # subsequently be used by yum for later operations.
            yum_repos:
            # The name of the repository
             epel-testing:
               baseurl: {EPEL_TESTING_BASEURL}
               enabled: false
               failovermethod: priority
               gpgcheck: true
               gpgkey: file:///etc/pki/rpm-gpg/RPM-GPG-KEY-EPEL
               name: Extra Packages for Enterprise Linux 5 - Testing
            """
        ),
        dedent(
            """\
            # Any yum repo configuration can be passed directly into
            # the repository file created. See: man yum.conf for supported
            # config keys.
            #
            # Write /etc/yum.conf.d/my-package-stream.repo with gpgkey checks
            # on the repo data of the repository enabled.
            yum_repos:
              my package stream:
                baseurl: http://blah.org/pub/epel/testing/5/$basearch/
                mirrorlist: http://some-url-to-list-of-baseurls
                repo_gpgcheck: 1
                enable_gpgcheck: true
                gpgkey: https://url.to.ascii-armored-gpg-key
            """
        ),
    ],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": ["yum_repos"],
}

__doc__ = get_meta_doc(meta)


def _canonicalize_id(repo_id: str) -> str:
    """Canonicalize repo id.

    The sole name convention for repo ids is to not contain namespaces,
    and typically the separator used is `-`. More info:
    https://access.redhat.com/documentation/en-us/red_hat_enterprise_linux/6/html/deployment_guide/sec-setting_repository_options

    :param repo_id: Repo id to convert.
    :return: Canonical repo id.
    """
    return repo_id.replace(" ", "-")


def _format_repo_value(val):
    if isinstance(val, (bool)):
        # Seems like yum prefers 1/0
        return str(int(val))
    if isinstance(val, (list, tuple)):
        # Can handle 'lists' in certain cases
        # See: https://linux.die.net/man/5/yum.conf
        return "\n".join([_format_repo_value(v) for v in val])
    if not isinstance(val, str):
        return str(val)
    return val


# TODO(harlowja): move to distro?
# See man yum.conf
def _format_repository_config(repo_id, repo_config):
    to_be = ConfigParser()
    to_be.add_section(repo_id)
    # Do basic translation of the items -> values
    for (k, v) in repo_config.items():
        # For now assume that people using this know
        # the format of yum and don't verify keys/values further
        to_be.set(repo_id, k, _format_repo_value(v))
    to_be_stream = io.StringIO()
    to_be.write(to_be_stream)
    to_be_stream.seek(0)
    lines = to_be_stream.readlines()
    lines.insert(0, "# Created by cloud-init on %s\n" % (util.time_rfc2822()))
    return "".join(lines)


def handle(
    name: str, cfg: Config, cloud: Cloud, log: Logger, args: list
) -> None:
    repos = cfg.get("yum_repos")
    if not repos:
        log.debug(
            "Skipping module named %s, no 'yum_repos' configuration found",
            name,
        )
        return
    repo_base_path = util.get_cfg_option_str(
        cfg, "yum_repo_dir", "/etc/yum.repos.d/"
    )
    repo_locations = {}
    repo_configs = {}
    for (repo_id, repo_config) in repos.items():
        canon_repo_id = _canonicalize_id(repo_id)
        repo_fn_pth = os.path.join(repo_base_path, "%s.repo" % (canon_repo_id))
        if os.path.exists(repo_fn_pth):
            log.info(
                "Skipping repo %s, file %s already exists!",
                repo_id,
                repo_fn_pth,
            )
            continue
        elif canon_repo_id in repo_locations:
            log.info(
                "Skipping repo %s, file %s already pending!",
                repo_id,
                repo_fn_pth,
            )
            continue
        if not repo_config:
            repo_config = {}
        # Do some basic sanity checks/cleaning
        n_repo_config = {}
        for (k, v) in repo_config.items():
            k = k.lower().strip().replace("-", "_")
            if k:
                n_repo_config[k] = v
        repo_config = n_repo_config
        missing_required = 0
        for req_field in ["baseurl"]:
            if req_field not in repo_config:
                log.warning(
                    "Repository %s does not contain a %s"
                    " configuration 'required' entry",
                    repo_id,
                    req_field,
                )
                missing_required += 1
        if not missing_required:
            repo_configs[canon_repo_id] = repo_config
            repo_locations[canon_repo_id] = repo_fn_pth
        else:
            log.warning(
                "Repository %s is missing %s required fields, skipping!",
                repo_id,
                missing_required,
            )
    for (c_repo_id, path) in repo_locations.items():
        repo_blob = _format_repository_config(
            c_repo_id, repo_configs.get(c_repo_id)
        )
        util.write_file(path, repo_blob)


# vi: ts=4 expandtab
