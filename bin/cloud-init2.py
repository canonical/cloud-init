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
from cloudinit import util
from cloudinit import version


# Things u can query on
QUERY_DATA_TYPES = [
    'data',
    'data_raw',
    'instance_id',
]

LOG = logging.getLogger(__name__)


def read_write_cmdline_url(target_fn):
    if not os.path.exists(target_fn):
        try:
            (key, url, content) = util.get_cmdline_url()
        except:
            util.logexc(LOG, "Failed fetching command line url")
            return
        try:
            if key and content:
                util.write_file(target_fn, content, mode=0600)
                LOG.info(("Wrote to %s with contents of command line"
                          " url %s (len=%s)"), target_fn, url, len(content))
            elif key and not content:
                LOG.info(("Command line key %s with url"
                          " %s had no contents"), key, url)
        except:
            util.logexc(LOG, "Failed writing url content to %s", target_fn)


def main_init(args):
    deps = [sources.DEP_FILESYSTEM, sources.DEP_NETWORK]
    if args.local:
        deps = [sources.DEP_FILESYSTEM]

    cfg_path = None
    if args.file:
        # Already opened so lets just pass that along
        # since it would of broke if it couldn't have
        # read that file
        cfg_path = str(args.file.name)

    if not args.local:
        # What is this for??
        root_name = "%s.d" % (settings.CLOUD_CONFIG)
        target_fn = os.path.join(root_name, "91_kernel_cmdline_url.cfg")
        read_write_cmdline_url(target_fn)
    
    # Cloud-init 'init' stage is broken up into the following stages
    # 1. Ensure that the init object fetches its config without errors
    # 2. Setup logging/output redirections with resultant config (if any)
    # 3. Initialize the cloud-init filesystem
    # 4. Check if we can stop early by looking for various files
    # 5. Fetch the datasource
    # 6. Consume the userdata (handlers get activated here)
    # 7. Adjust any subsequent logging/output redirections
    # 8. Run the transforms for the 'init' stage
    # 9. Done!
    now = util.time_rfc2822()
    uptime = util.uptime()
    init = stages.Init(deps)
    # Stage 1
    init.read_cfg()
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
        nonet_path = "%s/%s" % (cloudinit.get_cpath("data"), "no-net")

def main_config(args):
    pass


def main_final(args):
    pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', '-v', action='version', 
                        version='%(prog)s ' + (version.version_string()))
    parser.add_argument('--file', '-f', action='store', 
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
    return func(args)


if __name__ == '__main__':
    sys.exit(main())

