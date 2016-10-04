# vi: ts=4 expandtab
#
#    Copyright (C) 2009-2011 Canonical Ltd.
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
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
Emit Upstart
------------
**Summary:** emit upstart configuration

Emit upstart configuration for cloud-init modules on upstart based systems. No
user configuration should be required.

**Internal name:** ``cc_emit_upstart``

**Module frequency:** per always

**Supported distros:** ubuntu, debian
"""

import os

from cloudinit import log as logging
from cloudinit.settings import PER_ALWAYS
from cloudinit import util

frequency = PER_ALWAYS

distros = ['ubuntu', 'debian']
LOG = logging.getLogger(__name__)


def is_upstart_system():
    if not os.path.isfile("/sbin/initctl"):
        LOG.debug("no /sbin/initctl located")
        return False

    myenv = os.environ.copy()
    if 'UPSTART_SESSION' in myenv:
        del myenv['UPSTART_SESSION']
    check_cmd = ['initctl', 'version']
    try:
        (out, err) = util.subp(check_cmd, env=myenv)
        return 'upstart' in out
    except util.ProcessExecutionError as e:
        LOG.debug("'%s' returned '%s', not using upstart",
                  ' '.join(check_cmd), e.exit_code)
    return False


def handle(name, _cfg, cloud, log, args):
    event_names = args
    if not event_names:
        # Default to the 'cloud-config'
        # event for backwards compat.
        event_names = ['cloud-config']

    if not is_upstart_system():
        log.debug("not upstart system, '%s' disabled", name)
        return

    cfgpath = cloud.paths.get_ipath_cur("cloud_config")
    for n in event_names:
        cmd = ['initctl', 'emit', str(n), 'CLOUD_CFG=%s' % cfgpath]
        try:
            util.subp(cmd)
        except Exception as e:
            # TODO(harlowja), use log exception from utils??
            log.warn("Emission of upstart event %s failed due to: %s", n, e)
