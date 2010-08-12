#!/usr/bin/python
# vi: ts=4 expandtab
#
#    Copyright (C) 2009-2010 Canonical Ltd.
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

import sys
import cloudinit
import logging

def Usage(out = sys.stdout):
    out.write("Usage: cloud-init-run-module freq sem-name mod-name [args]\n")
    
def main():
    # expect to be called with
    #   <freq> <semaphore-name> <module-name> args
    if len(sys.argv) < 4:
        Usage(sys.stderr)
        sys.exit(1)

    (freq,semname,modname)=sys.argv[1:4]
    run_args=sys.argv[4:]

    cloudinit.logging_set_from_cfg_file()
    log = logging.getLogger()
    log.info("cloud-init-run-module %s" % sys.argv[1:])
    cloud = cloudinit.CloudInit()
    try:
        cloud.get_data_source()
    except Exception as e:
        fail("Failed to get instance data\n\t%s" % traceback.format_exc(),log)

    if cloud.sem_has_run(semname,freq):
        msg="%s already ran %s" % (semname,freq)
        sys.stderr.write("%s\n" % msg)
        log.debug(msg)
        sys.exit(0)

    try:
        mod = __import__('cloudinit.' + modname)
        inst = getattr(mod,modname)
    except:
        fail("Failed to load module cloudinit.%s\n" % modname)

    import os

    cfg_path = None
    cfg_env_name = cloudinit.cfg_env_name
    if os.environ.has_key(cfg_env_name):
        cfg_path = os.environ[cfg_env_name]

    try:
        cloud.sem_and_run(semname, freq, inst.run, [run_args,cfg_path,log], False)
    except Exception as e:
        fail("Execution of %s failed:%s" % (semname,e), log)

    sys.exit(0)

def err(msg,log=None):
    if log:
        log.error(msg)
    sys.stderr.write(msg + "\n")

def fail(msg,log=None):
    err(msg,log)
    sys.exit(1)

if __name__ == '__main__':
    main()
