#!/usr/bin/env python3

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
import traceback
import logging
import yaml
from typing import Optional, Tuple, Callable, Union

from cloudinit import netinfo
from cloudinit import signal_handler
from cloudinit import sources
from cloudinit import socket
from cloudinit import stages
from cloudinit import url_helper
from cloudinit import util
from cloudinit import performance
from cloudinit import version
from cloudinit import warnings
from cloudinit import reporting
from cloudinit import atomic_helper
from cloudinit import lifecycle
from cloudinit import handlers
from cloudinit.log import log_util, loggers
from cloudinit.cmd.devel import read_cfg_paths
from cloudinit.config import cc_set_hostname
from cloudinit.config.modules import Modules
from cloudinit.config.schema import validate_cloudconfig_schema
from cloudinit.lifecycle import log_with_downgradable_level
from cloudinit.reporting import events
from cloudinit.settings import (
    PER_INSTANCE,
    PER_ALWAYS,
    PER_ONCE,
    CLOUD_CONFIG,
)

Reason = str

# Welcome message template
WELCOME_MSG_TPL = (
    "Cloud-init v. {version} running '{action}' at "
    "{timestamp}. Up {uptime} seconds."
)

# Module section template
MOD_SECTION_TPL = "cloud_%s_modules"

# Frequency shortname to full name
# (so users don't have to remember the full name...)
FREQ_SHORT_NAMES = {
    "instance": PER_INSTANCE,
    "always": PER_ALWAYS,
    "once": PER_ONCE,
}

# https://docs.cloud-init.io/en/latest/explanation/boot.html
STAGE_NAME = {
    "init-local": "Local Stage",
    "init": "Network Stage",
    "modules-config": "Config Stage",
    "modules-final": "Final Stage",
}

LOG = logging.getLogger(__name__)


# Used for when a logger may not be active
# and we still want to print exceptions...
def print_exc(msg=""):
    if msg:
        sys.stderr.write("%s\n" % (msg))
    sys.stderr.write("-" * 60)
    sys.stderr.write("\n")
    traceback.print_exc(file=sys.stderr)
    sys.stderr.write("-" * 60)
    sys.stderr.write("\n")


def welcome(action, msg=None):
    if not msg:
        msg = welcome_format(action)
    log_util.multi_log("%s\n" % (msg), console=False, stderr=True, log=LOG)
    return msg


def welcome_format(action):
    return WELCOME_MSG_TPL.format(
        version=version.version_string(),
        uptime=util.uptime(),
        timestamp=util.time_rfc2822(),
        action=action,
    )


@performance.timed("Closing stdin")
def close_stdin(logger: Callable[[str], None] = LOG.debug):
    """
    reopen stdin as /dev/null to ensure no side effects

    logger: a function for logging messages
    """
    if not os.isatty(sys.stdin.fileno()):
        logger("Closing stdin")
        with open(os.devnull) as fp:
            os.dup2(fp.fileno(), sys.stdin.fileno())
    else:
        logger("Not closing stdin, stdin is a tty.")


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


def run_module_section(mods: Modules, action_name, section):
    full_section_name = MOD_SECTION_TPL % (section)
    (which_ran, failures) = mods.run_section(full_section_name)
    total_attempted = len(which_ran) + len(failures)
    if total_attempted == 0:
        msg = "No '%s' modules to run under section '%s'" % (
            action_name,
            full_section_name,
        )
        sys.stderr.write("%s\n" % (msg))
        LOG.debug(msg)
        return []
    else:
        LOG.debug(
            "Ran %s modules with %s failures", len(which_ran), len(failures)
        )
        return failures


def apply_reporting_cfg(cfg):
    if cfg.get("reporting"):
        reporting.update_configuration(cfg.get("reporting"))


def parse_cmdline_url(cmdline, names=("cloud-config-url", "url")):
    data = util.keyval_str_to_dict(cmdline)
    for key in names:
        if key in data:
            return key, data[key]
    raise KeyError("No keys (%s) found in string '%s'" % (cmdline, names))


