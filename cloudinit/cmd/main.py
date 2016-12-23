#!/usr/bin/python
#
# Copyright (C) 2012 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import argparse
import json
import os
import sys
import time
import traceback

from cloudinit import patcher
patcher.patch()  # noqa

from cloudinit import log as logging
from cloudinit import netinfo
from cloudinit import signal_handler
from cloudinit import sources
from cloudinit import stages
from cloudinit import templater
from cloudinit import util
from cloudinit import version

from cloudinit import reporting
from cloudinit.reporting import events

from cloudinit.settings import (PER_INSTANCE, PER_ALWAYS, PER_ONCE,
                                CLOUD_CONFIG)

from cloudinit import atomic_helper

from cloudinit.dhclient_hook import LogDhclient


# Pretty little cheetah formatted welcome message template
WELCOME_MSG_TPL = ("Cloud-init v. ${version} running '${action}' at "
                   "${timestamp}. Up ${uptime} seconds.")

# Module section template
MOD_SECTION_TPL = "cloud_%s_modules"

# Things u can query on
QUERY_DATA_TYPES = [
    'data',
    'data_raw',
    'instance_id',
]

# Frequency shortname to full name
# (so users don't have to remember the full name...)
FREQ_SHORT_NAMES = {
    'instance': PER_INSTANCE,
    'always': PER_ALWAYS,
    'once': PER_ONCE,
}

LOG = logging.getLogger()


# Used for when a logger may not be active
# and we still want to print exceptions...
def print_exc(msg=''):
    if msg:
        sys.stderr.write("%s\n" % (msg))
    sys.stderr.write('-' * 60)
    sys.stderr.write("\n")
    traceback.print_exc(file=sys.stderr)
    sys.stderr.write('-' * 60)
    sys.stderr.write("\n")


def welcome(action, msg=None):
    if not msg:
        msg = welcome_format(action)
    util.multi_log("%s\n" % (msg),
                   console=False, stderr=True, log=LOG)
    return msg


def welcome_format(action):
    tpl_params = {
        'version': version.version_string(),
        'uptime': util.uptime(),
        'timestamp': util.time_rfc2822(),
        'action': action,
    }
    return templater.render_string(WELCOME_MSG_TPL, tpl_params)


def extract_fns(args):
    # Files are already opened so lets just pass that along
    # since it would of broke if it couldn't have
    # read that file already...
    fn_cfgs = []
    if args.files:
        for fh in args.files:
            # The realpath is more useful in logging
            # so lets resolve to that...
            fn_cfgs.append(os.path.realpath(fh.name))
    return fn_cfgs


def run_module_section(mods, action_name, section):
    full_section_name = MOD_SECTION_TPL % (section)
    (which_ran, failures) = mods.run_section(full_section_name)
    total_attempted = len(which_ran) + len(failures)
    if total_attempted == 0:
        msg = ("No '%s' modules to run"
               " under section '%s'") % (action_name, full_section_name)
        sys.stderr.write("%s\n" % (msg))
        LOG.debug(msg)
        return []
    else:
        LOG.debug("Ran %s modules with %s failures",
                  len(which_ran), len(failures))
        return failures


def apply_reporting_cfg(cfg):
    if cfg.get('reporting'):
        reporting.update_configuration(cfg.get('reporting'))


