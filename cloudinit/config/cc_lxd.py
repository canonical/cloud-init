# vi: ts=4 expandtab
#
#    Copyright (C) 2016 Canonical Ltd.
#
#    Author: Wesley Wiedenmeier <wesley.wiedenmeier@canonical.com>
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

"""
This module initializes lxd using 'lxd init'

Example config:
  #cloud-config
  lxd:
    init:
      network_address: <ip addr>
      network_port: <port>
      storage_backend: <zfs/dir>
      storage_create_device: <dev>
      storage_create_loop: <size>
      storage_pool: <name>
      trust_password: <password>
"""

from cloudinit import util


def handle(name, cfg, cloud, log, args):
    if not cfg.get('lxd') and cfg['lxd'].get('init'):
        log.debug("Skipping module named %s, not present or disabled by cfg")
        return
    lxd_conf = cfg['lxd']['init']
    keys = ('network_address', 'network_port', 'storage_backend',
            'storage_create_device', 'storage_create_loop', 'storage_pool',
            'trust_password')
    cmd = ['lxd', 'init', '--auto']
    for k in keys:
        if lxd_conf.get(k):
            cmd.extend(["--%s" % k.replace('_', '-'), lxd_conf[k]])
    util.subp(cmd)
