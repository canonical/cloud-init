#!/usr/bin/python
#
# Copyright (C) 2012 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
# Copyright (C) 2012 Yahoo! Inc.
# Copyright (C) 2017 Amazon.com, Inc. or its affiliates
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
# Author: Andrew Jorgensen <ajorgens@amazon.com>
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
from cloudinit import url_helper
from cloudinit import util
from cloudinit import version
from cloudinit import warnings

from cloudinit import reporting
from cloudinit.reporting import events

from cloudinit.settings import (PER_INSTANCE, PER_ALWAYS, PER_ONCE,
                                CLOUD_CONFIG)

from cloudinit import atomic_helper

from cloudinit.config import cc_set_hostname
from cloudinit.dhclient_hook import LogDhclient


# Welcome message template
WELCOME_MSG_TPL = ("Cloud-init v. {version} running '{action}' at "
                   "{timestamp}. Up {uptime} seconds.")

# Module section template
MOD_SECTION_TPL = "cloud_%s_modules"

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
    return WELCOME_MSG_TPL.format(
        version=version.version_string(),
        uptime=util.uptime(),
        timestamp=util.time_rfc2822(),
        action=action)


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


def parse_cmdline_url(cmdline, names=('cloud-config-url', 'url')):
    data = util.keyval_str_to_dict(cmdline)
    for key in names:
        if key in data:
            return key, data[key]
    raise KeyError("No keys (%s) found in string '%s'" %
                   (cmdline, names))


def attempt_cmdline_url(path, network=True, cmdline=None):
    """Write data from url referenced in command line to path.

    path: a file to write content to if downloaded.
    network: should network access be assumed.
    cmdline: the cmdline to parse for cloud-config-url.

    This is used in MAAS datasource, in "ephemeral" (read-only root)
    environment where the instance netboots to iscsi ro root.
    and the entity that controls the pxe config has to configure
    the maas datasource.

    An attempt is made on network urls even in local datasource
    for case of network set up in initramfs.

    Return value is a tuple of a logger function (logging.DEBUG)
    and a message indicating what happened.
    """

    if cmdline is None:
        cmdline = util.get_cmdline()

    try:
        cmdline_name, url = parse_cmdline_url(cmdline)
    except KeyError:
        return (logging.DEBUG, "No kernel command line url found.")

    path_is_local = url.startswith("file://") or url.startswith("/")

    if path_is_local and os.path.exists(path):
        if network:
            m = ("file '%s' existed, possibly from local stage download"
                 " of command line url '%s'. Not re-writing." % (path, url))
            level = logging.INFO
            if path_is_local:
                level = logging.DEBUG
        else:
            m = ("file '%s' existed, possibly from previous boot download"
                 " of command line url '%s'. Not re-writing." % (path, url))
            level = logging.WARN

        return (level, m)

    kwargs = {'url': url, 'timeout': 10, 'retries': 2}
    if network or path_is_local:
        level = logging.WARN
        kwargs['sec_between'] = 1
    else:
        level = logging.DEBUG
        kwargs['sec_between'] = .1

    data = None
    header = b'#cloud-config'
    try:
        resp = url_helper.read_file_or_url(**kwargs)
        if resp.ok():
            data = resp.contents
            if not resp.contents.startswith(header):
                if cmdline_name == 'cloud-config-url':
                    level = logging.WARN
                else:
                    level = logging.INFO
                return (
                    level,
                    "contents of '%s' did not start with %s" % (url, header))
        else:
            return (level,
                    "url '%s' returned code %s. Ignoring." % (url, resp.code))

    except url_helper.UrlError as e:
        return (level, "retrieving url '%s' failed: %s" % (url, e))

    util.write_file(path, data, mode=0o600)
    return (logging.INFO,
            "wrote cloud-config data from %s='%s' to %s" %
            (cmdline_name, url, path))


