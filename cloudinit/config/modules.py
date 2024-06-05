# Copyright (C) 2008-2022 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Chuck Short <chuck.short@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import copy
import logging
from inspect import signature
from types import ModuleType
from typing import Dict, List, NamedTuple, Optional

from cloudinit import config, importer, type_utils, util
from cloudinit.distros import ALL_DISTROS
from cloudinit.helpers import ConfigMerger
from cloudinit.reporting.events import ReportEventStack
from cloudinit.settings import FREQUENCIES
from cloudinit.stages import Init

LOG = logging.getLogger(__name__)

# This prefix is used to make it less
# of a chance that when importing
# we will not find something else with the same
# name in the lookup path...
MOD_PREFIX = "cc_"

# List of modules that have removed upstream. This prevents every downstream
# from having to create upgrade scripts to avoid warnings about missing
# modules.
REMOVED_MODULES = [
    "cc_migrator",  # Removed in 24.1
    "cc_rightscale_userdata",  # Removed in 24.1
]

RENAMED_MODULES = {
    "cc_ubuntu_advantage": "cc_ubuntu_pro",  # Renamed 24.1
}


class ModuleDetails(NamedTuple):
    module: ModuleType
    name: str
    frequency: str
    run_args: List[str]


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


def validate_module(mod, name):
    if (
        not hasattr(mod, "meta")
        or "frequency" not in mod.meta
        or "distros" not in mod.meta
    ):
        raise ValueError(
            f"Module '{mod}' with name '{name}' MUST have a 'meta' attribute "
            "of type 'MetaSchema'."
        )
    if mod.meta["frequency"] not in FREQUENCIES:
        raise ValueError(
            f"Module '{mod}' with name '{name}' has an invalid frequency "
            f"{mod.meta['frequency']}."
        )
    if hasattr(mod, "schema"):
        raise ValueError(
            f"Module '{mod}' with name '{name}' has a JSON 'schema' attribute "
            "defined. Please define schema in cloud-init-schema,json."
        )


def _is_active(module_details: ModuleDetails, cfg: dict) -> bool:
    activate_by_schema_keys_keys = frozenset(
        module_details.module.meta.get("activate_by_schema_keys", {})
    )
    if not activate_by_schema_keys_keys:
        return True
    if not activate_by_schema_keys_keys.intersection(cfg.keys()):
        return False
    return True


