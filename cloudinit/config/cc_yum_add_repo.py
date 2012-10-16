# vi: ts=4 expandtab
#
#    Copyright (C) 2011 Canonical Ltd.
#    Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
#    Author: Scott Moser <scott.moser@canonical.com>
#    Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License version 3, as
#    published by the Free Software Foundation.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this 

import os

from cloudinit import util

import configobj


def _canonicalize_id(repo_id):
    repo_id = repo_id.lower().replace("-", "_")
    repo_id = repo_id.replace(" ", "_")
    return repo_id


## TODO(harlowja): move to distro?
# See man yum.conf
def _format_repository_config(repo_id, repo_config):
    to_be = configobj.ConfigObj()
    to_be[repo_id] = {}
    # Do basic translation of 
    for (k, v) in repo_config.items():
        if isinstance(v, bool):
            if v:
                v = '1'
            else:
                v = '0'
        elif isinstance(v, (tuple, list)):
            v = "\n    ".join(v)
        # For now assume that peopel using this know
        # the format of yum and don't verify further
        to_be[repo_id][k] = v
    lines = to_be.write()
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
        if not 'baseurl' in repo_config:
            log.warn("Repository %s does not contain a baseurl address",
                     repo_id)
        else:
            repo_configs[canon_repo_id] = repo_config
            repo_locations[canon_repo_id] = repo_fn_pth
    for (c_repo_id, path) in repo_locations.items():
        repo_blob = _format_repository_config(c_repo_id,
                                              repo_configs.get(c_repo_id))
        util.write_file(path, repo_blob)
