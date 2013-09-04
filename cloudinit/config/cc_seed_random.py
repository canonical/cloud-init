# vi: ts=4 expandtab
#
#    Copyright (C) 2013 Yahoo! Inc.
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

from cloudinit.settings import PER_INSTANCE

frequency = PER_INSTANCE


def handle(name, cfg, cloud, log, _args):
    random_seed = None
    # Prefer metadata over cfg for random_seed
    for src in (cloud.datasource.metadata, cfg):
        if not src:
            continue
        tmp_random_seed = src.get('random_seed')
        if tmp_random_seed and isinstance(tmp_random_seed, (str, basestring)):
            random_seed = tmp_random_seed
            break
    if random_seed:
        log.debug("%s: setting random seed", name)
        cloud.distro.set_random_seed(random_seed)