def main_init(name, args):
    deps = [sources.DEP_FILESYSTEM, sources.DEP_NETWORK]
    if args.local:
        deps = [sources.DEP_FILESYSTEM]

    if not args.local:
        # See doc/kernel-cmdline.txt
        #
        # This is used in maas datasource, in "ephemeral" (read-only root)
        # environment where the instance netboots to iscsi ro root.
        # and the entity that controls the pxe config has to configure
        # the maas datasource.
        #
        # Could be used elsewhere, only works on network based (not local).
        root_name = "%s.d" % (CLOUD_CONFIG)
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
    # 8. Construct the modules object
    # 9. Adjust any subsequent logging/output redirections using the modules
    #    objects config as it may be different from init object
    # 10. Run the modules for the 'init' stage
    # 11. Done!
    if not args.local:
        w_msg = welcome_format(name)
    else:
        w_msg = welcome_format("%s-local" % (name))
    init = stages.Init(ds_deps=deps, reporter=args.reporter)
    # Stage 1
    init.read_cfg(extract_fns(args))
    # Stage 2
    outfmt = None
    errfmt = None
    try:
        LOG.debug("Closing stdin")
        util.close_stdin()
        (outfmt, errfmt) = util.fixup_output(init.cfg, name)
    except Exception:
        util.logexc(LOG, "Failed to setup output redirection!")
        print_exc("Failed to setup output redirection!")
    if args.debug:
        # Reset so that all the debug handlers are closed out
        LOG.debug(("Logging being reset, this logger may no"
                   " longer be active shortly"))
        logging.resetLogging()
    logging.setupLogging(init.cfg)
    apply_reporting_cfg(init.cfg)

    # Any log usage prior to setupLogging above did not have local user log
    # config applied.  We send the welcome message now, as stderr/out have
    # been redirected and log now configured.
    welcome(name, msg=w_msg)

    # Stage 3
    try:
        init.initialize()
    except Exception:
        util.logexc(LOG, "Failed to initialize, likely bad things to come!")
    # Stage 4
    path_helper = init.paths
    mode = sources.DSMODE_LOCAL if args.local else sources.DSMODE_NETWORK

    if mode == sources.DSMODE_NETWORK:
        existing = "trust"
        sys.stderr.write("%s\n" % (netinfo.debug_info()))
        LOG.debug(("Checking to see if files that we need already"
                   " exist from a previous run that would allow us"
                   " to stop early."))
        # no-net is written by upstart cloud-init-nonet when network failed
        # to come up
        stop_files = [
            os.path.join(path_helper.get_cpath("data"), "no-net"),
        ]
        existing_files = []
        for fn in stop_files:
            if os.path.isfile(fn):
                existing_files.append(fn)

        if existing_files:
            LOG.debug("[%s] Exiting. stop file %s existed",
                      mode, existing_files)
            return (None, [])
        else:
            LOG.debug("Execution continuing, no previous run detected that"
                      " would allow us to stop early.")
    else:
        existing = "check"
        if util.get_cfg_option_bool(init.cfg, 'manual_cache_clean', False):
            existing = "trust"

        init.purge_cache()
        # Delete the non-net file as well
        util.del_file(os.path.join(path_helper.get_cpath("data"), "no-net"))

    # Stage 5
    try:
        init.fetch(existing=existing)
        # if in network mode, and the datasource is local
        # then work was done at that stage.
        if mode == sources.DSMODE_NETWORK and init.datasource.dsmode != mode:
            LOG.debug("[%s] Exiting. datasource %s in local mode",
                      mode, init.datasource)
            return (None, [])
    except sources.DataSourceNotFoundException:
        # In the case of 'cloud-init init' without '--local' it is a bit
        # more likely that the user would consider it failure if nothing was
        # found. When using upstart it will also mentions job failure
        # in console log if exit code is != 0.
        if mode == sources.DSMODE_LOCAL:
            LOG.debug("No local datasource found")
        else:
            util.logexc(LOG, ("No instance datasource found!"
                              " Likely bad things to come!"))
        if not args.force:
            init.apply_network_config(bring_up=not args.local)
            LOG.debug("[%s] Exiting without datasource in local mode", mode)
            if mode == sources.DSMODE_LOCAL:
                return (None, [])
            else:
                return (None, ["No instance datasource found."])
        else:
            LOG.debug("[%s] barreling on in force mode without datasource",
                      mode)

    # Stage 6
    iid = init.instancify()
    LOG.debug("[%s] %s will now be targeting instance id: %s. new=%s",
              mode, name, iid, init.is_new_instance())

    init.apply_network_config(bring_up=bool(mode != sources.DSMODE_LOCAL))

    if mode == sources.DSMODE_LOCAL:
        if init.datasource.dsmode != mode:
            LOG.debug("[%s] Exiting. datasource %s not in local mode.",
                      mode, init.datasource)
            return (init.datasource, [])
        else:
            LOG.debug("[%s] %s is in local mode, will apply init modules now.",
                      mode, init.datasource)

    # update fully realizes user-data (pulling in #include if necessary)
    init.update()
    # Stage 7
    try:
        # Attempt to consume the data per instance.
        # This may run user-data handlers and/or perform
        # url downloads and such as needed.
        (ran, _results) = init.cloudify().run('consume_data',
                                              init.consume_data,
                                              args=[PER_INSTANCE],
                                              freq=PER_INSTANCE)
        if not ran:
            # Just consume anything that is set to run per-always
            # if nothing ran in the per-instance code
            #
            # See: https://bugs.launchpad.net/bugs/819507 for a little
            # reason behind this...
            init.consume_data(PER_ALWAYS)
    except Exception:
        util.logexc(LOG, "Consuming user data failed!")
        return (init.datasource, ["Consuming user data failed!"])

    apply_reporting_cfg(init.cfg)

    # Stage 8 - re-read and apply relevant cloud-config to include user-data
    mods = stages.Modules(init, extract_fns(args), reporter=args.reporter)
    # Stage 9
    try:
        outfmt_orig = outfmt
        errfmt_orig = errfmt
        (outfmt, errfmt) = util.get_output_cfg(mods.cfg, name)
        if outfmt_orig != outfmt or errfmt_orig != errfmt:
            LOG.warn("Stdout, stderr changing to (%s, %s)", outfmt, errfmt)
            (outfmt, errfmt) = util.fixup_output(mods.cfg, name)
    except Exception:
        util.logexc(LOG, "Failed to re-adjust output redirection!")
    logging.setupLogging(mods.cfg)

    # give the activated datasource a chance to adjust
    init.activate_datasource()

    # Stage 10
    return (init.datasource, run_module_section(mods, name, name))


