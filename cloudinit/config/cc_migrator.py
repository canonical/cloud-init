# vi: ts=4 expandtab
#
#    Copyright (C) 2012 Yahoo! Inc.
#
#    Author: Joshua Harlow <harlowja@yahoo-inc.com>
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
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

import os
import shutil

from cloudinit import helpers
from cloudinit import util

from cloudinit.settings import PER_ALWAYS

frequency = PER_ALWAYS


def _migrate_canon_sems(cloud):
    sem_path = cloud.paths.get_ipath('sem')
    if not sem_path or not os.path.exists(sem_path):
        return 0
    am_adjusted = 0
    for p in os.listdir(sem_path):
        full_path = os.path.join(sem_path, p)
        if os.path.isfile(full_path):
            canon_p = helpers.canon_sem_name(p)
            if canon_p != p:
                new_path = os.path.join(sem_path, p)
                shutil.move(full_path, new_path)
                am_adjusted += 1
    return am_adjusted


def handle(name, cfg, cloud, log, _args):
    do_migrate = util.get_cfg_option_str(cfg, "migrate", True)
    if not util.translate_bool(do_migrate):
        log.debug("Skipping module named %s, migration disabled", name)
        return
    sems_moved = _migrate_canon_sems(cloud)
    log.debug("Migrated %s semaphore files to there canonicalized names",
              sems_moved)
