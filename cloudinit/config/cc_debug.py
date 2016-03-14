# vi: ts=4 expandtab
#
#    Copyright (C) 2013 Yahoo! Inc.
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

"""
**Summary:** helper to debug cloud-init *internal* datastructures.

**Description:** This module will enable for outputting various internal
information that cloud-init sources provide to either a file or to the output
console/log location that this cloud-init has been configured with when
running.

It can be configured with the following option structure::

    debug:
       verbose: (defaulting to true)
       output: (location to write output, defaulting to console + log)

.. note::

    Log configurations are not output.
"""

import copy

from six import StringIO

from cloudinit import type_utils
from cloudinit import util

SKIP_KEYS = frozenset(['log_cfgs'])


def _make_header(text):
    header = StringIO()
    header.write("-" * 80)
    header.write("\n")
    header.write(text.center(80, ' '))
    header.write("\n")
    header.write("-" * 80)
    header.write("\n")
    return header.getvalue()


def _dumps(obj):
    text = util.yaml_dumps(obj, explicit_start=False, explicit_end=False)
    return text.rstrip()


def handle(name, cfg, cloud, log, args):
    """Handler method activated by cloud-init."""

    verbose = util.get_cfg_by_path(cfg, ('debug', 'verbose'), default=True)
    if args:
        # if args are provided (from cmdline) then explicitly set verbose
        out_file = args[0]
        verbose = True
    else:
        out_file = util.get_cfg_by_path(cfg, ('debug', 'output'))

    if not verbose:
        log.debug(("Skipping module named %s,"
                   " verbose printing disabled"), name)
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
    to_print.write("Datasource: %s\n" %
                   (type_utils.obj_name(cloud.datasource)))
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