def main_modules(action_name, args):
    name = args.mode
    # Cloud-init 'modules' stages are broken up into the following sub-stages
    # 1. Ensure that the init object fetches its config without errors
    # 2. Get the datasource from the init object, if it does
    #    not exist then that means the main_init stage never
    #    worked, and thus this stage can not run.
    # 3. Construct the modules object
    # 4. Adjust any subsequent logging/output redirections using
    #    the modules objects configuration
    # 5. Run the modules for the given stage name
    # 6. Done!
    w_msg = welcome_format("%s:%s" % (action_name, name))
    init = stages.Init(ds_deps=[], reporter=args.reporter)
    # Stage 1
    init.read_cfg(extract_fns(args))
    # Stage 2
    try:
        init.fetch(existing="trust")
    except sources.DataSourceNotFoundException:
        # There was no datasource found, theres nothing to do
        msg = ('Can not apply stage %s, no datasource found! Likely bad '
               'things to come!' % name)
        util.logexc(LOG, msg)
        print_exc(msg)
        if not args.force:
            return [(msg)]
    # Stage 3
    mods = stages.Modules(init, extract_fns(args), reporter=args.reporter)
    # Stage 4
    try:
        LOG.debug("Closing stdin")
        util.close_stdin()
        util.fixup_output(mods.cfg, name)
    except Exception:
        util.logexc(LOG, "Failed to setup output redirection!")
    if args.debug:
        # Reset so that all the debug handlers are closed out
        LOG.debug(("Logging being reset, this logger may no"
                   " longer be active shortly"))
        logging.resetLogging()
    logging.setupLogging(mods.cfg)
    apply_reporting_cfg(init.cfg)

    # now that logging is setup and stdout redirected, send welcome
    welcome(name, msg=w_msg)

    # Stage 5
    return run_module_section(mods, name, name)


def main_query(name, _args):
    raise NotImplementedError(("Action '%s' is not"
                               " currently implemented") % (name))


