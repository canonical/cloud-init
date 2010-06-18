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
import cloudinit.CloudConfig
import logging
import os

def Usage(out = sys.stdout):
    out.write("Usage: %s name\n" % sys.argv[0])
    
def main():
    # expect to be called with
    #   name [ args ]
    #   run the cloud-config job 'name' at with given args
    # or
    #   read cloud config jobs from config (builtin -> system)
    #   and run all in order

    if len(sys.argv) < 2:
        Usage(sys.stderr)
        sys.exit(1)

    name=sys.argv[1]
    run_args=sys.argv[2:]

    cloudinit.logging_set_from_cfg_file()
    log = logging.getLogger()
    log.info("cloud-init-cfg %s" % sys.argv[1:])

    cfg_path = cloudinit.cloud_config
    cfg_env_name = cloudinit.cfg_env_name
    if os.environ.has_key(cfg_env_name):
        cfg_path = os.environ[cfg_env_name]

    cc = cloudinit.CloudConfig.CloudConfig(cfg_path)

    module_list = [ ]
    if name == "all":
        # create 'module_list', an array of arrays
        # where array[0] = config
        #       array[1] = freq
        #       array[2:] = arguemnts
        if "cloud_config_modules" in cc.cfg:
            for item in cc.cfg["cloud_config_modules"]:
                if isinstance(item,str):
                    module_list.append((item,))
                elif isinstance(item,list):
                    module_list.append(item)
                else:
                    fail("Failed to parse cloud_config_modules",log)
        else:
            fail("No cloud_config_modules found in config",log)
    else:
        args = [ name, None ] + run_args
        module_list.append = ( args )

    failures = []
    for cfg_mod in module_list:
        name = cfg_mod[0]
        freq = None
        run_args = [ ]
        if len(cfg_mod) > 1:
            freq = cfg_mod[1]
        if len(cfg_mod) > 2:
            run_args = cfg_mod[2:]

        try:
            cc.handle(name, run_args, freq=freq)
        except:
            import traceback
            traceback.print_exc(file=sys.stderr)
            err("config handling of %s failed\n" % name,log)
            failures.append(name)
            sys.exit(len(failures))

    sys.exit(len(failures))

def err(msg,log=None):
    if log:
        log.error(msg)
    sys.stderr.write(msg + "\n")

def fail(msg,log=None):
    err(msg,log)
    sys.exit(1)

if __name__ == '__main__':
    main()
