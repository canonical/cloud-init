# vi: ts=4 expandtab
#
#    Copyright (C) 2011 Canonical Ltd.
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
from cloudinit import util

import errno
import os
import re
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


def handle(_name, cfg, _cloud, log, _args):

    try:
        (args, timeout) = load_power_state(cfg)
        if args is None:
            log.debug("no power_state provided. doing nothing")
            return
    except Exception as e:
        log.warn("%s Not performing power state change!" % str(e))
        return

    mypid = os.getpid()

    cmdline = givecmdline(mypid)
    if not cmdline:
        log.warn("power_state: failed to get cmdline of current process")
        return

    devnull_fp = open(os.devnull, "w")

    log.debug("After pid %s ends, will execute: %s" % (mypid, ' '.join(args)))

    util.fork_cb(run_after_pid_gone, mypid, cmdline, timeout, log, execmd,
                 [args, devnull_fp])


def load_power_state(cfg):
    # returns a tuple of shutdown_command, timeout
    # shutdown_command is None if no config found
    pstate = cfg.get('power_state')

    if pstate is None:
        return (None, None)

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

    return (args, timeout)


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


def run_after_pid_gone(pid, pidcmdline, timeout, log, func, args):
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
    func(*args)