def main_init(name, args):
    deps = [sources.DEP_FILESYSTEM, sources.DEP_NETWORK]
    if args.local:
        deps = [sources.DEP_FILESYSTEM]

    early_logs = [attempt_cmdline_url(
        path=os.path.join("%s.d" % CLOUD_CONFIG,
                          "91_kernel_cmdline_url.cfg"),
        network=not args.local)]

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
        early_logs.append((logging.DEBUG, "Closing stdin."))
        util.close_stdin()
        (outfmt, errfmt) = util.fixup_output(init.cfg, name)
    except Exception:
        msg = "Failed to setup output redirection!"
        util.logexc(LOG, msg)
        print_exc(msg)
        early_logs.append((logging.WARN, msg))
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

    # re-play early log messages before logging was setup
    for lvl, msg in early_logs:
        LOG.log(lvl, msg)

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
        mcfg = util.get_cfg_option_bool(init.cfg, 'manual_cache_clean', False)
        if mcfg:
            LOG.debug("manual cache clean set from config")
            existing = "trust"
        else:
            mfile = path_helper.get_ipath_cur("manual_clean_marker")
            if os.path.exists(mfile):
                LOG.debug("manual cache clean found from marker: %s", mfile)
                existing = "trust"

        init.purge_cache()
        # Delete the no-net file as well
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
            LOG.debug("[%s] Exiting without datasource", mode)
            if mode == sources.DSMODE_LOCAL:
                return (None, [])
            else:
                return (None, ["No instance datasource found."])
        else:
            LOG.debug("[%s] barreling on in force mode without datasource",
                      mode)

    _maybe_persist_instance_data(init)
    # Stage 6
    iid = init.instancify()
    LOG.debug("[%s] %s will now be targeting instance id: %s. new=%s",
              mode, name, iid, init.is_new_instance())

    if mode == sources.DSMODE_LOCAL:
        # Before network comes up, set any configured hostname to allow
        # dhcp clients to advertize this hostname to any DDNS services
        # LP: #1746455.
        _maybe_set_hostname(init, stage='local', retry_stage='network')
    init.apply_network_config(bring_up=bool(mode != sources.DSMODE_LOCAL))

    if mode == sources.DSMODE_LOCAL:
        if init.datasource.dsmode != mode:
            LOG.debug("[%s] Exiting. datasource %s not in local mode.",
                      mode, init.datasource)
            return (init.datasource, [])
        else:
            LOG.debug("[%s] %s is in local mode, will apply init modules now.",
                      mode, init.datasource)

    # Give the datasource a chance to use network resources.
    # This is used on Azure to communicate with the fabric over network.
    init.setup_datasource()
    # update fully realizes user-data (pulling in #include if necessary)
    init.update()
    _maybe_set_hostname(init, stage='init-net', retry_stage='modules:config')
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
            LOG.warning("Stdout, stderr changing to (%s, %s)",
                        outfmt, errfmt)
            (outfmt, errfmt) = util.fixup_output(mods.cfg, name)
    except Exception:
        util.logexc(LOG, "Failed to re-adjust output redirection!")
    logging.setupLogging(mods.cfg)

    # give the activated datasource a chance to adjust
    init.activate_datasource()

    di_report_warn(datasource=init.datasource, cfg=init.cfg)

    # Stage 10
    return (init.datasource, run_module_section(mods, name, name))


def di_report_warn(datasource, cfg):
    if 'di_report' not in cfg:
        LOG.debug("no di_report found in config.")
        return

    dicfg = cfg['di_report']
    if dicfg is None:
        # ds-identify may write 'di_report:\n #comment\n'
        # which reads as {'di_report': None}
        LOG.debug("di_report was None.")
        return

    if not isinstance(dicfg, dict):
        LOG.warning("di_report config not a dictionary: %s", dicfg)
        return

    dslist = dicfg.get('datasource_list')
    if dslist is None:
        LOG.warning("no 'datasource_list' found in di_report.")
        return
    elif not isinstance(dslist, list):
        LOG.warning("di_report/datasource_list not a list: %s", dslist)
        return

    # ds.__module__ is like cloudinit.sources.DataSourceName
    # where Name is the thing that shows up in datasource_list.
    modname = datasource.__module__.rpartition(".")[2]
    if modname.startswith(sources.DS_PREFIX):
        modname = modname[len(sources.DS_PREFIX):]
    else:
        LOG.warning("Datasource '%s' came from unexpected module '%s'.",
                    datasource, modname)

    if modname in dslist:
        LOG.debug("used datasource '%s' from '%s' was in di_report's list: %s",
                  datasource, modname, dslist)
        return

    warnings.show_warning('dsid_missing_source', cfg,
                          source=modname, dslist=str(dslist))


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
    _maybe_persist_instance_data(init)
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
    _maybe_persist_instance_data(init)
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
        LOG.warning("Ran %s but it failed!", mod_name)
        return 1
    elif not which_ran:
        LOG.warning("Did not run %s, does it exist?", mod_name)
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

    modes = ('init', 'init-local', 'modules-init', 'modules-config',
             'modules-final')
    if mode not in modes:
        raise ValueError(
            "Invalid cloud init mode specified '{0}'".format(mode))

    status = None
    if mode == 'init-local':
        for f in (status_link, result_link, status_path, result_path):
            util.del_file(f)
    else:
        try:
            status = json.loads(util.load_file(status_path))
        except Exception:
            pass

    nullstatus = {
        'errors': [],
        'start': None,
        'finished': None,
    }
    if status is None:
        status = {'v1': {}}
        for m in modes:
            status['v1'][m] = nullstatus.copy()
        status['v1']['datasource'] = None
    elif mode not in status['v1']:
        status['v1'][mode] = nullstatus.copy()

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


def _maybe_persist_instance_data(init):
    """Write instance-data.json file if absent and datasource is restored."""
    if init.ds_restored:
        instance_data_file = os.path.join(
            init.paths.run_dir, sources.INSTANCE_JSON_FILE)
        if not os.path.exists(instance_data_file):
            init.datasource.persist_instance_data()


