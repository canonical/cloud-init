# vi: ts=4 expandtab
#
#    Copyright (C) 2008-2010 Canonical Ltd.
#    Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
#    Author: Chuck Short <chuck.short@canonical.com>
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
#

import yaml
import cloudinit
import cloudinit.util as util
import sys
import traceback
import os
import subprocess
import time

per_instance = cloudinit.per_instance
per_always = cloudinit.per_always
per_once = cloudinit.per_once


class CloudConfig():
    cfgfile = None
    cfg = None

    def __init__(self, cfgfile, cloud=None, ds_deps=None):
        if cloud == None:
            self.cloud = cloudinit.CloudInit(ds_deps)
            self.cloud.get_data_source()
        else:
            self.cloud = cloud
        self.cfg = self.get_config_obj(cfgfile)

    def get_config_obj(self, cfgfile):
        try:
            cfg = util.read_conf(cfgfile)
        except:
            # TODO: this 'log' could/should be passed in
            cloudinit.log.critical("Failed loading of cloud config '%s'. "
                                   "Continuing with empty config\n" % cfgfile)
            cloudinit.log.debug(traceback.format_exc() + "\n")
            cfg = None
        if cfg is None:
            cfg = {}

        try:
            ds_cfg = self.cloud.datasource.get_config_obj()
        except:
            ds_cfg = {}

        cfg = util.mergedict(cfg, ds_cfg)
        return(util.mergedict(cfg, self.cloud.cfg))

    def handle(self, name, args, freq=None):
        try:
            mod = __import__("cc_" + name.replace("-", "_"), globals())
            def_freq = getattr(mod, "frequency", per_instance)
            handler = getattr(mod, "handle")

            if not freq:
                freq = def_freq

            self.cloud.sem_and_run("config-" + name, freq, handler,
                [name, self.cfg, self.cloud, cloudinit.log, args])
        except:
            raise


# reads a cloudconfig module list, returns
# a 2 dimensional array suitable to pass to run_cc_modules
def read_cc_modules(cfg, name):
    if name not in cfg:
        return([])
    module_list = []
    # create 'module_list', an array of arrays
    # where array[0] = config
    #       array[1] = freq
    #       array[2:] = arguemnts
    for item in cfg[name]:
        if isinstance(item, str):
            module_list.append((item,))
        elif isinstance(item, list):
            module_list.append(item)
        else:
            raise TypeError("failed to read '%s' item in config")
    return(module_list)


def run_cc_modules(cc, module_list, log):
    failures = []
    for cfg_mod in module_list:
        name = cfg_mod[0]
        freq = None
        run_args = []
        if len(cfg_mod) > 1:
            freq = cfg_mod[1]
        if len(cfg_mod) > 2:
            run_args = cfg_mod[2:]

        try:
            log.debug("handling %s with freq=%s and args=%s" %
                (name, freq, run_args))
            cc.handle(name, run_args, freq=freq)
        except:
            log.warn(traceback.format_exc())
            log.error("config handling of %s, %s, %s failed\n" %
                (name, freq, run_args))
            failures.append(name)

    return(failures)