def attempt_cmdline_url(path, network=True, cmdline=None) -> Tuple[int, str]:
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

    path_is_local = url.startswith(("file://", "/"))

    if path_is_local and os.path.exists(path):
        if network:
            m = (
                "file '%s' existed, possibly from local stage download"
                " of command line url '%s'. Not re-writing." % (path, url)
            )
            level = logging.INFO
            if path_is_local:
                level = logging.DEBUG
        else:
            m = (
                "file '%s' existed, possibly from previous boot download"
                " of command line url '%s'. Not re-writing." % (path, url)
            )
            level = logging.WARN

        return (level, m)

    kwargs = {"url": url, "timeout": 10, "retries": 2, "stream": True}
    if network or path_is_local:
        level = logging.WARN
        kwargs["sec_between"] = 1
    else:
        level = logging.DEBUG
        kwargs["sec_between"] = 0.1

    data = None
    header = b"#cloud-config"
    try:
        resp = url_helper.read_file_or_url(**kwargs)
        sniffed_content = b""
        if resp.ok():
            is_cloud_cfg = True
            if isinstance(resp, url_helper.UrlResponse):
                try:
                    sniffed_content += next(
                        resp.iter_content(chunk_size=len(header))
                    )
                except StopIteration:
                    pass
                if not sniffed_content.startswith(header):
                    is_cloud_cfg = False
            elif not resp.contents.startswith(header):
                is_cloud_cfg = False
            if is_cloud_cfg:
                if cmdline_name == "url":
                    return lifecycle.deprecate(
                        deprecated="The kernel command line key `url`",
                        deprecated_version="22.3",
                        extra_message=" Please use `cloud-config-url` "
                        "kernel command line parameter instead",
                        skip_log=True,
                    )
            else:
                if cmdline_name == "cloud-config-url":
                    level = logging.WARN
                else:
                    level = logging.INFO
                return (
                    level,
                    f"contents of '{url}' did not start with {str(header)}",
                )
        else:
            return (
                level,
                "url '%s' returned code %s. Ignoring." % (url, resp.code),
            )
        data = sniffed_content + resp.contents

    except url_helper.UrlError as e:
        return (level, "retrieving url '%s' failed: %s" % (url, e))

    util.write_file(path, data, mode=0o600)
    return (
        logging.INFO,
        "wrote cloud-config data from %s='%s' to %s"
        % (cmdline_name, url, path),
    )


def purge_cache_on_python_version_change(init):
    """Purge the cache if python version changed on us.

    There could be changes not represented in our cache (obj.pkl) after we
    upgrade to a new version of python, so at that point clear the cache
    """
    current_python_version = "%d.%d" % (
        sys.version_info.major,
        sys.version_info.minor,
    )
    python_version_path = os.path.join(
        init.paths.get_cpath("data"), "python-version"
    )
    if os.path.exists(python_version_path):
        cached_python_version = util.load_text_file(python_version_path)
        # The Python version has changed out from under us, anything that was
        # pickled previously is likely useless due to API changes.
        if cached_python_version != current_python_version:
            LOG.debug("Python version change detected. Purging cache")
            init.purge_cache(True)
            util.write_file(python_version_path, current_python_version)
    else:
        if os.path.exists(init.paths.get_ipath_cur("obj_pkl")):
            LOG.info(
                "Writing python-version file. "
                "Cache compatibility status is currently unknown."
            )
        util.write_file(python_version_path, current_python_version)


def _should_bring_up_interfaces(init, args):
    if util.get_cfg_option_bool(init.cfg, "disable_network_activation"):
        return False
    return not args.local


def _should_wait_via_user_data(
    raw_config: Optional[Union[str, bytes]]
) -> Tuple[bool, Reason]:
    """Determine if our cloud-config requires us to wait

    User data requires us to wait during cloud-init network phase if:
    - We have user data that is anything other than cloud-config
      - This can likely be further optimized in the future to include
        other user data types
    - cloud-config contains:
      - bootcmd
      - random_seed command
      - mounts
      - write_files with source
    """
    if not raw_config:
        return False, "no configuration found"

    if (
        handlers.type_from_starts_with(raw_config.strip()[:13])
        != "text/cloud-config"
    ):
        return True, "non-cloud-config user data found"

    try:
        parsed_yaml = yaml.safe_load(raw_config)
    except Exception as e:
        log_with_downgradable_level(
            logger=LOG,
            version="24.4",
            requested_level=logging.WARNING,
            msg="Unexpected failure parsing userdata: %s",
            args=e,
        )
        return True, "failed to parse user data as yaml"

    # These all have the potential to require network access, so we should wait
    if "write_files" in parsed_yaml:
        for item in parsed_yaml["write_files"]:
            source_dict = item.get("source") or {}
            source_uri = source_dict.get("uri", "")
            if source_uri and not (source_uri.startswith(("/", "file:"))):
                return True, "write_files with source uri found"
        return False, "write_files without source uri found"
    if parsed_yaml.get("bootcmd"):
        return True, "bootcmd found"
    if parsed_yaml.get("random_seed", {}).get("command"):
        return True, "random_seed command found"
    if parsed_yaml.get("mounts"):
        return True, "mounts found"
    return False, "cloud-config does not contain network requiring elements"