def main_single(name, args):
    # Cloud-init single stage is broken up into the following sub-stages
    # 1. Ensure that the init object fetches its config without errors
    # 2. Attempt to fetch the datasource (warn if it doesn't work)
    # 3. Construct the modules object
    # 4. Adjust any subsequent logging/output redirections using
    #    the modules objects configuration
    # 5. Run the single module
    # 6. Done!
    mod_name = args.name
    w_msg = welcome_format(name)
    init = stages.Init(ds_deps=[], reporter=args.reporter)
    # Stage 1
    init.read_cfg(extract_fns(args))
    # Stage 2
    try:
        init.fetch(existing="trust")
    except sources.DataSourceNotFoundException:
        # There was no datasource found,
        # that might be bad (or ok) depending on
        # the module being ran (so continue on)
        util.logexc(LOG, ("Failed to fetch your datasource,"
                          " likely bad things to come!"))
        print_exc(("Failed to fetch your datasource,"
                   " likely bad things to come!"))
        if not args.force:
            return 1
    # Stage 3
    mods = stages.Modules(init, extract_fns(args), reporter=args.reporter)
    mod_args = args.module_args
    if mod_args:
        LOG.debug("Using passed in arguments %s", mod_args)
    mod_freq = args.frequency
    if mod_freq:
        LOG.debug("Using passed in frequency %s", mod_freq)
        mod_freq = FREQ_SHORT_NAMES.get(mod_freq)
    # Stage 4
    try:
        LOG.debug("Closing stdin")
        util.close_stdin()
        util.fixup_output(mods.cfg, None)
    except Exception:
        util.logexc(LOG, "Failed to setup output redirection!")
    if args.debug:
        # Reset so that all the debug handlers are closed out
        LOG.debug(("Logging being reset, this logger may no"
                   " longer be active shortly"))
        logging.resetLogging()
    logging.setupLogging(mods.cfg)
    apply_reporting_cfg(init.cfg)

    # now that logging is setup and stdout redirected, send welcome
    welcome(name, msg=w_msg)

    # Stage 5
    (which_ran, failures) = mods.run_single(mod_name,
                                            mod_args,
                                            mod_freq)
    if failures:
        LOG.warn("Ran %s but it failed!", mod_name)
        return 1
    elif not which_ran:
        LOG.warn("Did not run %s, does it exist?", mod_name)
        return 1
    else:
        # Guess it worked
        return 0


def dhclient_hook(name, args):
    record = LogDhclient(args)
    record.check_hooks_dir()
    record.record()


def status_wrapper(name, args, data_d=None, link_d=None):
    if data_d is None:
        data_d = os.path.normpath("/var/lib/cloud/data")
    if link_d is None:
        link_d = os.path.normpath("/run/cloud-init")

    status_path = os.path.join(data_d, "status.json")
    status_link = os.path.join(link_d, "status.json")
    result_path = os.path.join(data_d, "result.json")
    result_link = os.path.join(link_d, "result.json")

    util.ensure_dirs((data_d, link_d,))

    (_name, functor) = args.action

    if name == "init":
        if args.local:
            mode = "init-local"
        else:
            mode = "init"
    elif name == "modules":
        mode = "modules-%s" % args.mode
    else:
        raise ValueError("unknown name: %s" % name)

    modes = ('init', 'init-local', 'modules-config', 'modules-final')

    status = None
    if mode == 'init-local':
        for f in (status_link, result_link, status_path, result_path):
            util.del_file(f)
    else:
        try:
            status = json.loads(util.load_file(status_path))
        except Exception:
            pass

    if status is None:
        nullstatus = {
            'errors': [],
            'start': None,
            'finished': None,
        }
        status = {'v1': {}}
        for m in modes:
            status['v1'][m] = nullstatus.copy()
        status['v1']['datasource'] = None

    v1 = status['v1']
    v1['stage'] = mode
    v1[mode]['start'] = time.time()

    atomic_helper.write_json(status_path, status)
    util.sym_link(os.path.relpath(status_path, link_d), status_link,
                  force=True)

    try:
        ret = functor(name, args)
        if mode in ('init', 'init-local'):
            (datasource, errors) = ret
            if datasource is not None:
                v1['datasource'] = str(datasource)
        else:
            errors = ret

        v1[mode]['errors'] = [str(e) for e in errors]

    except Exception as e:
        util.logexc(LOG, "failed stage %s", mode)
        print_exc("failed run of stage %s" % mode)
        v1[mode]['errors'] = [str(e)]

    v1[mode]['finished'] = time.time()
    v1['stage'] = None

    atomic_helper.write_json(status_path, status)

    if mode == "modules-final":
        # write the 'finished' file
        errors = []
        for m in modes:
            if v1[m]['errors']:
                errors.extend(v1[m].get('errors', []))

        atomic_helper.write_json(
            result_path, {'v1': {'datasource': v1['datasource'],
                          'errors': errors}})
        util.sym_link(os.path.relpath(result_path, link_d), result_link,
                      force=True)

    return len(v1[mode]['errors'])