class Modules:
    def __init__(self, init: Init, cfg_files=None, reporter=None):
        self.init = init
        self.cfg_files = cfg_files
        # Created on first use
        self._cached_cfg: Optional[config.Config] = None
        if reporter is None:
            reporter = ReportEventStack(
                name="module-reporter",
                description="module-desc",
                reporting_enabled=False,
            )
        self.reporter = reporter

    @property
    def cfg(self) -> config.Config:
        # None check to avoid empty case causing re-reading
        if self._cached_cfg is None:
            merger = ConfigMerger(
                paths=self.init.paths,
                datasource=self.init.datasource,
                additional_fns=self.cfg_files,
                base_cfg=self.init.cfg,
            )
            self._cached_cfg = merger.cfg
        # Only give out a copy so that others can't modify this...
        return copy.deepcopy(self._cached_cfg)

    def _read_modules(self, name) -> List[Dict]:
        """Read the modules from the config file given the specified name.

        Returns a list of module definitions. E.g.,
        [
            {
                "mod": "bootcmd",
                "freq": "always",
                "args": "some_arg",
            }
        ]

        Note that in the default case, only "mod" will be set.
        """
        module_list: List[dict] = []
        if name not in self.cfg:
            return module_list
        cfg_mods = self.cfg.get(name)
        if not cfg_mods:
            return module_list
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

    def _fixup_modules(self, raw_mods) -> List[ModuleDetails]:
        """Convert list of returned from _read_modules() into new format.

        Invalid modules and arguments are ignored.
        Also ensures that the module has the required meta fields.
        """
        mostly_mods = []
        for raw_mod in raw_mods:
            raw_name = raw_mod["mod"]
            freq = raw_mod.get("freq")
            run_args = raw_mod.get("args") or []
            mod_name = form_module_name(raw_name)
            if not mod_name:
                continue
            if freq and freq not in FREQUENCIES:
                util.deprecate(
                    deprecated=(
                        f"Config specified module {raw_name} has an unknown"
                        f" frequency {freq}"
                    ),
                    deprecated_version="22.1",
                )
                # Misconfigured in /etc/cloud/cloud.cfg. Reset so cc_* module
                # default meta attribute "frequency" value is used.
                freq = None
            if mod_name in RENAMED_MODULES:
                util.deprecate(
                    deprecated=(
                        f"Module has been renamed from {mod_name} to "
                        f"{RENAMED_MODULES[mod_name]}. Update any"
                        " references in /etc/cloud/cloud.cfg"
                    ),
                    deprecated_version="24.1",
                )
                mod_name = RENAMED_MODULES[mod_name]
            mod_locs, looked_locs = importer.find_module(
                mod_name, ["", type_utils.obj_name(config)], ["handle"]
            )
            if not mod_locs:
                if mod_name in REMOVED_MODULES:
                    LOG.info(
                        "Module `%s` has been removed from cloud-init. "
                        "It may be removed from `/etc/cloud/cloud.cfg`.",
                        mod_name[3:],  # [3:] to remove 'cc_'
                    )
                else:
                    LOG.warning(
                        "Could not find module named %s (searched %s)",
                        mod_name,
                        looked_locs,
                    )
                continue
            mod = importer.import_module(mod_locs[0])
            validate_module(mod, raw_name)
            if freq is None:
                # Use cc_* module default setting since no cloud.cfg overrides
                freq = mod.meta["frequency"]
            mostly_mods.append(
                ModuleDetails(
                    module=mod,
                    name=raw_name,
                    frequency=freq,
                    run_args=run_args,
                )
            )
        return mostly_mods

    def _run_modules(self, mostly_mods: List[ModuleDetails]):
        cc = self.init.cloudify()
        # Return which ones ran
        # and which ones failed + the exception of why it failed
        failures = []
        which_ran = []
        for mod, name, freq, args in mostly_mods:
            try:
                LOG.debug(
                    "Running module %s (%s) with frequency %s", name, mod, freq
                )

                # Mark it as having started running
                which_ran.append(name)
                # This name will affect the semaphore name created
                run_name = f"config-{name}"

                desc = "running %s with frequency %s" % (run_name, freq)
                myrep = ReportEventStack(
                    name=run_name, description=desc, parent=self.reporter
                )
                func_args = {
                    "name": name,
                    "cfg": self.cfg,
                    "cloud": cc,
                    "args": args,
                }

                with myrep:
                    func_signature = signature(mod.handle)
                    func_params = func_signature.parameters
                    if len(func_params) == 5:
                        util.deprecate(
                            deprecated="Config modules with a `log` parameter",
                            deprecated_version="23.2",
                        )
                        func_args.update({"log": LOG})
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
        """Runs all modules in the given section.

        section_name - One of the modules lists as defined in
          /etc/cloud/cloud.cfg. One of:
         - cloud_init_modules
         - cloud_config_modules
         - cloud_final_modules
        """
        raw_mods = self._read_modules(section_name)
        mostly_mods = self._fixup_modules(raw_mods)
        distro_name = self.init.distro.name

        skipped = []
        forced = []
        overridden = self.cfg.get("unverified_modules", [])
        inapplicable_mods = []
        active_mods = []
        for module_details in mostly_mods:
            (mod, name, _freq, _args) = module_details
            if mod is None:
                continue
            worked_distros = mod.meta["distros"]
            if not _is_active(module_details, self.cfg):
                inapplicable_mods.append(name)
                continue
            # Skip only when the following conditions are all met:
            #  - distros are defined in the module != ALL_DISTROS
            #  - the current d_name isn't in distros
            #  - and the module is unverified and not in the unverified_modules
            #    override list
            if worked_distros and worked_distros != [ALL_DISTROS]:
                if distro_name not in worked_distros:
                    if name not in overridden:
                        skipped.append(name)
                        continue
                    forced.append(name)
            active_mods.append([mod, name, _freq, _args])

        if inapplicable_mods:
            LOG.info(
                "Skipping modules '%s' because no applicable config "
                "is provided.",
                ",".join(inapplicable_mods),
            )
        if skipped:
            LOG.info(
                "Skipping modules '%s' because they are not verified "
                "on distro '%s'.  To run anyway, add them to "
                "'unverified_modules' in config.",
                ",".join(skipped),
                distro_name,
            )
        if forced:
            LOG.info("running unverified_modules: '%s'", ", ".join(forced))

        return self._run_modules(active_mods)