def _should_wait_on_network(
    datasource: Optional[sources.DataSource],
) -> Tuple[bool, Reason]:
    """Determine if we should wait on network connectivity for cloud-init.

    We need to wait during the cloud-init network phase if:
    - We have no datasource
    - We have user data that may require network access
    """
    if not datasource:
        return True, "no datasource found"
    user_should_wait, user_reason = _should_wait_via_user_data(
        datasource.get_userdata_raw()
    )
    if user_should_wait:
        return True, f"{user_reason} in user data"
    vendor_should_wait, vendor_reason = _should_wait_via_user_data(
        datasource.get_vendordata_raw()
    )
    if vendor_should_wait:
        return True, f"{vendor_reason} in vendor data"
    vendor2_should_wait, vendor2_reason = _should_wait_via_user_data(
        datasource.get_vendordata2_raw()
    )
    if vendor2_should_wait:
        return True, f"{vendor2_reason} in vendor data2"

    return (
        False,
        (
            f"user data: {user_reason}, "
            f"vendor data: {vendor_reason}, "
            f"vendor data2: {vendor2_reason}"
        ),
    )


def main_init(name, args):
    deps = [sources.DEP_FILESYSTEM, sources.DEP_NETWORK]
    if args.local:
        deps = [sources.DEP_FILESYSTEM]

    early_logs = [
        attempt_cmdline_url(
            path=os.path.join(
                "%s.d" % CLOUD_CONFIG, "91_kernel_cmdline_url.cfg"
            ),
            network=not args.local,
        )
    ]

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
    bootstage_name = "init-local" if args.local else "init"
    w_msg = welcome_format(bootstage_name)
    init = stages.Init(ds_deps=deps, reporter=args.reporter)
    # Stage 1
    init.read_cfg(extract_fns(args))
    # Stage 2
    outfmt = None
    errfmt = None
    try:
        if not args.skip_log_setup:
            close_stdin(lambda msg: early_logs.append((logging.DEBUG, msg)))
            outfmt, errfmt = util.fixup_output(init.cfg, name)
        else:
            outfmt, errfmt = util.get_output_cfg(init.cfg, name)
    except Exception:
        msg = "Failed to setup output redirection!"
        util.logexc(LOG, msg)
        print_exc(msg)
        early_logs.append((logging.WARN, msg))
    if args.debug:
        # Reset so that all the debug handlers are closed out
        LOG.debug(
            "Logging being reset, this logger may no longer be active shortly"
        )
        loggers.reset_logging()
    if not args.skip_log_setup:
        loggers.setup_logging(init.cfg)
        apply_reporting_cfg(init.cfg)

    # Any log usage prior to setup_logging above did not have local user log
    # config applied.  We send the welcome message now, as stderr/out have
    # been redirected and log now configured.
    welcome(name, msg=w_msg)
    LOG.info("PID [%s] started cloud-init '%s'.", os.getppid(), bootstage_name)

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
    purge_cache_on_python_version_change(init)
    mode = sources.DSMODE_LOCAL if args.local else sources.DSMODE_NETWORK

    if mode == sources.DSMODE_NETWORK:
        if not os.path.exists(init.paths.get_runpath(".skip-network")):
            LOG.debug("Will wait for network connectivity before continuing")
            init.distro.wait_for_network()
        existing = "trust"
        sys.stderr.write("%s\n" % (netinfo.debug_info()))
    else:
        existing = "check"
        mcfg = util.get_cfg_option_bool(init.cfg, "manual_cache_clean", False)
        if mcfg:
            LOG.debug("manual cache clean set from config")
            existing = "trust"
        else:
            mfile = path_helper.get_ipath_cur("manual_clean_marker")
            if os.path.exists(mfile):
                LOG.debug("manual cache clean found from marker: %s", mfile)
                existing = "trust"

        init.purge_cache()

    # Stage 5
    bring_up_interfaces = _should_bring_up_interfaces(init, args)
    try:
        init.fetch(existing=existing)
        # if in network mode, and the datasource is local
        # then work was done at that stage.
        if mode == sources.DSMODE_NETWORK and init.datasource.dsmode != mode:
            LOG.debug(
                "[%s] Exiting. datasource %s in local mode",
                mode,
                init.datasource,
            )
            return (None, [])
    except sources.DataSourceNotFoundException:
        # In the case of 'cloud-init init' without '--local' it is a bit
        # more likely that the user would consider it failure if nothing was
        # found.
        if mode == sources.DSMODE_LOCAL:
            LOG.debug("No local datasource found")
        else:
            util.logexc(
                LOG, "No instance datasource found! Likely bad things to come!"
            )
        if not args.force:
            init.apply_network_config(bring_up=bring_up_interfaces)
            LOG.debug("[%s] Exiting without datasource", mode)
            if mode == sources.DSMODE_LOCAL:
                return (None, [])
            else:
                return (None, ["No instance datasource found."])
        else:
            LOG.debug(
                "[%s] barreling on in force mode without datasource", mode
            )

    _maybe_persist_instance_data(init)
    # Stage 6
    iid = init.instancify()
    LOG.debug(
        "[%s] %s will now be targeting instance id: %s. new=%s",
        mode,
        name,
        iid,
        init.is_new_instance(),
    )

    if mode == sources.DSMODE_LOCAL:
        # Before network comes up, set any configured hostname to allow
        # dhcp clients to advertize this hostname to any DDNS services
        # LP: #1746455.
        _maybe_set_hostname(init, stage="local", retry_stage="network")

    init.apply_network_config(bring_up=bring_up_interfaces)

    if mode == sources.DSMODE_LOCAL:
        should_wait, reason = _should_wait_on_network(init.datasource)
        if should_wait:
            LOG.debug(
                "Network connectivity determined necessary for "
                "cloud-init's network stage. Reason: %s",
                reason,
            )
        else:
            LOG.debug(
                "Network connectivity determined unnecessary for "
                "cloud-init's network stage. Reason: %s",
                reason,
            )
            util.write_file(init.paths.get_runpath(".skip-network"), "")

        if init.datasource.dsmode != mode:
            LOG.debug(
                "[%s] Exiting. datasource %s not in local mode.",
                mode,
                init.datasource,
            )
            return (init.datasource, [])
        else:
            LOG.debug(
                "[%s] %s is in local mode, will apply init modules now.",
                mode,
                init.datasource,
            )

    # Give the datasource a chance to use network resources.
    # This is used on Azure to communicate with the fabric over network.
    init.setup_datasource()
    # update fully realizes user-data (pulling in #include if necessary)
    init.update()
    _maybe_set_hostname(init, stage="init-net", retry_stage="modules:config")
    # Stage 7
    try:
        # Attempt to consume the data per instance.
        # This may run user-data handlers and/or perform
        # url downloads and such as needed.
        (ran, _results) = init.cloudify().run(
            "consume_data",
            init.consume_data,
            args=[PER_INSTANCE],
            freq=PER_INSTANCE,
        )
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

    # Validate user-data adheres to schema definition
    cloud_cfg_path = init.paths.get_ipath_cur("cloud_config")
    if os.path.exists(cloud_cfg_path) and os.stat(cloud_cfg_path).st_size != 0:
        validate_cloudconfig_schema(
            config=yaml.safe_load(util.load_text_file(cloud_cfg_path)),
            strict=False,
            log_details=False,
            log_deprecations=True,
        )
    else:
        LOG.debug("Skipping user-data validation. No user-data found.")

    apply_reporting_cfg(init.cfg)

    # Stage 8 - re-read and apply relevant cloud-config to include user-data
    mods = Modules(init, extract_fns(args), reporter=args.reporter)
    # Stage 9
    try:
        outfmt_orig = outfmt
        errfmt_orig = errfmt
        (outfmt, errfmt) = util.get_output_cfg(mods.cfg, name)
        if outfmt_orig != outfmt or errfmt_orig != errfmt:
            LOG.warning("Stdout, stderr changing to (%s, %s)", outfmt, errfmt)
            (outfmt, errfmt) = util.fixup_output(mods.cfg, name)
    except Exception:
        util.logexc(LOG, "Failed to re-adjust output redirection!")
    loggers.setup_logging(mods.cfg)

    # give the activated datasource a chance to adjust
    init.activate_datasource()

    di_report_warn(datasource=init.datasource, cfg=init.cfg)

    # Stage 10
    return (init.datasource, run_module_section(mods, name, name))


