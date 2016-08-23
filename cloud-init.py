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

import subprocess
import sys

import cloudinit
import cloudinit.util as util
import cloudinit.CloudConfig as CC
import cloudinit.DataSource as ds
import cloudinit.netinfo as netinfo
import time
import traceback
import logging
import errno
import os


def warn(wstr):
    sys.stderr.write("WARN:%s" % wstr)


def main():
    util.close_stdin()

    cmds = ("start", "start-local")
    deps = {"start": (ds.DEP_FILESYSTEM, ds.DEP_NETWORK),
            "start-local": (ds.DEP_FILESYSTEM, )}

    cmd = ""
    if len(sys.argv) > 1:
        cmd = sys.argv[1]

    cfg_path = None
    if len(sys.argv) > 2:
        # this is really for debugging only
        # but you can invoke on development system with ./config/cloud.cfg
        cfg_path = sys.argv[2]

    if not cmd in cmds:
        sys.stderr.write("bad command %s. use one of %s\n" % (cmd, cmds))
        sys.exit(1)

    now = time.strftime("%a, %d %b %Y %H:%M:%S %z", time.gmtime())
    try:
        uptimef = open("/proc/uptime")
        uptime = uptimef.read().split(" ")[0]
        uptimef.close()
    except IOError as e:
        warn("unable to open /proc/uptime\n")
        uptime = "na"

    cmdline_msg = None
    cmdline_exc = None
    if cmd == "start":
        target = "%s.d/%s" % (cloudinit.system_config,
            "91_kernel_cmdline_url.cfg")
        if os.path.exists(target):
            cmdline_msg = "cmdline: %s existed" % target
        else:
            cmdline = util.get_cmdline()
            try:
                (key, url, content) = cloudinit.get_cmdline_url(
                    cmdline=cmdline)
                if key and content:
                    util.write_file(target, content, mode=0600)
                    cmdline_msg = ("cmdline: wrote %s from %s, %s" %
                        (target, key, url))
                elif key:
                    cmdline_msg = ("cmdline: %s, %s had no cloud-config" %
                        (key, url))
            except Exception:
                cmdline_exc = ("cmdline: '%s' raised exception\n%s" %
                    (cmdline, traceback.format_exc()))
                warn(cmdline_exc)

    try:
        cfg = cloudinit.get_base_cfg(cfg_path)
    except Exception as e:
        warn("Failed to get base config. falling back to builtin: %s\n" % e)
        try:
            cfg = cloudinit.get_builtin_cfg()
        except Exception as e:
            warn("Unable to load builtin config\n")
            raise

    try:
        (outfmt, errfmt) = CC.get_output_cfg(cfg, "init")
        CC.redirect_output(outfmt, errfmt)
    except Exception as e:
        warn("Failed to get and set output config: %s\n" % e)

    cloudinit.logging_set_from_cfg(cfg)
    log = logging.getLogger()

    if cmdline_exc:
        log.debug(cmdline_exc)
    elif cmdline_msg:
        log.debug(cmdline_msg)

    try:
        cloudinit.initfs()
    except Exception as e:
        warn("failed to initfs, likely bad things to come: %s\n" % str(e))

    nonet_path = "%s/%s" % (cloudinit.get_cpath("data"), "no-net")

    if cmd == "start":
        print netinfo.debug_info()

        stop_files = (cloudinit.get_ipath_cur("obj_pkl"), nonet_path)
        # if starting as the network start, there are cases
        # where everything is already done for us, and it makes
        # most sense to exit early and silently
        for f in stop_files:
            try:
                fp = open(f, "r")
                fp.close()
            except:
                continue

            log.debug("no need for cloud-init start to run (%s)\n", f)
            sys.exit(0)
    elif cmd == "start-local":
        # cache is not instance specific, so it has to be purged
        # but we want 'start' to benefit from a cache if
        # a previous start-local populated one
        manclean = util.get_cfg_option_bool(cfg, 'manual_cache_clean', False)
        if manclean:
            log.debug("not purging cache, manual_cache_clean = True")
        cloudinit.purge_cache(not manclean)

        try:
            os.unlink(nonet_path)
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise

    msg = "cloud-init %s running: %s. up %s seconds" % (cmd, now, uptime)
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()

    log.info(msg)

    cloud = cloudinit.CloudInit(ds_deps=deps[cmd])

    try:
        cloud.get_data_source()
    except cloudinit.DataSourceNotFoundException as e:
        sys.stderr.write("no instance data found in %s\n" % cmd)
        sys.exit(0)

    # set this as the current instance
    cloud.set_cur_instance()

    # store the metadata
    cloud.update_cache()

    msg = "found data source: %s" % cloud.datasource
    sys.stderr.write(msg + "\n")
    log.debug(msg)

    # parse the user data (ec2-run-userdata.py)
    try:
        ran = cloud.sem_and_run("consume_userdata", cloudinit.per_instance,
            cloud.consume_userdata, [cloudinit.per_instance], False)
        if not ran:
            cloud.consume_userdata(cloudinit.per_always)
    except:
        warn("consuming user data failed!\n")
        raise

    cfg_path = cloudinit.get_ipath_cur("cloud_config")
    cc = CC.CloudConfig(cfg_path, cloud)

    # if the output config changed, update output and err
    try:
        outfmt_orig = outfmt
        errfmt_orig = errfmt
        (outfmt, errfmt) = CC.get_output_cfg(cc.cfg, "init")
        if outfmt_orig != outfmt or errfmt_orig != errfmt:
            warn("stdout, stderr changing to (%s,%s)" % (outfmt, errfmt))
            CC.redirect_output(outfmt, errfmt)
    except Exception as e:
        warn("Failed to get and set output config: %s\n" % e)

    # send the cloud-config ready event
    cc_path = cloudinit.get_ipath_cur('cloud_config')
    cc_ready = cc.cfg.get("cc_ready_cmd",
        ['initctl', 'emit', 'cloud-config',
         '%s=%s' % (cloudinit.cfg_env_name, cc_path)])
    if cc_ready:
        if isinstance(cc_ready, str):
            cc_ready = ['sh', '-c', cc_ready]
        subprocess.Popen(cc_ready).communicate()

    module_list = CC.read_cc_modules(cc.cfg, "cloud_init_modules")

    failures = []
    if len(module_list):
        failures = CC.run_cc_modules(cc, module_list, log)
    else:
        msg = "no cloud_init_modules to run"
        sys.stderr.write(msg + "\n")
        log.debug(msg)
        sys.exit(0)

    sys.exit(len(failures))

if __name__ == '__main__':
    main()
