# vi: ts=4 expandtab
#
#    Copyright (C) 2015 Canonical Ltd.
#
#    Author: Scott Moser <scott.moser@canonical.com>
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
Fan
---
**Summary:** configure ubuntu fan networking

This module installs, configures and starts the ubuntu fan network system. For
more information about Ubuntu Fan, see:
``https://wiki.ubuntu.com/FanNetworking``.

If cloud-init sees a ``fan`` entry in cloud-config it will:

    - write ``config_path`` with the contents of the ``config`` key
    - install the package ``ubuntu-fan`` if it is not installed
    - ensure the service is started (or restarted if was previously running)

**Internal name:** ``cc_fan``

**Module frequency:** per instance

**Supported distros:** ubuntu

**Config keys**::

    fan:
        config: |
            # fan 240
            10.0.0.0/8 eth0/16 dhcp
            10.0.0.0/8 eth1/16 dhcp off
            # fan 241
            241.0.0.0/8 eth0/16 dhcp
        config_path: /etc/network/fan
"""

from cloudinit import log as logging
from cloudinit.settings import PER_INSTANCE
from cloudinit import util

LOG = logging.getLogger(__name__)

frequency = PER_INSTANCE

BUILTIN_CFG = {
    'config': None,
    'config_path': '/etc/network/fan',
}


def stop_update_start(service, config_file, content, systemd=False):
    if systemd:
        cmds = {'stop': ['systemctl', 'stop', service],
                'start': ['systemctl', 'start', service],
                'enable': ['systemctl', 'enable', service]}
    else:
        cmds = {'stop': ['service', 'stop'],
                'start': ['service', 'start']}

    def run(cmd, msg):
        try:
            return util.subp(cmd, capture=True)
        except util.ProcessExecutionError as e:
            LOG.warn("failed: %s (%s): %s", service, cmd, e)
            return False

    stop_failed = not run(cmds['stop'], msg='stop %s' % service)
    if not content.endswith('\n'):
        content += '\n'
    util.write_file(config_file, content, omode="w")

    ret = run(cmds['start'], msg='start %s' % service)
    if ret and stop_failed:
        LOG.warn("success: %s started", service)

    if 'enable' in cmds:
        ret = run(cmds['enable'], msg='enable %s' % service)

    return ret


def handle(name, cfg, cloud, log, args):
    cfgin = cfg.get('fan')
    if not cfgin:
        cfgin = {}
    mycfg = util.mergemanydict([cfgin, BUILTIN_CFG])

    if not mycfg.get('config'):
        LOG.debug("%s: no 'fan' config entry. disabling", name)
        return

    util.write_file(mycfg.get('config_path'), mycfg.get('config'), omode="w")
    distro = cloud.distro
    if not util.which('fanctl'):
        distro.install_packages(['ubuntu-fan'])

    stop_update_start(
        service='ubuntu-fan', config_file=mycfg.get('config_path'),
        content=mycfg.get('config'), systemd=distro.uses_systemd())