def _maybe_set_hostname(init, stage, retry_stage):
    """Call set-hostname if metadata, vendordata or userdata provides it.

    @param stage: String representing current stage in which we are running.
    @param retry_stage: String represented logs upon error setting hostname.
    """
    cloud = init.cloudify()
    (hostname, _fqdn) = util.get_hostname_fqdn(
        init.cfg, cloud, metadata_only=True)
    if hostname:  # meta-data or user-data hostname content
        try:
            cc_set_hostname.handle('set-hostname', init.cfg, cloud, LOG, None)
        except cc_set_hostname.SetHostnameError as e:
            LOG.debug(
                'Failed setting hostname in %s stage. Will'
                ' retry in %s stage. Error: %s.', stage, retry_stage, str(e))


def main_features(name, args):
    sys.stdout.write('\n'.join(sorted(version.FEATURES)) + '\n')


def main(sysv_args=None):
    if not sysv_args:
        sysv_args = sys.argv
    parser = argparse.ArgumentParser(prog=sysv_args[0])
    sysv_args = sysv_args[1:]

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
    subparsers = parser.add_subparsers(title='Subcommands', dest='subcommand')
    subparsers.required = True

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

    parser_query = subparsers.add_parser(
        'query',
        help='Query standardized instance metadata from the command line.')

    parser_dhclient = subparsers.add_parser('dhclient-hook',
                                            help=('run the dhclient hook'
                                                  'to record network info'))
    parser_dhclient.add_argument("net_action",
                                 help=('action taken on the interface'))
    parser_dhclient.add_argument("net_interface",
                                 help=('the network interface being acted'
                                       ' upon'))
    parser_dhclient.set_defaults(action=('dhclient_hook', dhclient_hook))

    parser_features = subparsers.add_parser('features',
                                            help=('list defined features'))
    parser_features.set_defaults(action=('features', main_features))

    parser_analyze = subparsers.add_parser(
        'analyze', help='Devel tool: Analyze cloud-init logs and data')

    parser_devel = subparsers.add_parser(
        'devel', help='Run development tools')

    parser_collect_logs = subparsers.add_parser(
        'collect-logs', help='Collect and tar all cloud-init debug info')

    parser_clean = subparsers.add_parser(
        'clean', help='Remove logs and artifacts so cloud-init can re-run.')

    parser_status = subparsers.add_parser(
        'status', help='Report cloud-init status or wait on completion.')

    if sysv_args:
        # Only load subparsers if subcommand is specified to avoid load cost
        if sysv_args[0] == 'analyze':
            from cloudinit.analyze.__main__ import get_parser as analyze_parser
            # Construct analyze subcommand parser
            analyze_parser(parser_analyze)
        elif sysv_args[0] == 'devel':
            from cloudinit.cmd.devel.parser import get_parser as devel_parser
            # Construct devel subcommand parser
            devel_parser(parser_devel)
        elif sysv_args[0] == 'collect-logs':
            from cloudinit.cmd.devel.logs import (
                get_parser as logs_parser, handle_collect_logs_args)
            logs_parser(parser_collect_logs)
            parser_collect_logs.set_defaults(
                action=('collect-logs', handle_collect_logs_args))
        elif sysv_args[0] == 'clean':
            from cloudinit.cmd.clean import (
                get_parser as clean_parser, handle_clean_args)
            clean_parser(parser_clean)
            parser_clean.set_defaults(
                action=('clean', handle_clean_args))
        elif sysv_args[0] == 'query':
            from cloudinit.cmd.query import (
                get_parser as query_parser, handle_args as handle_query_args)
            query_parser(parser_query)
            parser_query.set_defaults(
                action=('render', handle_query_args))
        elif sysv_args[0] == 'status':
            from cloudinit.cmd.status import (
                get_parser as status_parser, handle_status_args)
            status_parser(parser_status)
            parser_status.set_defaults(
                action=('status', handle_status_args))

    args = parser.parse_args(args=sysv_args)

    # Subparsers.required = True and each subparser sets action=(name, functor)
    (name, functor) = args.action

    # Setup basic logging to start (until reinitialized)
    # iff in debug mode.
    if args.debug:
        logging.setupBasicLogging()

    # Setup signal handlers before running
    signal_handler.attach_handlers()

    if name in ("modules", "init"):
        functor = status_wrapper

    rname = None
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
    else:
        rname = name
        rdesc = "running 'cloud-init %s'" % name
        report_on = False

    args.reporter = events.ReportEventStack(
        rname, rdesc, reporting_enabled=report_on)

    with args.reporter:
        retval = util.log_time(
            logfunc=LOG.debug, msg="cloud-init mode '%s'" % name,
            get_uptime=True, func=functor, args=(name, args))
        reporting.flush_events()
        return retval


if __name__ == '__main__':
    if 'TZ' not in os.environ:
        os.environ['TZ'] = ":/etc/localtime"
    return_value = main(sys.argv)
    if return_value:
        sys.exit(return_value)

# vi: ts=4 expandtab
