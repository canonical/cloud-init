# Copyright (C) 2008-2022 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Chuck Short <chuck.short@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import copy

from cloudinit import config, distros, helpers, importer
from cloudinit import log as logging
from cloudinit import type_utils, util
from cloudinit.reporting import events
from cloudinit.settings import FREQUENCIES, PER_INSTANCE

LOG = logging.getLogger(__name__)

# This prefix is used to make it less
# of a chance that when importing
# we will not find something else with the same
# name in the lookup path...
MOD_PREFIX = "cc_"


def form_module_name(name):
    canon_name = name.replace("-", "_")
    if canon_name.lower().endswith(".py"):
        canon_name = canon_name[0 : (len(canon_name) - 3)]
    canon_name = canon_name.strip()
    if not canon_name:
        return None
    if not canon_name.startswith(MOD_PREFIX):
        canon_name = "%s%s" % (MOD_PREFIX, canon_name)
    return canon_name


def fixup_module(mod, def_freq=PER_INSTANCE):
    if not hasattr(mod, "frequency"):
        setattr(mod, "frequency", def_freq)
    else:
        freq = mod.frequency
        if freq and freq not in FREQUENCIES:
            LOG.warning("Module %s has an unknown frequency %s", mod, freq)
    if not hasattr(mod, "distros"):
        setattr(mod, "distros", [])
    if not hasattr(mod, "osfamilies"):
        setattr(mod, "osfamilies", [])
    return mod