def di_report_warn(datasource, cfg):
    if "di_report" not in cfg:
        LOG.debug("no di_report found in config.")
        return

    dicfg = cfg["di_report"]
    if dicfg is None:
        # ds-identify may write 'di_report:\n #comment\n'
        # which reads as {'di_report': None}
        LOG.debug("di_report was None.")
        return

    if not isinstance(dicfg, dict):
        LOG.warning("di_report config not a dictionary: %s", dicfg)
        return

    dslist = dicfg.get("datasource_list")
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
        modname = modname[len(sources.DS_PREFIX) :]
    else:
        LOG.warning(
            "Datasource '%s' came from unexpected module '%s'.",
            datasource,
            modname,
        )

    if modname in dslist:
        LOG.debug(
            "used datasource '%s' from '%s' was in di_report's list: %s",
            datasource,
            modname,
            dslist,
        )
        return

    warnings.show_warning(
        "dsid_missing_source", cfg, source=modname, dslist=str(dslist)
    )


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
    bootstage_name = "%s:%s" % (action_name, name)
    w_msg = welcome_format(bootstage_name)
    init = stages.Init(ds_deps=[], reporter=args.reporter)
    # Stage 1
    init.read_cfg(extract_fns(args))
    # Stage 2
    try:
        init.fetch(existing="trust")
    except sources.DataSourceNotFoundException:
        # There was no datasource found, theres nothing to do
        msg = (
            "Can not apply stage %s, no datasource found! Likely bad "
            "things to come!" % name
        )
        util.logexc(LOG, msg)
        print_exc(msg)
        if not args.force:
            return [(msg)]
    _maybe_persist_instance_data(init)
    # Stage 3
    mods = Modules(init, extract_fns(args), reporter=args.reporter)
    # Stage 4
    try:
        if not args.skip_log_setup:
            close_stdin()
            util.fixup_output(mods.cfg, name)
    except Exception:
        util.logexc(LOG, "Failed to setup output redirection!")
    if args.debug:
        # Reset so that all the debug handlers are closed out
        LOG.debug(
            "Logging being reset, this logger may no longer be active shortly"
        )
        loggers.reset_logging()
    if not args.skip_log_setup:
        loggers.setup_logging(mods.cfg)
        apply_reporting_cfg(init.cfg)

    # now that logging is setup and stdout redirected, send welcome
    welcome(name, msg=w_msg)
    LOG.info("PID [%s] started cloud-init '%s'.", os.getppid(), bootstage_name)

    if name == "init":
        lifecycle.deprecate(
            deprecated="`--mode init`",
            deprecated_version="24.1",
            extra_message="Use `cloud-init init` instead.",
        )

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
        util.logexc(
            LOG, "Failed to fetch your datasource, likely bad things to come!"
        )
        print_exc(
            "Failed to fetch your datasource, likely bad things to come!"
        )
        if not args.force:
            return 1
    _maybe_persist_instance_data(init)
    # Stage 3
    mods = Modules(init, extract_fns(args), reporter=args.reporter)
    mod_args = args.module_args
    if mod_args:
        LOG.debug("Using passed in arguments %s", mod_args)
    mod_freq = args.frequency
    if mod_freq:
        LOG.debug("Using passed in frequency %s", mod_freq)
        mod_freq = FREQ_SHORT_NAMES.get(mod_freq)
    # Stage 4
    try:
        close_stdin()
        util.fixup_output(mods.cfg, None)
    except Exception:
        util.logexc(LOG, "Failed to setup output redirection!")
    if args.debug:
        # Reset so that all the debug handlers are closed out
        LOG.debug(
            "Logging being reset, this logger may no longer be active shortly"
        )
        loggers.reset_logging()
    loggers.setup_logging(mods.cfg)
    apply_reporting_cfg(init.cfg)

    # now that logging is setup and stdout redirected, send welcome
    welcome(name, msg=w_msg)

    # Stage 5
    (which_ran, failures) = mods.run_single(mod_name, mod_args, mod_freq)
    if failures:
        LOG.warning("Ran %s but it failed!", mod_name)
        return 1
    elif not which_ran:
        LOG.warning("Did not run %s, does it exist?", mod_name)
        return 1
    else:
        # Guess it worked
        return 0


