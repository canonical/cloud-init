# Copyright (C) 2011 Canonical Ltd.
#
# Author: Scott Moser <scott.moser@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Power State Change: Change power state"""

import errno
import os
import re
import subprocess
import time
from logging import Logger
from textwrap import dedent

from cloudinit import subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.distros import ALL_DISTROS
from cloudinit.settings import PER_INSTANCE

frequency = PER_INSTANCE

EXIT_FAIL = 254

MODULE_DESCRIPTION = """\
This module handles shutdown/reboot after all config modules have been run. By
default it will take no action, and the system will keep running unless a
package installation/upgrade requires a system reboot (e.g. installing a new
kernel) and ``package_reboot_if_required`` is true.

Using this module ensures that cloud-init is entirely finished with
modules that would be executed.

An example to distinguish delay from timeout:

If you delay 5 (5 minutes) and have a timeout of
120 (2 minutes), then the max time until shutdown will be 7 minutes, though
it could be as soon as 5 minutes. Cloud-init will invoke 'shutdown +5' after
the process finishes, or when 'timeout' seconds have elapsed.

.. note::
    With Alpine Linux any message value specified is ignored as Alpine's halt,
    poweroff, and reboot commands do not support broadcasting a message.

"""

meta: MetaSchema = {
    "id": "cc_power_state_change",
    "name": "Power State Change",
    "title": "Change power state",
    "description": MODULE_DESCRIPTION,
    "distros": [ALL_DISTROS],
    "frequency": PER_INSTANCE,
    "examples": [
        dedent(
            """\
            power_state:
                delay: now
                mode: poweroff
                message: Powering off
                timeout: 2
                condition: true
            """
        ),
        dedent(
            """\
            power_state:
                delay: 30
                mode: reboot
                message: Rebooting machine
                condition: test -f /var/tmp/reboot_me
            """
        ),
    ],
    "activate_by_schema_keys": ["power_state"],
}

__doc__ = get_meta_doc(meta)


def givecmdline(pid):
    # Returns the cmdline for the given process id. In Linux we can use procfs
    # for this but on BSD there is /usr/bin/procstat.
    try:
        # Example output from procstat -c 1
        #   PID COMM             ARGS
        #     1 init             /bin/init --
        if util.is_FreeBSD():
            (output, _err) = subp.subp(["procstat", "-c", str(pid)])
            line = output.splitlines()[1]
            m = re.search(r"\d+ (\w|\.|-)+\s+(/\w.+)", line)
            return m.group(2)
        else:
            return util.load_file("/proc/%s/cmdline" % pid)
    except IOError:
        return None


def check_condition(cond, log=None):
    if isinstance(cond, bool):
        if log:
            log.debug("Static Condition: %s" % cond)
        return cond

    pre = "check_condition command (%s): " % cond
    try:
        proc = subprocess.Popen(cond, shell=not isinstance(cond, list))
        proc.communicate()
        ret = proc.returncode
        if ret == 0:
            if log:
                log.debug(pre + "exited 0. condition met.")
            return True
        elif ret == 1:
            if log:
                log.debug(pre + "exited 1. condition not met.")
            return False
        else:
            if log:
                log.warning(
                    pre + "unexpected exit %s. " % ret + "do not apply change."
                )
            return False
    except Exception as e:
        if log:
            log.warning(pre + "Unexpected error: %s" % e)
        return False


def handle(
    name: str, cfg: Config, cloud: Cloud, log: Logger, args: list
) -> None:
    try:
        (args, timeout, condition) = load_power_state(cfg, cloud.distro)
        if args is None:
            log.debug("no power_state provided. doing nothing")
            return
    except Exception as e:
        log.warning("%s Not performing power state change!" % str(e))
        return

    if condition is False:
        log.debug("Condition was false. Will not perform state change.")
        return

    mypid = os.getpid()

    cmdline = givecmdline(mypid)
    if not cmdline:
        log.warning("power_state: failed to get cmdline of current process")
        return

    devnull_fp = open(os.devnull, "w")

    log.debug("After pid %s ends, will execute: %s" % (mypid, " ".join(args)))

    util.fork_cb(
        run_after_pid_gone,
        mypid,
        cmdline,
        timeout,
        log,
        condition,
        execmd,
        [args, devnull_fp],
    )


def load_power_state(cfg, distro):
    # returns a tuple of shutdown_command, timeout
    # shutdown_command is None if no config found
    pstate = cfg.get("power_state")

    if pstate is None:
        return (None, None, None)

    if not isinstance(pstate, dict):
        raise TypeError("power_state is not a dict.")

    modes_ok = ["halt", "poweroff", "reboot"]
    mode = pstate.get("mode")
    if mode not in distro.shutdown_options_map:
        raise TypeError(
            "power_state[mode] required, must be one of: %s. found: '%s'."
            % (",".join(modes_ok), mode)
        )

    args = distro.shutdown_command(
        mode=mode,
        delay=pstate.get("delay", "now"),
        message=pstate.get("message"),
    )

    try:
        timeout = float(pstate.get("timeout", 30.0))
    except ValueError as e:
        raise ValueError(
            "failed to convert timeout '%s' to float." % pstate["timeout"]
        ) from e

    condition = pstate.get("condition", True)
    if not isinstance(condition, (str, list, bool)):
        raise TypeError("condition type %s invalid. must be list, bool, str")
    return (args, timeout, condition)


def doexit(sysexit):
    os._exit(sysexit)


def execmd(exe_args, output=None, data_in=None):
    ret = 1
    try:
        proc = subprocess.Popen(
            exe_args,
            stdin=subprocess.PIPE,
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        proc.communicate(data_in)
        ret = proc.returncode
    except Exception:
        doexit(EXIT_FAIL)
    doexit(ret)


def run_after_pid_gone(pid, pidcmdline, timeout, log, condition, func, args):
    # wait until pid, with /proc/pid/cmdline contents of pidcmdline
    # is no longer alive.  After it is gone, or timeout has passed
    # execute func(args)
    msg = None
    end_time = time.time() + timeout

    def fatal(msg):
        if log:
            log.warning(msg)
        doexit(EXIT_FAIL)

    known_errnos = (errno.ENOENT, errno.ESRCH)

    while True:
        if time.time() > end_time:
            msg = "timeout reached before %s ended" % pid
            break

        try:
            cmdline = givecmdline(pid)
            if cmdline != pidcmdline:
                msg = "cmdline changed for %s [now: %s]" % (pid, cmdline)
                break

        except IOError as ioerr:
            if ioerr.errno in known_errnos:
                msg = "pidfile gone [%d]" % ioerr.errno
            else:
                fatal("IOError during wait: %s" % ioerr)
            break

        except Exception as e:
            fatal("Unexpected Exception: %s" % e)

        time.sleep(0.25)

    if not msg:
        fatal("Unexpected error in run_after_pid_gone")

    if log:
        log.debug(msg)

    try:
        if not check_condition(condition, log):
            return
    except Exception as e:
        fatal("Unexpected Exception when checking condition: %s" % e)

    func(*args)


# vi: ts=4 expandtab
