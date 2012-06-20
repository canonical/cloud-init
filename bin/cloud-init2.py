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


# Transform section template
TR_TPL = "cloud_%s_modules"

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


def run_transforms(tr, action_name, section):
    full_section_name = TR_TPL % (section)
    (ran_am, failures) = tr.run(full_section_name)
    if not ran_am:
        msg = ("No '%s' transforms to run"
               " under section '%s'") % (action_name, full_section_name)
        sys.stderr.write("%s\n" % (msg))
        LOG.debug(msg)
        return 0
    else:
        LOG.debug("Ran %s transforms with %s failures", ran_am, len(failures))
        return len(failures)


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
    # 8. Construct the transform object
    # 9. Adjust any subsequent logging/output redirections using
    #    the transform objects configuration
    # 10. Run the transforms for the 'init' stage
    # 11. Done!
    welcome(name)
    init = stages.Init(deps)
    # Stage 1
    init.read_cfg(cfg_extra_paths)
    # Stage 2
    outfmt = None
    errfmt = None
    try:
        LOG.debug("Closing stdin")
        util.close_stdin()
        (outfmt, errfmt) = util.fixup_output(init.cfg, name)
    except:
        util.logexc(LOG, "Failed to setup output redirection!")
    if args.debug:
        # Reset so that all the debug handlers are closed out
        LOG.debug(("Logging being reset, this logger may no"
                    " longer be active shortly"))
        logging.resetLogging()
    logging.setupLogging(init.cfg)
    # Stage 3
    try:
        init.initialize()
    except Exception:
        util.logexc(LOG, "Failed to initialize, likely bad things to come!")
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
            except Exception:
                pass
        if existing_files:
            LOG.debug("Exiting early due to the existence of %s files",
                      existing_files)
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
        util.del_file(os.path.join(path_helper.get_cpath("data"), "no-net"))
    # Stage 5
    try:
        init.fetch()
    except sources.DataSourceNotFoundException:
        util.logexc(LOG, "No instance datasource found!")
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
            init.consume(settings.PER_ALWAYS)
    except Exception:
        util.logexc(LOG, "Consuming user data failed!")
        return 1
    # Stage 8
    tr = stages.Transforms(init, cfg_extra_paths)
    # Stage 9 - TODO is this really needed??
    try:
        outfmt_orig = outfmt
        errfmt_orig = errfmt
        (outfmt, errfmt) = util.get_output_cfg(tr.cfg, name)
        if outfmt_orig != outfmt or errfmt_orig != errfmt:
            LOG.warn("Stdout, stderr changing to (%s, %s)", outfmt, errfmt)
            (outfmt, errfmt) = util.fixup_output(tr.cfg, name)
    except:
        util.logexc(LOG, "Failed to adjust output redirection!")
    # Stage 10
    return run_transforms(tr, name, name)


def main_transform(_action_name, args):
    name = args.mode
    i_cfgs = []
    if args.files:
        for fh in args.files:
            i_cfgs.append(fh.name)
    # Cloud-init transform stages are broken up into the following sub-stages
    # 1. Ensure that the init object fetches its config without errors
    # 2. Get the datasource from the init object, if it does
    #    not exist then that means the main_init stage never
    #    worked, and thus this stage can not run.
    # 3. Construct the transform object
    # 4. Adjust any subsequent logging/output redirections using
    #    the transform objects configuration
    # 5. Run the transforms for the given stage name
    # 6. Done!
    welcome(name)
    init = stages.Init(ds_deps=[])
    # Stage 1
    init.read_cfg(i_cfgs)
    # Stage 2
    try:
        init.fetch()
    except sources.DataSourceNotFoundException:
        # There was no datasource found, theres nothing to do
        util.logexc(LOG, 'Can not apply stage %s, no datasource found', name)
        return 1
    # Stage 3
    tr_cfgs = list(i_cfgs)
    cc_cfg = init.paths.get_ipath_cur('cloud_config')
    if settings.CFG_ENV_NAME in os.environ:
        cc_cfg = os.environ[settings.CFG_ENV_NAME]
    if cc_cfg and os.path.exists(cc_cfg):
        tr_cfgs.append(cc_cfg)
    tr = stages.Transforms(init, tr_cfgs)
    # Stage 4
    try:
        LOG.debug("Closing stdin")
        util.close_stdin()
        util.fixup_output(tr.cfg, name)
    except:
        util.logexc(LOG, "Failed to setup output redirection!")
    if args.debug:
        # Reset so that all the debug handlers are closed out
        LOG.debug(("Logging being reset, this logger may no"
                    " longer be active shortly"))
        logging.resetLogging()
    logging.setupLogging(tr.cfg)
    # Stage 5
    return run_transforms(tr, name, name)


def main_query(_name, _args):
    pass


def main_single(_name, _args):
    pass


def main():
    parser = argparse.ArgumentParser()
    
    # Top level args
    parser.add_argument('--version', '-v', action='version', 
                        version='%(prog)s ' + (version.version_string()))
    parser.add_argument('--file', '-f', action='append', 
                        dest='files',
                        help=('additional yaml configuration'
                              ' files to use'),
                        type=argparse.FileType('rb'))
    parser.add_argument('--debug', '-d', action='store_true',
                        help=('show additional pre-action'
                              ' logging (default: %(default)s)'),
                        default=False)
    subparsers = parser.add_subparsers()

    # Each action and its sub-options (if any)
    parser_init = subparsers.add_parser('init', 
                                        help=('initializes cloud-init and'
                                              ' performs initial transforms'))
    parser_init.add_argument("--local", '-l', action='store_true',
                             help="start in local mode (default: %(default)s)",
                             default=False)
    # This is used so that we can know which action is selected + 
    # the functor to use to run this subcommand
    parser_init.set_defaults(action=('init', main_init))

    # These settings are used for the 'config' and 'final' stages
    parser_tr = subparsers.add_parser('transform', 
                                      help=('performs transforms '
                                            'using a given configuration key'))
    parser_tr.add_argument("--mode", '-m', action='store',
                             help=("transform configuration name "
                                    "to use (default: %(default)s)"),
                             default='config',
                             choices=('config', 'final'))
    parser_tr.set_defaults(action=('transform', main_transform))

    # These settings are used when you want to query information
    # stored in the cloud-init data objects/directories/files
    parser_query = subparsers.add_parser('query', 
                                         help=('query information stored '
                                               'in cloud-init'))
    parser_query.add_argument("--name", '-n', action="store",
                              help="item name to query on",
                              required=True,
                              choices=QUERY_DATA_TYPES)
    parser_query.set_defaults(action=('query', main_query))

    # This subcommand allows you to run a single transform
    parser_single = subparsers.add_parser('single', 
                                         help=('run a single transform '))
    parser_single.set_defaults(action=('single', main_single))
    parser_single.add_argument("--name", '-n', action="store",
                              help="transform name to run",
                              required=True)
    parser_single.add_argument("--frequency", action="store",
                              help=("frequency of "
                                    " the transform (default: %(default)s)"),
                              required=False,
                              default=settings.PER_ALWAYS,
                              choices=settings.FREQUENCIES)
    parser_single.set_defaults(action=('single', main_single))


    args = parser.parse_args()

    # Setup basic logging to start (until reinitialized)
    if args.debug:
        logging.setupBasicLogging()

    (name, functor) = args.action
    return functor(name, args)


if __name__ == '__main__':
    sys.exit(main())

