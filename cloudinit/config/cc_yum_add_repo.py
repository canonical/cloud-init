# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""
Yum Add Repo
------------
**Summary:** add yum repository configuration to the system

Add yum repository configuration to ``/etc/yum.repos.d``. Configuration files
are named based on the dictionary key under the ``yum_repos`` they are
specified with. If a config file already exists with the same name as a config
entry, the config entry will be skipped.

**Internal name:** ``cc_yum_add_repo``

**Module frequency:** per always

**Supported distros:** fedora, rhel

**Config keys**::

    yum_repos:
        <repo-name>:
            baseurl: <repo url>
            name: <repo name>
            enabled: <true/false>
            # any repository configuration options (see man yum.conf)
"""

import os

import configobj
import six

from cloudinit import util

distros = ['fedora', 'rhel']


def _canonicalize_id(repo_id):
    repo_id = repo_id.lower().replace("-", "_")
    repo_id = repo_id.replace(" ", "_")
    return repo_id


def _format_repo_value(val):
    if isinstance(val, (bool)):
        # Seems like yum prefers 1/0
        return str(int(val))
    if isinstance(val, (list, tuple)):
        # Can handle 'lists' in certain cases
        # See: http://bit.ly/Qqrf1t
        return "\n    ".join([_format_repo_value(v) for v in val])
    if not isinstance(val, six.string_types):
        return str(val)
    return val


# TODO(harlowja): move to distro?
# See man yum.conf
def _format_repository_config(repo_id, repo_config):
    to_be = configobj.ConfigObj()
    to_be[repo_id] = {}
    # Do basic translation of the items -> values
    for (k, v) in repo_config.items():
        # For now assume that people using this know
        # the format of yum and don't verify keys/values further
        to_be[repo_id][k] = _format_repo_value(v)
    lines = to_be.write()
    lines.insert(0, "# Created by cloud-init on %s" % (util.time_rfc2822()))
    return "\n".join(lines)


def handle(name, cfg, _cloud, log, _args):
    repos = cfg.get('yum_repos')
    if not repos:
        log.debug(("Skipping module named %s,"
                   " no 'yum_repos' configuration found"), name)
        return
    repo_base_path = util.get_cfg_option_str(cfg, 'yum_repo_dir',
                                             '/etc/yum.repos.d/')
    repo_locations = {}
    repo_configs = {}
    for (repo_id, repo_config) in repos.items():
        canon_repo_id = _canonicalize_id(repo_id)
        repo_fn_pth = os.path.join(repo_base_path, "%s.repo" % (canon_repo_id))
        if os.path.exists(repo_fn_pth):
            log.info("Skipping repo %s, file %s already exists!",
                     repo_id, repo_fn_pth)
            continue
        elif canon_repo_id in repo_locations:
            log.info("Skipping repo %s, file %s already pending!",
                     repo_id, repo_fn_pth)
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
        for req_field in ['baseurl']:
            if req_field not in repo_config:
                log.warn(("Repository %s does not contain a %s"
                          " configuration 'required' entry"),
                         repo_id, req_field)
                missing_required += 1
        if not missing_required:
            repo_configs[canon_repo_id] = repo_config
            repo_locations[canon_repo_id] = repo_fn_pth
        else:
            log.warn("Repository %s is missing %s required fields, skipping!",
                     repo_id, missing_required)
    for (c_repo_id, path) in repo_locations.items():
        repo_blob = _format_repository_config(c_repo_id,
                                              repo_configs.get(c_repo_id))
        util.write_file(path, repo_blob)

# vi: ts=4 expandtab