class Modules(object):
    def __init__(self, init, cfg_files=None, reporter=None):
        self.init = init
        self.cfg_files = cfg_files
        # Created on first use
        self._cached_cfg = None
        if reporter is None:
            reporter = events.ReportEventStack(
                name="module-reporter",
                description="module-desc",
                reporting_enabled=False,
            )
        self.reporter = reporter

    @property
    def cfg(self):
        # None check to avoid empty case causing re-reading
        if self._cached_cfg is None:
            merger = helpers.ConfigMerger(
                paths=self.init.paths,
                datasource=self.init.datasource,
                additional_fns=self.cfg_files,
                base_cfg=self.init.cfg,
            )
            self._cached_cfg = merger.cfg
            # LOG.debug("Loading 'module' config %s", self._cached_cfg)
        # Only give out a copy so that others can't modify this...
        return copy.deepcopy(self._cached_cfg)

    def _read_modules(self, name):
        module_list = []
        if name not in self.cfg:
            return module_list
        cfg_mods = self.cfg.get(name)
        if not cfg_mods:
            return module_list
        # Create 'module_list', an array of hashes
        # Where hash['mod'] = module name
        #       hash['freq'] = frequency
        #       hash['args'] = arguments
        for item in cfg_mods:
            if not item:
                continue
            if isinstance(item, str):
                module_list.append(
                    {
                        "mod": item.strip(),
                    }
                )
            elif isinstance(item, (list)):
                contents = {}
                # Meant to fall through...
                if len(item) >= 1:
                    contents["mod"] = item[0].strip()
                if len(item) >= 2:
                    contents["freq"] = item[1].strip()
                if len(item) >= 3:
                    contents["args"] = item[2:]
                if contents:
                    module_list.append(contents)
            elif isinstance(item, (dict)):
                contents = {}
                valid = False
                if "name" in item:
                    contents["mod"] = item["name"].strip()
                    valid = True
                if "frequency" in item:
                    contents["freq"] = item["frequency"].strip()
                if "args" in item:
                    contents["args"] = item["args"] or []
                if contents and valid:
                    module_list.append(contents)
            else:
                raise TypeError(
                    "Failed to read '%s' item in config, unknown type %s"
                    % (item, type_utils.obj_name(item))
                )
        return module_list

    def _fixup_modules(self, raw_mods):
        mostly_mods = []
        for raw_mod in raw_mods:
            raw_name = raw_mod["mod"]
            freq = raw_mod.get("freq")
            run_args = raw_mod.get("args") or []
            mod_name = form_module_name(raw_name)
            if not mod_name:
                continue
            if freq and freq not in FREQUENCIES:
                LOG.warning(
                    "Config specified module %s has an unknown frequency %s",
                    raw_name,
                    freq,
                )
                # Reset it so when ran it will get set to a known value
                freq = None
            mod_locs, looked_locs = importer.find_module(
                mod_name, ["", type_utils.obj_name(config)], ["handle"]
            )
            if not mod_locs:
                LOG.warning(
                    "Could not find module named %s (searched %s)",
                    mod_name,
                    looked_locs,
                )
                continue
            mod = fixup_module(importer.import_module(mod_locs[0]))
            mostly_mods.append([mod, raw_name, freq, run_args])
        return mostly_mods

    def _run_modules(self, mostly_mods):
        cc = self.init.cloudify()
        # Return which ones ran
        # and which ones failed + the exception of why it failed
        failures = []
        which_ran = []
        for (mod, name, freq, args) in mostly_mods:
            try:
                # Try the modules frequency, otherwise fallback to a known one
                if not freq:
                    freq = mod.frequency
                if freq not in FREQUENCIES:
                    freq = PER_INSTANCE
                LOG.debug(
                    "Running module %s (%s) with frequency %s", name, mod, freq
                )

                # Use the configs logger and not our own
                # TODO(harlowja): possibly check the module
                # for having a LOG attr and just give it back
                # its own logger?
                func_args = [name, self.cfg, cc, LOG, args]
                # Mark it as having started running
                which_ran.append(name)
                # This name will affect the semaphore name created
                run_name = "config-%s" % (name)

                desc = "running %s with frequency %s" % (run_name, freq)
                myrep = events.ReportEventStack(
                    name=run_name, description=desc, parent=self.reporter
                )

                with myrep:
                    ran, _r = cc.run(
                        run_name, mod.handle, func_args, freq=freq
                    )
                    if ran:
                        myrep.message = "%s ran successfully" % run_name
                    else:
                        myrep.message = "%s previously ran" % run_name

            except Exception as e:
                util.logexc(LOG, "Running module %s (%s) failed", name, mod)
                failures.append((name, e))
        return (which_ran, failures)

    def run_single(self, mod_name, args=None, freq=None):
        # Form the users module 'specs'
        mod_to_be = {
            "mod": mod_name,
            "args": args,
            "freq": freq,
        }
        # Now resume doing the normal fixups and running
        raw_mods = [mod_to_be]
        mostly_mods = self._fixup_modules(raw_mods)
        return self._run_modules(mostly_mods)

    def run_section(self, section_name):
        raw_mods = self._read_modules(section_name)
        mostly_mods = self._fixup_modules(raw_mods)
        d_name = self.init.distro.name

        skipped = []
        forced = []
        overridden = self.cfg.get("unverified_modules", [])
        active_mods = []
        all_distros = set([distros.ALL_DISTROS])
        for (mod, name, _freq, _args) in mostly_mods:
            worked_distros = set(mod.distros)  # Minimally [] per fixup_modules
            worked_distros.update(
                distros.Distro.expand_osfamily(mod.osfamilies)
            )

            # Skip only when the following conditions are all met:
            #  - distros are defined in the module != ALL_DISTROS
            #  - the current d_name isn't in distros
            #  - and the module is unverified and not in the unverified_modules
            #    override list
            if worked_distros and worked_distros != all_distros:
                if d_name not in worked_distros:
                    if name not in overridden:
                        skipped.append(name)
                        continue
                    forced.append(name)
            active_mods.append([mod, name, _freq, _args])

        if skipped:
            LOG.info(
                "Skipping modules '%s' because they are not verified "
                "on distro '%s'.  To run anyway, add them to "
                "'unverified_modules' in config.",
                ",".join(skipped),
                d_name,
            )
        if forced:
            LOG.info("running unverified_modules: '%s'", ", ".join(forced))

        return self._run_modules(active_mods)
