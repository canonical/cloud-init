# vi: ts=4 expandtab
#
#    Copyright (C) 2014 Canonical Ltd.
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

from cloudinit.settings import PER_INSTANCE
from cloudinit import log as logging
from cloudinit import util
from cloudinit.distros import ubuntu

import os
import time

frequency = PER_INSTANCE
REBOOT_CMD = ["/sbin/reboot"]

DEFAULT_CONFIG = {
    'init_switch': {'target': None}
}

SWITCH_INIT = """
#!/bin/sh
# switch_init: [upstart | systemd]

is_systemd() {
   [ "$(dpkg-divert --listpackage /sbin/init)" = "systemd-sysv" ]
}
debug() { echo "$@" 1>&2; }
fail() { echo "$@" 1>&2; exit 1; }

if [ "$1" = "systemd" ]; then
   if is_systemd; then
      debug "already systemd, nothing to do"
   else
      [ -f /lib/systemd/systemd ] || fail "no systemd available";
      dpkg-divert --package systemd-sysv --divert /sbin/init.diverted \\
          --rename /sbin/init
   fi
   [ -f /sbin/init ] || ln /lib/systemd/systemd /sbin/init
elif [ "$1" = "upstart" ]; then
   if is_systemd; then
      rm -f /sbin/init
      dpkg-divert --package systemd-sysv --rename --remove /sbin/init
   else
      debug "already upstart, nothing to do."
   fi
else
  fail "Error. expect 'upstart' or 'systemd'"
fi
"""


def handle(name, cfg, cloud, log, _args):

    if not isinstance(cloud.distro, ubuntu.Distro):
        log.debug("%s: distro is '%s', not ubuntu. returning",
                  name, cloud.distro.__class__)
        return

    cfg = util.mergemanydict(cfg, DEFAULT_CONFIG)
    target = cfg['init_switch']['target']
    if not target:
        log.debug("%s: target=%s. nothing to do", name, target)
        return

    supported = ('upstart', 'systemd')
    if target not in supported:
        log.warn("%s: target set to %s, expected one of: %s",
                 name, target, str(supported))

    if os.path.exists("/run/systemd/systemd"):
        current = "systemd"
    else:
        current = "upstart"

    if current == target:
        log.debug("%s: current = target = %s. nothing to do", name, target)
        return

    try:
        util.subp(['sh', '-c', SWITCH_INIT, '--', target])
    except util.ProcessExecutionError as e:
        log.warn("%s: Failed to switch to init '%s'. %s", name, target, e)
        return

    try:
        log.warn("%s: rebooting from '%s' to '%s'", name, current, target)
        logging.flushLoggers(log)
        _fire_reboot(log, initial_sleep=4)
    except Exception as e:
        util.logexc(log, "Requested reboot did not happen!")
        raise


def _fire_reboot(log, wait_attempts=6, initial_sleep=1, backoff=2):
    util.subp(REBOOT_CMD)
    start = time.time()
    wait_time = initial_sleep
    for _i in range(0, wait_attempts):
        time.sleep(wait_time)
        wait_time *= backoff
        elapsed = time.time() - start
        log.debug("Rebooted, but still running after %s seconds", int(elapsed))
    # If we got here, not good
    elapsed = time.time() - start
    raise RuntimeError(("Reboot did not happen"
                        " after %s seconds!") % (int(elapsed)))
