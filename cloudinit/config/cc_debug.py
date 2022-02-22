# Copyright (C) 2013 Yahoo! Inc.
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Debug: Helper to debug cloud-init *internal* datastructures."""

import copy
from io import StringIO
from textwrap import dedent

from cloudinit import safeyaml, type_utils, util
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.distros import ALL_DISTROS
from cloudinit.settings import PER_INSTANCE

SKIP_KEYS = frozenset(["log_cfgs"])

MODULE_DESCRIPTION = """\
This module will enable for outputting various internal information that
cloud-init sources provide to either a file or to the output console/log
location that this cloud-init has been configured with when running.

.. note::
    Log configurations are not output.
"""

meta: MetaSchema = {
    "id": "cc_debug",
    "name": "Debug",
    "title": "Helper to debug cloud-init *internal* datastructures",
    "description": MODULE_DESCRIPTION,
    "distros": [ALL_DISTROS],
    "frequency": PER_INSTANCE,
    "examples": [
        dedent(
            """\
            debug:
              verbose: true
              output: /tmp/my_debug.log
            """
        )
    ],
}

__doc__ = get_meta_doc(meta)


def _make_header(text):
    header = StringIO()
    header.write("-" * 80)
    header.write("\n")
    header.write(text.center(80, " "))
    header.write("\n")
    header.write("-" * 80)
    header.write("\n")
    return header.getvalue()


def _dumps(obj):
    text = safeyaml.dumps(obj, explicit_start=False, explicit_end=False)
    return text.rstrip()


def handle(name, cfg, cloud, log, args):
    """Handler method activated by cloud-init."""
    verbose = util.get_cfg_by_path(cfg, ("debug", "verbose"), default=True)
    if args:
        # if args are provided (from cmdline) then explicitly set verbose
        out_file = args[0]
        verbose = True
    else:
        out_file = util.get_cfg_by_path(cfg, ("debug", "output"))

    if not verbose:
        log.debug("Skipping module named %s, verbose printing disabled", name)
        return
    # Clean out some keys that we just don't care about showing...
    dump_cfg = copy.deepcopy(cfg)
    for k in SKIP_KEYS:
        dump_cfg.pop(k, None)
    all_keys = list(dump_cfg)
    for k in all_keys:
        if k.startswith("_"):
            dump_cfg.pop(k, None)
    # Now dump it...
    to_print = StringIO()
    to_print.write(_make_header("Config"))
    to_print.write(_dumps(dump_cfg))
    to_print.write("\n")
    to_print.write(_make_header("MetaData"))
    to_print.write(_dumps(cloud.datasource.metadata))
    to_print.write("\n")
    to_print.write(_make_header("Misc"))
    to_print.write(
        "Datasource: %s\n" % (type_utils.obj_name(cloud.datasource))
    )
    to_print.write("Distro: %s\n" % (type_utils.obj_name(cloud.distro)))
    to_print.write("Hostname: %s\n" % (cloud.get_hostname(True)))
    to_print.write("Instance ID: %s\n" % (cloud.get_instance_id()))
    to_print.write("Locale: %s\n" % (cloud.get_locale()))
    to_print.write("Launch IDX: %s\n" % (cloud.launch_index))
    contents = to_print.getvalue()
    content_to_file = []
    for line in contents.splitlines():
        line = "ci-info: %s\n" % (line)
        content_to_file.append(line)
    if out_file:
        util.write_file(out_file, "".join(content_to_file), 0o644, "w")
    else:
        util.multi_log("".join(content_to_file), console=True, stderr=False)


# vi: ts=4 expandtab
