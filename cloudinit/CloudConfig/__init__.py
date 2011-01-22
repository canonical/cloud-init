# vi: ts=4 expandtab
#
#    Copyright (C) 2008-2010 Canonical Ltd.
#
#    Author: Chuck Short <chuck.short@canonical.com>
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

per_instance="once-per-instance"
per_always="always"

class CloudConfig():
    cfgfile = None
    cfg = None

    def __init__(self,cfgfile, cloud=None):
        if cloud == None:
            self.cloud = cloudinit.CloudInit()
        else:
            self.cloud = cloud
        self.cfg = self.get_config_obj(cfgfile)
        self.cloud.get_data_source()

    def get_config_obj(self,cfgfile):
        try:
            cfg = util.read_conf(cfgfile)
        except:
            # TODO: this 'log' could/should be passed in
            cloudinit.log.critical("Failed loading of cloud config '%s'. Continuing with empty config\n" % cfgfile)
            cloudinit.log.debug(traceback.format_exc() + "\n")
            cfg = None
        if cfg is None: cfg = { }
        return(util.mergedict(cfg,self.cloud.cfg))

    def handle(self, name, args, freq=None):
        try:
            mod = __import__("cc_" + name.replace("-","_"),globals())
            def_freq = getattr(mod, "frequency",per_instance)
            handler = getattr(mod, "handle")

            if not freq:
                freq = def_freq

            self.cloud.sem_and_run("config-" + name, freq, handler,
                [ name, self.cfg, self.cloud, cloudinit.log, args ])
        except:
            raise

# reads a cloudconfig module list, returns
# a 2 dimensional array suitable to pass to run_cc_modules
def read_cc_modules(cfg,name):
    if name not in cfg: return([])
    module_list = []
    # create 'module_list', an array of arrays
    # where array[0] = config
    #       array[1] = freq
    #       array[2:] = arguemnts
    for item in cfg[name]:
        if isinstance(item,str):
            module_list.append((item,))
        elif isinstance(item,list):
            module_list.append(item)
        else:
            raise TypeError("failed to read '%s' item in config")
    return(module_list)
    
def run_cc_modules(cc,module_list,log):
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
            log.debug("handling %s with freq=%s and args=%s" %
                (name, freq, run_args ))
            cc.handle(name, run_args, freq=freq)
        except:
            log.warn(traceback.format_exc())
            log.err("config handling of %s, %s, %s failed\n" %
                (name,freq,run_args))
            failures.append(name)

    return(failures)
