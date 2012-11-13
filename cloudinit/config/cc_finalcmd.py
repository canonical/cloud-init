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
import subprocess
import sys
import time

frequency = PER_INSTANCE


def handle(_name, cfg, _cloud, log, _args):

    finalcmds = cfg.get("finalcmd")

    if not finalcmds:
        log.debug("No final commands")
        return

    mypid = os.getpid()
    cmdline = util.load_file("/proc/%s/cmdline")

    if not cmdline:
        log.warn("Failed to get cmdline of current process")
        return

    try:
        timeout = float(cfg.get("finalcmd_timeout", 30.0))
    except ValueError:
        log.warn("failed to convert finalcmd_timeout '%s' to float" %
                 cfg.get("finalcmd_timeout", 30.0))
        return

    devnull_fp = open("/dev/null", "w")

    shellcode = util.shellify(finalcmds)

    # note, after the fork, we do not use any of cloud-init's functions
    # that would attempt to log.  The primary reason for that is
    # to allow the 'finalcmd' the ability to do just about anything
    # and not depend on syslog services.
    # Basically, it should "just work" to have finalcmd of:
    #  - sleep 30
    #  - /sbin/poweroff
    finalcmd_d = os.path.join(cloud.get_ipath_cur(), "finalcmds")

    util.fork_cb(run_after_pid_gone, mypid, cmdline, timeout,
                 runfinal, (shellcode, finalcmd_d, devnull_fp))


def execmd(exe_args, data_in=None, output=None):
    try:
        proc = subprocess.Popen(exe_args, stdin=subprocess.PIPE,
                                stdout=output, stderr=subprocess.STDERR)
        proc.communicate(data_in)
    except Exception as e:
        return 254
    return proc.returncode()


def runfinal(shellcode, finalcmd_d, output=None):
    ret = execmd(("/bin/sh",), data_in=shellcode, output=output)
    if not (finalcmd_d and os.path.isdir(finalcmd_d)):
        sys.exit(ret)

    fails = 0
    if ret != 0:
        fails = 1

    # now runparts the final command dir
    for exe_name in sorted(os.listdir(finalcmd_d)):
        exe_path = os.path.join(finalcmd_d, exe_name)
        if os.path.isfile(exe_path) and os.access(exe_path, os.X_OK):
            ret = execmd(exe_path, data_in=None, output=output)
            if ret != 0:
                fails += 1
    sys.exit(fails)


def run_after_pid_gone(pid, pidcmdline, timeout, func, args):
    # wait until pid, with /proc/pid/cmdline contents of pidcmdline
    # is no longer alive.  After it is gone, or timeout has passed
    # execute func(args)
    msg = "ERROR: Uncaught error"
    end_time = time.time() + timeout

    cmdline_f = "/proc/%s/cmdline" % pid

    while True:
        if time.time() > end_time:
            msg = "timeout reached before %s ended" % pid
            break

        try:
            cmdline = ""
            with open(cmdline_f) as fp:
                cmdline = fp.read()
            if cmdline != pidcmdline:
                msg = "cmdline changed for %s [now: %s]" % (pid, cmdline)
                break

        except IOError as ioerr:
            if ioerr.errno == errno.ENOENT:
                msg = "pidfile '%s' gone" % cmdline_f
            else:
                msg = "ERROR: IOError: %s" % ioerr
                raise
            break

        except Exception as e:
            msg = "ERROR: Exception: %s" % e
            raise

    if msg.startswith("ERROR:"):
        sys.stderr.write(msg)
        sys.stderr.write("Not executing finalcmd")
        sys.exit(1)

    sys.stderr.write("calling %s with %s\n" % (func, args))
    sys.exit(func(*args))