# always returns well formated values
# cfg is expected to have an entry 'output' in it, which is a dictionary
# that includes entries for 'init', 'config', 'final' or 'all'
#   init: /var/log/cloud.out
#   config: [ ">> /var/log/cloud-config.out", /var/log/cloud-config.err ]
#   final:
#     output: "| logger -p"
#     error: "> /dev/null"
# this returns the specific 'mode' entry, cleanly formatted, with value
# None if if none is given
def get_output_cfg(cfg, mode="init"):
    ret = [None, None]
    if not 'output' in cfg:
        return ret

    outcfg = cfg['output']
    if mode in outcfg:
        modecfg = outcfg[mode]
    else:
        if 'all' not in outcfg:
            return ret
        # if there is a 'all' item in the output list
        # then it applies to all users of this (init, config, final)
        modecfg = outcfg['all']

    # if value is a string, it specifies stdout and stderr
    if isinstance(modecfg, str):
        ret = [modecfg, modecfg]

    # if its a list, then we expect (stdout, stderr)
    if isinstance(modecfg, list):
        if len(modecfg) > 0:
            ret[0] = modecfg[0]
        if len(modecfg) > 1:
            ret[1] = modecfg[1]

    # if it is a dictionary, expect 'out' and 'error'
    # items, which indicate out and error
    if isinstance(modecfg, dict):
        if 'output' in modecfg:
            ret[0] = modecfg['output']
        if 'error' in modecfg:
            ret[1] = modecfg['error']

    # if err's entry == "&1", then make it same as stdout
    # as in shell syntax of "echo foo >/dev/null 2>&1"
    if ret[1] == "&1":
        ret[1] = ret[0]

    swlist = [">>", ">", "|"]
    for i in range(len(ret)):
        if not ret[i]:
            continue
        val = ret[i].lstrip()
        found = False
        for s in swlist:
            if val.startswith(s):
                val = "%s %s" % (s, val[len(s):].strip())
                found = True
                break
        if not found:
            # default behavior is append
            val = "%s %s" % (">>", val.strip())
        ret[i] = val

    return(ret)


# redirect_output(outfmt, errfmt, orig_out, orig_err)
#  replace orig_out and orig_err with filehandles specified in outfmt or errfmt
#  fmt can be:
#   > FILEPATH
#   >> FILEPATH
#   | program [ arg1 [ arg2 [ ... ] ] ]
#
#   with a '|', arguments are passed to shell, so one level of
#   shell escape is required.
def redirect_output(outfmt, errfmt, o_out=sys.stdout, o_err=sys.stderr):
    if outfmt:
        (mode, arg) = outfmt.split(" ", 1)
        if mode == ">" or mode == ">>":
            owith = "ab"
            if mode == ">":
                owith = "wb"
            new_fp = open(arg, owith)
        elif mode == "|":
            proc = subprocess.Popen(arg, shell=True, stdin=subprocess.PIPE)
            new_fp = proc.stdin
        else:
            raise TypeError("invalid type for outfmt: %s" % outfmt)

        if o_out:
            os.dup2(new_fp.fileno(), o_out.fileno())
        if errfmt == outfmt:
            os.dup2(new_fp.fileno(), o_err.fileno())
            return

    if errfmt:
        (mode, arg) = errfmt.split(" ", 1)
        if mode == ">" or mode == ">>":
            owith = "ab"
            if mode == ">":
                owith = "wb"
            new_fp = open(arg, owith)
        elif mode == "|":
            proc = subprocess.Popen(arg, shell=True, stdin=subprocess.PIPE)
            new_fp = proc.stdin
        else:
            raise TypeError("invalid type for outfmt: %s" % outfmt)

        if o_err:
            os.dup2(new_fp.fileno(), o_err.fileno())
    return


def run_per_instance(name, func, args, clear_on_fail=False):
    semfile = "%s/%s" % (cloudinit.get_ipath_cur("data"), name)
    if os.path.exists(semfile):
        return

    util.write_file(semfile, str(time.time()))
    try:
        func(*args)
    except:
        if clear_on_fail:
            os.unlink(semfile)
        raise


# apt_get top level command (install, update...), and args to pass it
def apt_get(tlc, args=None):
    if args is None:
        args = []
    e = os.environ.copy()
    e['DEBIAN_FRONTEND'] = 'noninteractive'
    cmd = ['apt-get', '--option', 'Dpkg::Options::=--force-confold',
           '--assume-yes', tlc]
    cmd.extend(args)
    subprocess.check_call(cmd, env=e)


def update_package_sources():
    run_per_instance("update-sources", apt_get, ("update",))


def install_packages(pkglist):
    update_package_sources()
    apt_get("install", pkglist)