def main(sysv_args=None):
    if sysv_args is not None:
        parser = argparse.ArgumentParser(prog=sysv_args[0])
        sysv_args = sysv_args[1:]
    else:
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
    parser.add_argument('--force', action='store_true',
                        help=('force running even if no datasource is'
                              ' found (use at your own risk)'),
                        dest='force',
                        default=False)

    parser.set_defaults(reporter=None)
    subparsers = parser.add_subparsers()

    # Each action and its sub-options (if any)
    parser_init = subparsers.add_parser('init',
                                        help=('initializes cloud-init and'
                                              ' performs initial modules'))
    parser_init.add_argument("--local", '-l', action='store_true',
                             help="start in local mode (default: %(default)s)",
                             default=False)
    # This is used so that we can know which action is selected +
    # the functor to use to run this subcommand
    parser_init.set_defaults(action=('init', main_init))

    # These settings are used for the 'config' and 'final' stages
    parser_mod = subparsers.add_parser('modules',
                                       help=('activates modules using '
                                             'a given configuration key'))
    parser_mod.add_argument("--mode", '-m', action='store',
                            help=("module configuration name "
                                  "to use (default: %(default)s)"),
                            default='config',
                            choices=('init', 'config', 'final'))
    parser_mod.set_defaults(action=('modules', main_modules))

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

    # This subcommand allows you to run a single module
    parser_single = subparsers.add_parser('single',
                                          help=('run a single module '))
    parser_single.add_argument("--name", '-n', action="store",
                               help="module name to run",
                               required=True)
    parser_single.add_argument("--frequency", action="store",
                               help=("frequency of the module"),
                               required=False,
                               choices=list(FREQ_SHORT_NAMES.keys()))
    parser_single.add_argument("--report", action="store_true",
                               help="enable reporting",
                               required=False)
    parser_single.add_argument("module_args", nargs="*",
                               metavar='argument',
                               help=('any additional arguments to'
                                     ' pass to this module'))
    parser_single.set_defaults(action=('single', main_single))

    parser_dhclient = subparsers.add_parser('dhclient-hook',
                                            help=('run the dhclient hook'
                                                  'to record network info'))
    parser_dhclient.add_argument("net_action",
                                 help=('action taken on the interface'))
    parser_dhclient.add_argument("net_interface",
                                 help=('the network interface being acted'
                                       ' upon'))
    parser_dhclient.set_defaults(action=('dhclient_hook', dhclient_hook))

    args = parser.parse_args(args=sysv_args)

    try:
        (name, functor) = args.action
    except AttributeError:
        parser.error('too few arguments')

    # Setup basic logging to start (until reinitialized)
    # iff in debug mode...
    if args.debug:
        logging.setupBasicLogging()

    # Setup signal handlers before running
    signal_handler.attach_handlers()

    if name in ("modules", "init"):
        functor = status_wrapper

    report_on = True
    if name == "init":
        if args.local:
            rname, rdesc = ("init-local", "searching for local datasources")
        else:
            rname, rdesc = ("init-network",
                            "searching for network datasources")
    elif name == "modules":
        rname, rdesc = ("modules-%s" % args.mode,
                        "running modules for %s" % args.mode)
    elif name == "single":
        rname, rdesc = ("single/%s" % args.name,
                        "running single module %s" % args.name)
        report_on = args.report

    elif name == 'dhclient_hook':
        rname, rdesc = ("dhclient-hook",
                        "running dhclient-hook module")

    args.reporter = events.ReportEventStack(
        rname, rdesc, reporting_enabled=report_on)

    with args.reporter:
        return util.log_time(
            logfunc=LOG.debug, msg="cloud-init mode '%s'" % name,
            get_uptime=True, func=functor, args=(name, args))


if __name__ == '__main__':
    if 'TZ' not in os.environ:
        os.environ['TZ'] = ":/etc/localtime"
    main(sys.argv)

# vi: ts=4 expandtab
