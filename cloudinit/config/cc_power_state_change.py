# Copyright (C) 2011 Canonical Ltd.
#
# Author: Scott Moser <scott.moser@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""
Power State Change
------------------
**Summary:** change power state

This module handles shutdown/reboot after all config modules have been run. By
default it will take no action, and the system will keep running unless a
package installation/upgrade requires a system reboot (e.g. installing a new
kernel) and ``package_reboot_if_required`` is true. The ``power_state`` config
key accepts a dict of options. If ``mode`` is any value other than
``poweroff``, ``halt``, or ``reboot``, then no action will be taken.

The system
can be shutdown before cloud-init has finished using the ``timeout`` option.
The ``delay`` key specifies a duration to be added onto any shutdown command
used. Therefore, if a 5 minute delay and a 120 second shutdown are specified,
the maximum amount of time between cloud-init starting and the system shutting
down is 7 minutes, and the minimum amount of time is 5 minutes. The ``delay``
key must have an argument in a form that the ``shutdown`` utility recognizes.
The most common format is the form ``+5`` for 5 minutes. See ``man shutdown``
for more options.

Optionally, a command can be run to determine whether or not
the system should shut down. The command to be run should be specified in the
``condition`` key. For command formatting, see the documentation for
``cc_runcmd``. The specified shutdown behavior will only take place if the
``condition`` key is omitted or the command specified by the ``condition``
key returns 0.

**Internal name:** ``cc_power_state_change``

**Module frequency:** per instance

**Supported distros:** all

**Config keys**::

    power_state:
        delay: <now/'+minutes'>
        mode: <poweroff/halt/reboot>
        message: <shutdown message>
        timeout: <seconds>
        condition: <true/false/command>
"""

from cloudinit.settings import PER_INSTANCE
from cloudinit import util

import errno
import os
import re
import six
import subprocess
import time

frequency = PER_INSTANCE

EXIT_FAIL = 254


def givecmdline(pid):
    # Returns the cmdline for the given process id. In Linux we can use procfs
    # for this but on BSD there is /usr/bin/procstat.
    try:
        # Example output from procstat -c 1
        #   PID COMM             ARGS
        #     1 init             /bin/init --
        if util.system_info()["platform"].startswith('FreeBSD'):
            (output, _err) = util.subp(['procstat', '-c', str(pid)])
            line = output.splitlines()[1]
            m = re.search('\d+ (\w|\.|-)+\s+(/\w.+)', line)
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
                log.warn(pre + "unexpected exit %s. " % ret +
                         "do not apply change.")
            return False
    except Exception as e:
        if log:
            log.warn(pre + "Unexpected error: %s" % e)
        return False


def handle(_name, cfg, _cloud, log, _args):

    try:
        (args, timeout, condition) = load_power_state(cfg)
        if args is None:
            log.debug("no power_state provided. doing nothing")
            return
    except Exception as e:
        log.warn("%s Not performing power state change!" % str(e))
        return

    if condition is False:
        log.debug("Condition was false. Will not perform state change.")
        return

    mypid = os.getpid()

    cmdline = givecmdline(mypid)
    if not cmdline:
        log.warn("power_state: failed to get cmdline of current process")
        return

    devnull_fp = open(os.devnull, "w")

    log.debug("After pid %s ends, will execute: %s" % (mypid, ' '.join(args)))

    util.fork_cb(run_after_pid_gone, mypid, cmdline, timeout, log,
                 condition, execmd, [args, devnull_fp])


def load_power_state(cfg):
    # returns a tuple of shutdown_command, timeout
    # shutdown_command is None if no config found
    pstate = cfg.get('power_state')

    if pstate is None:
        return (None, None, None)

    if not isinstance(pstate, dict):
        raise TypeError("power_state is not a dict.")

    opt_map = {'halt': '-H', 'poweroff': '-P', 'reboot': '-r'}

    mode = pstate.get("mode")
    if mode not in opt_map:
        raise TypeError(
            "power_state[mode] required, must be one of: %s. found: '%s'." %
            (','.join(opt_map.keys()), mode))

    delay = pstate.get("delay", "now")
    # convert integer 30 or string '30' to '+30'
    try:
        delay = "+%s" % int(delay)
    except ValueError:
        pass

    if delay != "now" and not re.match(r"\+[0-9]+", delay):
        raise TypeError(
            "power_state[delay] must be 'now' or '+m' (minutes)."
            " found '%s'." % delay)

    args = ["shutdown", opt_map[mode], delay]
    if pstate.get("message"):
        args.append(pstate.get("message"))

    try:
        timeout = float(pstate.get('timeout', 30.0))
    except ValueError:
        raise ValueError("failed to convert timeout '%s' to float." %
                         pstate['timeout'])

    condition = pstate.get("condition", True)
    if not isinstance(condition, six.string_types + (list, bool)):
        raise TypeError("condition type %s invalid. must be list, bool, str")
    return (args, timeout, condition)


def doexit(sysexit):
    os._exit(sysexit)


def execmd(exe_args, output=None, data_in=None):
    try:
        proc = subprocess.Popen(exe_args, stdin=subprocess.PIPE,
                                stdout=output, stderr=subprocess.STDOUT)
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
            log.warn(msg)
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

        time.sleep(.25)

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