def status_wrapper(name, args):
    paths = read_cfg_paths()
    data_d = paths.get_cpath("data")
    link_d = os.path.normpath(paths.run_dir)

    status_path = os.path.join(data_d, "status.json")
    status_link = os.path.join(link_d, "status.json")
    result_path = os.path.join(data_d, "result.json")
    result_link = os.path.join(link_d, "result.json")
    root_logger = logging.getLogger()

    util.ensure_dirs(
        (
            data_d,
            link_d,
        )
    )

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

    if mode not in STAGE_NAME:
        raise ValueError(
            "Invalid cloud init mode specified '{0}'".format(mode)
        )

    nullstatus = {
        "errors": [],
        "recoverable_errors": {},
        "start": None,
        "finished": None,
    }
    status = {
        "v1": {
            "datasource": None,
            "init": nullstatus.copy(),
            "init-local": nullstatus.copy(),
            "modules-config": nullstatus.copy(),
            "modules-final": nullstatus.copy(),
        }
    }
    if mode == "init-local":
        for f in (status_link, result_link, status_path, result_path):
            util.del_file(f)
    else:
        try:
            status = json.loads(util.load_text_file(status_path))
        except Exception:
            pass

    if mode not in status["v1"]:
        # this should never happen, but leave it just to be safe
        status["v1"][mode] = nullstatus.copy()

    v1 = status["v1"]
    v1["stage"] = mode
    if v1[mode]["start"] and not v1[mode]["finished"]:
        # This stage was restarted, which isn't expected.
        LOG.warning(
            "Unexpected start time found for %s. Was this stage restarted?",
            STAGE_NAME[mode],
        )

    v1[mode]["start"] = float(util.uptime())
    handler = next(
        filter(
            lambda h: isinstance(h, loggers.LogExporter), root_logger.handlers
        )
    )
    preexisting_recoverable_errors = handler.export_logs()

    # Write status.json prior to running init / module code
    atomic_helper.write_json(status_path, status)
    util.sym_link(
        os.path.relpath(status_path, link_d), status_link, force=True
    )

    try:
        ret = functor(name, args)
        if mode in ("init", "init-local"):
            (datasource, errors) = ret
            if datasource is not None:
                v1["datasource"] = str(datasource)
        else:
            errors = ret

        v1[mode]["errors"].extend([str(e) for e in errors])
    except Exception as e:
        LOG.exception("failed stage %s", mode)
        print_exc("failed run of stage %s" % mode)
        v1[mode]["errors"].append(str(e))
    except SystemExit as e:
        # All calls to sys.exit() resume running here.
        # silence a pylint false positive
        # https://github.com/pylint-dev/pylint/issues/9556
        if e.code:  # pylint: disable=using-constant-test
            # Only log errors when sys.exit() is called with a non-zero
            # exit code
            LOG.exception("failed stage %s", mode)
            print_exc("failed run of stage %s" % mode)
            v1[mode]["errors"].append(f"sys.exit({str(e.code)}) called")
    finally:
        # Before it exits, cloud-init will:
        # 1) Write status.json (and result.json if in Final stage).
        # 2) Write the final log message containing module run time.
        # 3) Flush any queued reporting event handlers.
        v1[mode]["finished"] = float(util.uptime())
        v1["stage"] = None

        # merge new recoverable errors into existing recoverable error list
        new_recoverable_errors = handler.export_logs()
        handler.clean_logs()
        for key in new_recoverable_errors.keys():
            if key in preexisting_recoverable_errors:
                v1[mode]["recoverable_errors"][key] = list(
                    set(
                        preexisting_recoverable_errors[key]
                        + new_recoverable_errors[key]
                    )
                )
            else:
                v1[mode]["recoverable_errors"][key] = new_recoverable_errors[
                    key
                ]

        # Write status.json after running init / module code
        atomic_helper.write_json(status_path, status)

    if mode == "modules-final":
        # write the 'finished' file
        errors = []
        for m in v1.keys():
            if isinstance(v1[m], dict) and v1[m].get("errors"):
                errors.extend(v1[m].get("errors", []))

        atomic_helper.write_json(
            result_path,
            {"v1": {"datasource": v1["datasource"], "errors": errors}},
        )
        util.sym_link(
            os.path.relpath(result_path, link_d), result_link, force=True
        )

    return len(v1[mode]["errors"])


