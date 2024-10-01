# Copyright (C) 2011 Canonical Ltd.
#
# Author: Scott Moser <scott.moser@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Power State Change: Change power state"""

import errno
import logging
import os
import re
import subprocess
import time

from cloudinit import subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.distros import ALL_DISTROS
from cloudinit.settings import PER_INSTANCE

frequency = PER_INSTANCE

EXIT_FAIL = 254

meta: MetaSchema = {
    "id": "cc_power_state_change",
    "distros": [ALL_DISTROS],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": ["power_state"],
}  # type: ignore

LOG = logging.getLogger(__name__)


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
            return util.load_text_file("/proc/%s/cmdline" % pid)
    except IOError:
        return None


def check_condition(cond):
    if isinstance(cond, bool):
        LOG.debug("Static Condition: %s", cond)
        return cond

    pre = "check_condition command (%s): " % cond
    try:
        proc = subprocess.Popen(cond, shell=not isinstance(cond, list))
        proc.communicate()
        ret = proc.returncode
        if ret == 0:
            LOG.debug("%sexited 0. condition met.", pre)
            return True
        elif ret == 1:
            LOG.debug("%sexited 1. condition not met.", pre)
            return False
        else:
            LOG.warning("%sunexpected exit %s. do not apply change.", pre, ret)
            return False
    except Exception as e:
        LOG.warning("%sUnexpected error: %s", pre, e)
        return False


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    try:
        (arg_list, timeout, condition) = load_power_state(cfg, cloud.distro)
        if arg_list is None:
            LOG.debug("no power_state provided. doing nothing")
            return
    except Exception as e:
        LOG.warning("%s Not performing power state change!", str(e))
        return

    if condition is False:
        LOG.debug("Condition was false. Will not perform state change.")
        return

    mypid = os.getpid()

    cmdline = givecmdline(mypid)
    if not cmdline:
        LOG.warning("power_state: failed to get cmdline of current process")
        return

    devnull_fp = open(os.devnull, "w")

    LOG.debug("After pid %s ends, will execute: %s", mypid, " ".join(arg_list))

    util.fork_cb(
        run_after_pid_gone,
        mypid,
        cmdline,
        timeout,
        condition,
        execmd,
        [arg_list, devnull_fp],
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
        proc = subprocess.Popen(  # nosec B603
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


def run_after_pid_gone(pid, pidcmdline, timeout, condition, func, args):
    # wait until pid, with /proc/pid/cmdline contents of pidcmdline
    # is no longer alive.  After it is gone, or timeout has passed
    # execute func(args)
    msg = None
    end_time = time.monotonic() + timeout

    def fatal(msg):
        LOG.warning(msg)
        doexit(EXIT_FAIL)

    known_errnos = (errno.ENOENT, errno.ESRCH)

    while True:
        if time.monotonic() > end_time:
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

    LOG.debug(msg)

    try:
        if not check_condition(condition):
            return
    except Exception as e:
        fatal("Unexpected Exception when checking condition: %s" % e)

    func(*args)
