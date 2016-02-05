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
    # Get config
    lxd_cfg = cfg.get('lxd')
    if not lxd_cfg and isinstance(lxd_cfg, dict):
        log.debug("Skipping module named %s, not present or disabled by cfg")
        return

    # Ensure lxd is installed
    if not util.which("lxd"):
        try:
            cloud.distro.install_packages(("lxd",))
        except util.ProcessExecutionError as e:
            log.warn("no lxd executable and could not install lxd: '%s'" % e)
            return

    # Set up lxd if init config is given
    init_cfg = lxd_cfg.get('init')
    if init_cfg:
        if not isinstance(init_cfg, dict):
            log.warn("lxd init config must be a dict of flag: val pairs")
            return
        init_keys = ('network_address', 'network_port', 'storage_backend',
                     'storage_create_device', 'storage_create_loop',
                     'storage_pool', 'trust_password')
        cmd = ['lxd', 'init', '--auto']
        for k in init_keys:
            if init_cfg.get(k):
                cmd.extend(["--%s" % k.replace('_', '-'), init_cfg[k]])
        util.subp(cmd)