def _maybe_persist_instance_data(init: stages.Init):
    """Write instance-data.json file if absent and datasource is restored."""
    if init.datasource and init.ds_restored:
        instance_data_file = init.paths.get_runpath("instance_data")
        if not os.path.exists(instance_data_file):
            init.datasource.persist_instance_data(write_cache=False)


def _maybe_set_hostname(init, stage, retry_stage):
    """Call set_hostname if metadata, vendordata or userdata provides it.

    @param stage: String representing current stage in which we are running.
    @param retry_stage: String represented logs upon error setting hostname.
    """
    cloud = init.cloudify()
    (hostname, _fqdn, _) = util.get_hostname_fqdn(
        init.cfg, cloud, metadata_only=True
    )
    if hostname:  # meta-data or user-data hostname content
        try:
            cc_set_hostname.handle("set_hostname", init.cfg, cloud, None)
        except cc_set_hostname.SetHostnameError as e:
            LOG.debug(
                "Failed setting hostname in %s stage. Will"
                " retry in %s stage. Error: %s.",
                stage,
                retry_stage,
                str(e),
            )


def main_features(name, args):
    sys.stdout.write("\n".join(sorted(version.FEATURES)) + "\n")


def main(sysv_args=None):
    loggers.configure_root_logger()
    if not sysv_args:
        sysv_args = sys.argv
    parser = argparse.ArgumentParser(prog=sysv_args.pop(0))

    # Top level args
    parser.add_argument(
        "--version",
        "-v",
        action="version",
        version="%(prog)s " + (version.version_string()),
        help="Show program's version number and exit.",
    )
    parser.add_argument(
        "--debug",
        "-d",
        action="store_true",
        help="Show additional pre-action logging (default: %(default)s).",
        default=False,
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Force running even if no datasource is"
            " found (use at your own risk)."
        ),
        dest="force",
        default=False,
    )

    parser.add_argument(
        "--all-stages",
        dest="all_stages",
        action="store_true",
        help=(
            "Run cloud-init's stages under a single process using a "
            "syncronization protocol. This is not intended for CLI usage."
        ),
        default=False,
    )

    parser.set_defaults(reporter=None)
    subparsers = parser.add_subparsers(title="Subcommands", dest="subcommand")

    # Each action and its sub-options (if any)
    parser_init = subparsers.add_parser(
        "init", help="Initialize cloud-init and perform initial modules."
    )
    parser_init.add_argument(
        "--local",
        "-l",
        action="store_true",
        help="Start in local mode (default: %(default)s).",
        default=False,
    )
    parser_init.add_argument(
        "--file",
        "-f",
        action="append",
        dest="files",
        help="Use additional yaml configuration files.",
        type=argparse.FileType("rb"),
    )
    # This is used so that we can know which action is selected +
    # the functor to use to run this subcommand
    parser_init.set_defaults(action=("init", main_init))

    # These settings are used for the 'config' and 'final' stages
    parser_mod = subparsers.add_parser(
        "modules", help="Activate modules using a given configuration key."
    )
    extra_help = lifecycle.deprecate(
        deprecated="`init`",
        deprecated_version="24.1",
        extra_message="Use `cloud-init init` instead.",
        skip_log=True,
    ).message
    parser_mod.add_argument(
        "--mode",
        "-m",
        action="store",
        help=(
            f"Module configuration name to use (default: %(default)s)."
            f" {extra_help}"
        ),
        default="config",
        choices=("init", "config", "final"),
    )
    parser_mod.add_argument(
        "--file",
        "-f",
        action="append",
        dest="files",
        help="Use additional yaml configuration files.",
        type=argparse.FileType("rb"),
    )
    parser_mod.set_defaults(action=("modules", main_modules))

    # This subcommand allows you to run a single module
    parser_single = subparsers.add_parser(
        "single", help="Run a single module."
    )
    parser_single.add_argument(
        "--name",
        "-n",
        action="store",
        help="Module name to run.",
        required=True,
    )
    parser_single.add_argument(
        "--frequency",
        action="store",
        help="Module frequency for this run.",
        required=False,
        choices=list(FREQ_SHORT_NAMES.keys()),
    )
    parser_single.add_argument(
        "--report",
        action="store_true",
        help="Enable reporting.",
        required=False,
    )
    parser_single.add_argument(
        "module_args",
        nargs="*",
        metavar="argument",
        help="Any additional arguments to pass to this module.",
    )
    parser_single.add_argument(
        "--file",
        "-f",
        action="append",
        dest="files",
        help="Use additional yaml configuration files.",
        type=argparse.FileType("rb"),
    )
    parser_single.set_defaults(action=("single", main_single))

    parser_query = subparsers.add_parser(
        "query",
        help="Query standardized instance metadata from the command line.",
    )

    parser_features = subparsers.add_parser(
        "features", help="List defined features."
    )
    parser_features.set_defaults(action=("features", main_features))

    parser_analyze = subparsers.add_parser(
        "analyze", help="Devel tool: Analyze cloud-init logs and data."
    )

    parser_devel = subparsers.add_parser(
        "devel", help="Run development tools."
    )

    parser_collect_logs = subparsers.add_parser(
        "collect-logs", help="Collect and tar all cloud-init debug info."
    )

    parser_clean = subparsers.add_parser(
        "clean", help="Remove logs and artifacts so cloud-init can re-run."
    )

    parser_status = subparsers.add_parser(
        "status", help="Report cloud-init status or wait on completion."
    )

    parser_schema = subparsers.add_parser(
        "schema", help="Validate cloud-config files using jsonschema."
    )

    if sysv_args:
        # Only load subparsers if subcommand is specified to avoid load cost
        subcommand = next(
            (posarg for posarg in sysv_args if not posarg.startswith("-")),
            None,
        )
        if subcommand == "analyze":
            from cloudinit.analyze import get_parser as analyze_parser

            # Construct analyze subcommand parser
            analyze_parser(parser_analyze)
        elif subcommand == "devel":
            from cloudinit.cmd.devel.parser import get_parser as devel_parser

            # Construct devel subcommand parser
            devel_parser(parser_devel)
        elif subcommand == "collect-logs":
            from cloudinit.cmd.devel.logs import (
                get_parser as logs_parser,
                handle_collect_logs_args,
            )

            logs_parser(parser=parser_collect_logs)
            parser_collect_logs.set_defaults(
                action=("collect-logs", handle_collect_logs_args)
            )
        elif subcommand == "clean":
            from cloudinit.cmd.clean import (
                get_parser as clean_parser,
                handle_clean_args,
            )

            clean_parser(parser_clean)
            parser_clean.set_defaults(action=("clean", handle_clean_args))
        elif subcommand == "query":
            from cloudinit.cmd.query import (
                get_parser as query_parser,
                handle_args as handle_query_args,
            )

            query_parser(parser_query)
            parser_query.set_defaults(action=("render", handle_query_args))
        elif subcommand == "schema":
            from cloudinit.config.schema import (
                get_parser as schema_parser,
                handle_schema_args,
            )

            schema_parser(parser_schema)
            parser_schema.set_defaults(action=("schema", handle_schema_args))
        elif subcommand == "status":
            from cloudinit.cmd.status import (
                get_parser as status_parser,
                handle_status_args,
            )

            status_parser(parser_status)
            parser_status.set_defaults(action=("status", handle_status_args))
    else:
        parser.error("a subcommand is required")

    args = parser.parse_args(args=sysv_args)
    setattr(args, "skip_log_setup", False)
    if not args.all_stages:
        return sub_main(args)
    return all_stages(parser)


