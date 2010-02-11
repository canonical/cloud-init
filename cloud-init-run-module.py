#!/usr/bin/python
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

    cloud = cloudinit.CloudInit()
    try:
        cloud.get_data_source()
    except Exception as e:
        print e
        sys.stderr.write("Failed to get instance data")
        sys.exit(1)

    if cloud.sem_has_run(semname,freq):
        sys.stderr.write("%s already ran %s\n" % (semname,freq))
        sys.exit(0)

    try:
        mod = __import__('cloudinit.' + modname)
        inst = getattr(mod,modname)
    except:
        sys.stderr.write("Failed to load module cloudinit.%s\n" % modname)
        sys.exit(1)

    import os

    cfg_path = None
    cfg_env_name = cloudinit.cfg_env_name
    if os.environ.has_key(cfg_env_name):
        cfg_path = os.environ[cfg_env_name]

    cloud.sem_and_run(semname, freq, inst.run, [run_args,cfg_path], False)

    sys.exit(0)

if __name__ == '__main__':
    main()
