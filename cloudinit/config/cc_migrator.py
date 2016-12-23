# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""
Migrator
--------
**Summary:** migrate old versions of cloud-init data to new

This module handles moving old versions of cloud-init data to newer ones.
Currently, it only handles renaming cloud-init's per-frequency semaphore files
to canonicalized name and renaming legacy semaphore names to newer ones. This
module is enabled by default, but can be disabled by specifying ``migrate:
false`` in config.

**Internal name:** ``cc_migrator``

**Module frequency:** per always

**Supported distros:** all

**Config keys**::

    migrate: <true/false>
"""

import os
import shutil

from cloudinit import helpers
from cloudinit import util

from cloudinit.settings import PER_ALWAYS

frequency = PER_ALWAYS


def _migrate_canon_sems(cloud):
    paths = (cloud.paths.get_ipath('sem'), cloud.paths.get_cpath('sem'))
    am_adjusted = 0
    for sem_path in paths:
        if not sem_path or not os.path.exists(sem_path):
            continue
        for p in os.listdir(sem_path):
            full_path = os.path.join(sem_path, p)
            if os.path.isfile(full_path):
                (name, ext) = os.path.splitext(p)
                canon_name = helpers.canon_sem_name(name)
                if canon_name != name:
                    new_path = os.path.join(sem_path, canon_name + ext)
                    shutil.move(full_path, new_path)
                    am_adjusted += 1
    return am_adjusted


def _migrate_legacy_sems(cloud, log):
    legacy_adjust = {
        'apt-update-upgrade': [
            'apt-configure',
            'package-update-upgrade-install',
        ],
    }
    paths = (cloud.paths.get_ipath('sem'), cloud.paths.get_cpath('sem'))
    for sem_path in paths:
        if not sem_path or not os.path.exists(sem_path):
            continue
        sem_helper = helpers.FileSemaphores(sem_path)
        for (mod_name, migrate_to) in legacy_adjust.items():
            possibles = [mod_name, helpers.canon_sem_name(mod_name)]
            old_exists = []
            for p in os.listdir(sem_path):
                (name, _ext) = os.path.splitext(p)
                if name in possibles and os.path.isfile(p):
                    old_exists.append(p)
            for p in old_exists:
                util.del_file(os.path.join(sem_path, p))
                (_name, freq) = os.path.splitext(p)
                for m in migrate_to:
                    log.debug("Migrating %s => %s with the same frequency",
                              p, m)
                    with sem_helper.lock(m, freq):
                        pass


def handle(name, cfg, cloud, log, _args):
    do_migrate = util.get_cfg_option_str(cfg, "migrate", True)
    if not util.translate_bool(do_migrate):
        log.debug("Skipping module named %s, migration disabled", name)
        return
    sems_moved = _migrate_canon_sems(cloud)
    log.debug("Migrated %s semaphore files to there canonicalized names",
              sems_moved)
    _migrate_legacy_sems(cloud, log)

# vi: ts=4 expandtab