def all_stages(parser):
    """Run all stages in a single process using an ordering protocol."""
    LOG.info("Running cloud-init in single process mode.")

    # this _must_ be called before sd_notify is called otherwise netcat may
    # attempt to send "start" before a socket exists
    sync = socket.SocketSync("local", "network", "config", "final")

    # notify systemd that this stage has completed
    socket.sd_notify("READY=1")
    # wait for cloud-init-local.service to start
    with sync("local"):
        # set up logger
        args = parser.parse_args(args=["init", "--local"])
        args.skip_log_setup = False
        # run local stage
        sync.systemd_exit_code = sub_main(args)

    # wait for cloud-init-network.service to start
    with sync("network"):
        # skip re-setting up logger
        args = parser.parse_args(args=["init"])
        args.skip_log_setup = True
        # run init stage
        sync.systemd_exit_code = sub_main(args)

    # wait for cloud-config.service to start
    with sync("config"):
        # skip re-setting up logger
        args = parser.parse_args(args=["modules", "--mode=config"])
        args.skip_log_setup = True
        # run config stage
        sync.systemd_exit_code = sub_main(args)

    # wait for cloud-final.service to start
    with sync("final"):
        # skip re-setting up logger
        args = parser.parse_args(args=["modules", "--mode=final"])
        args.skip_log_setup = True
        # run final stage
        sync.systemd_exit_code = sub_main(args)

    # signal completion to cloud-init-main.service
    if sync.experienced_any_error:
        message = "a stage of cloud-init exited non-zero"
        if sync.first_exception:
            message = f"first exception received: {sync.first_exception}"
        socket.sd_notify(
            f"STATUS=Completed with failure, {message}. Run 'cloud-init status"
            " --long' for more details."
        )
        socket.sd_notify("STOPPING=1")
        # exit 1 for a fatal failure in any stage
        return 1
    else:
        socket.sd_notify("STATUS=Completed")
        socket.sd_notify("STOPPING=1")


