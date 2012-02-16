#!/usr/bin/python
# vi: ts=4 expandtab
#
#    Copyright (C) 2009-2010 Canonical Ltd.
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

import sys
import cloudinit
import cloudinit.util as util
import cloudinit.CloudConfig as CC
import logging
import os


def Usage(out=sys.stdout):
    out.write("Usage: %s name\n" % sys.argv[0])


def main():
    # expect to be called with
    #   name [ freq [ args ]
    #   run the cloud-config job 'name' at with given args
    # or
    #   read cloud config jobs from config (builtin -> system)
    #   and run all in order

    util.close_stdin()

    modename = "config"

    if len(sys.argv) < 2:
        Usage(sys.stderr)
        sys.exit(1)
    if sys.argv[1] == "all":
        name = "all"
        if len(sys.argv) > 2:
            modename = sys.argv[2]
    else:
        freq = None
        run_args = []
        name = sys.argv[1]
        if len(sys.argv) > 2:
            freq = sys.argv[2]
            if freq == "None":
                freq = None
        if len(sys.argv) > 3:
            run_args = sys.argv[3:]

    cfg_path = cloudinit.get_ipath_cur("cloud_config")
    cfg_env_name = cloudinit.cfg_env_name
    if cfg_env_name in os.environ:
        cfg_path = os.environ[cfg_env_name]

    cloud = cloudinit.CloudInit(ds_deps=[])  # ds_deps=[], get only cached
    try:
        cloud.get_data_source()
    except cloudinit.DataSourceNotFoundException as e:
        # there was no datasource found, theres nothing to do
        sys.exit(0)

    cc = CC.CloudConfig(cfg_path, cloud)

    try:
        (outfmt, errfmt) = CC.get_output_cfg(cc.cfg, modename)
        CC.redirect_output(outfmt, errfmt)
    except Exception as e:
        err("Failed to get and set output config: %s\n" % e)

    cloudinit.logging_set_from_cfg(cc.cfg)
    log = logging.getLogger()
    log.info("cloud-init-cfg %s" % sys.argv[1:])

    module_list = []
    if name == "all":
        modlist_cfg_name = "cloud_%s_modules" % modename
        module_list = CC.read_cc_modules(cc.cfg, modlist_cfg_name)
        if not len(module_list):
            err("no modules to run in cloud_config [%s]" % modename, log)
            sys.exit(0)
    else:
        module_list.append([name, freq] + run_args)

    failures = CC.run_cc_modules(cc, module_list, log)
    if len(failures):
        err("errors running cloud_config [%s]: %s" % (modename, failures), log)
    sys.exit(len(failures))


def err(msg, log=None):
    if log:
        log.error(msg)
    sys.stderr.write(msg + "\n")


def fail(msg, log=None):
    err(msg, log)
    sys.exit(1)

if __name__ == '__main__':
    main()
