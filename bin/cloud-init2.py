#!/usr/bin/python
# vi: ts=4 expandtab
#
#    Copyright (C) 2012 Canonical Ltd.
#    Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#    Copyright (C) 2012 Yahoo! Inc.
#
#    Author: Scott Moser <scott.moser@canonical.com>
#    Author: Juerg Haefliger <juerg.haefliger@hp.com>
#    Author: Joshua Harlow <harlowja@yahoo-inc.com>
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

import argparse
import os
import traceback
import sys

# This is more just for running from the bin folder
possible_topdir = os.path.normpath(os.path.join(os.path.abspath(
        sys.argv[0]), os.pardir, os.pardir))
if os.path.exists(os.path.join(possible_topdir, "cloudinit", "__init__.py")):
    sys.path.insert(0, possible_topdir)

from cloudinit import log as logging
from cloudinit import netinfo
from cloudinit import settings
from cloudinit import sources
from cloudinit import stages
from cloudinit import templater
from cloudinit import util
from cloudinit import version


# Things u can query on
QUERY_DATA_TYPES = [
    'data',
    'data_raw',
    'instance_id',
]

LOG = logging.getLogger()


def warn(wstr):
    sys.stderr.write("WARN: %s\n" % (wstr))


def welcome(action):
    msg = ("Cloud-init v. {{version}} running '{{action}}' at "
           "{{timestamp}}. Up {{uptime}} seconds.")
    tpl_params = {
        'version': version.version_string(),
        'uptime': util.uptime(),
        'timestamp': util.time_rfc2822(),
        'action': action,
    }
    welcome_msg = "%s" % (templater.render_string(msg, tpl_params))
    sys.stderr.write("%s\n" % (welcome_msg))
    sys.stderr.flush()
    LOG.info(welcome_msg)


def main_init(name, args):
    deps = [sources.DEP_FILESYSTEM, sources.DEP_NETWORK]
    if args.local:
        deps = [sources.DEP_FILESYSTEM]

    cfg_extra_paths = []
    if args.files:
        # Already opened so lets just pass that along
        # since it would of broke if it couldn't have
        # read that file
        for f in args.files:
            cfg_extra_paths.append(f.name)

    if not args.local:
        # TODO: What is this for??
        root_name = "%s.d" % (settings.CLOUD_CONFIG)
        target_fn = os.path.join(root_name, "91_kernel_cmdline_url.cfg")
        util.read_write_cmdline_url(target_fn)

    # Cloud-init 'init' stage is broken up into the following sub-stages
    # 1. Ensure that the init object fetches its config without errors
    # 2. Setup logging/output redirections with resultant config (if any)
    # 3. Initialize the cloud-init filesystem
    # 4. Check if we can stop early by looking for various files
    # 5. Fetch the datasource
    # 6. Connect to the current instance location + update the cache
    # 7. Consume the userdata (handlers get activated here)
    # 8. Adjust any subsequent logging/output redirections
    # 9. Run the transforms for the 'init' stage
    # 10. Done!
    init = stages.Init(deps)
    # Stage 1
    init.read_cfg(cfg_extra_paths)
    # Stage 2
    try:
        util.fixup_output(init.cfg, 'init')
    except:
        util.logexc(LOG, "Failed to setup output redirection")
    if args.debug:
        # Reset so that all the debug handlers are closed out
        LOG.debug("Logging being reset, this logger may no longer be active shortly")
        logging.resetLogging()
    logging.setupLogging(init.cfg)
    # Stage 3
    try:
        init.initialize()
    except Exception as e:
        util.logexc(LOG, "Failed to initialize, likely bad things to come: %s", e)
    # Stage 4
    path_helper = init.paths
    if not args.local:
        sys.stderr.write("%s\n" % (netinfo.debug_info()))
        LOG.debug(("Checking to see if files that we need already"
                   " exist from a previous run that would allow us"
                   " to stop early."))
        stop_files = [
            os.path.join(path_helper.get_cpath("data"), "no-net"),
            path_helper.get_ipath_cur("obj_pkl"),
        ]
        existing_files = []
        for fn in stop_files:
            try:
                c = util.load_file(fn)
                if len(c):
                    existing_files.append((fn, len(c)))
            except Exception as e:
                pass
        if existing_files:
            LOG.debug("Exiting early due to the existence of %s", existing_files)
            return 0
    else:
        # The cache is not instance specific, so it has to be purged
        # but we want 'start' to benefit from a cache if
        # a previous start-local populated one...
        manual_clean = util.get_cfg_option_bool(init.cfg,
                                                'manual_cache_clean', False)
        if manual_clean:
            LOG.debug("Not purging instance link, manual cleaning enabled")
            init.purge_cache(False)
        else:
            init.purge_cache()
        # Delete the non-net file as well
        util.del_fie(os.path.join(path_helper.get_cpath("data"), "no-net"))
    # Stage 5
    welcome(name)
    try:
        init.fetch()
    except sources.DataSourceNotFoundException as e:
        util.logexc(LOG, "No instance datasource found")
        warn("No instance datasource found: %s" % (e))
        # TODO: Return 0 or 1??
        return 1
    # Stage 6
    iid = init.instancify()
    LOG.debug("%s will now be targeting instance id: %s", name, iid)
    init.update()
    # Stage 7
    try:
        (ran, _results) = init.cloudify().run('consume_userdata',
                                             init.consume,
                                             args=[settings.PER_INSTANCE],
                                             freq=settings.PER_INSTANCE)
        if not ran:
            init.consume(settings.ALWAYS)
    except Exception as e:
        warn("Consuming user data failed: %s" % (e))
        raise
    # Stage 8
    

def main_config(name, args):
    pass


def main_final(name, args):
    pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', '-v', action='version', 
                        version='%(prog)s ' + (version.version_string()))
    parser.add_argument('--file', '-f', action='append', 
                        dest='files',
                        help='additional configuration file to include',
                        type=argparse.FileType('rb'))
    parser.add_argument('--debug', '-d', action='store_true', 
                        help='show additional pre-action logging',
                        default=False)
    subparsers = parser.add_subparsers()

    # Each action and its suboptions (if any)
    parser_init = subparsers.add_parser('init', help='initializes cloud-init and performs \'init\' transforms')
    parser_init.add_argument("--local", '-l', action='store_true',
                             help="start in local mode", default=False)
    parser_init.set_defaults(action='init')  # This is used so that we can know which action is selected

    parser_config = subparsers.add_parser('config', help='performs cloud-init \'config\' transforms')
    parser_config.set_defaults(action='config')

    parser_final = subparsers.add_parser('final', help='performs cloud-init \'final\' transforms')
    parser_final.set_defaults(action='final')

    parser_query = subparsers.add_parser('query', help='query information stored in cloud-init')
    parser_query.add_argument("--name", action="store",
                              help="item name to query on",
                              required=True,
                              choices=QUERY_DATA_TYPES)
    parser_query.set_defaults(action='query')
    args = parser.parse_args()
    
    # Setup basic logging to start (until reinitialized)
    if args.debug:
        logging.setupBasicLogging()

    stage_name = args.action
    stage_mp = {
        'init': main_init,
        'config': main_config,
        'final': main_final,
    }
    func = stage_mp.get(stage_name)
    return func(stage_name, args)


if __name__ == '__main__':
    sys.exit(main())