def sub_main(args):

    # Subparsers.required = True and each subparser sets action=(name, functor)
    (name, functor) = args.action

    # Setup basic logging for cloud-init:
    # - for cloud-init stages if --debug
    # - for all other subcommands:
    #   - if --debug is passed, logging.DEBUG
    #   - if --debug is not passed, logging.WARNING
    if name not in ("init", "modules"):
        loggers.setup_basic_logging(
            logging.DEBUG if args.debug else logging.WARNING
        )
    elif args.debug:
        loggers.setup_basic_logging()

    # Setup signal handlers before running
    signal_handler.attach_handlers()

    # Write boot stage data to write status.json and result.json
    # Exclude modules --mode=init, since it is not a real boot stage and
    # should not be written into status.json
    if "init" == name or ("modules" == name and "init" != args.mode):
        functor = status_wrapper

    rname = None
    report_on = True
    if name == "init":
        if args.local:
            rname, rdesc = ("init-local", "searching for local datasources")
        else:
            rname, rdesc = (
                "init-network",
                "searching for network datasources",
            )
    elif name == "modules":
        rname, rdesc = (
            "modules-%s" % args.mode,
            "running modules for %s" % args.mode,
        )
    elif name == "single":
        rname, rdesc = (
            "single/%s" % args.name,
            "running single module %s" % args.name,
        )
        report_on = args.report
    else:
        rname = name
        rdesc = "running 'cloud-init %s'" % name
        report_on = False

    args.reporter = events.ReportEventStack(
        rname, rdesc, reporting_enabled=report_on
    )

    with args.reporter:
        with performance.Timed(f"cloud-init stage: '{rname}'"):
            retval = functor(name, args)
    reporting.flush_events()

    # handle return code for main_modules, as it is not wrapped by
    # status_wrapped when mode == init
    if "modules" == name and "init" == args.mode:
        retval = len(retval)

    return retval


if __name__ == "__main__":
    sys.exit(main(sys.argv))
