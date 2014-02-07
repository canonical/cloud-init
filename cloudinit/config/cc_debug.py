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

from cloudinit import type_utils
from cloudinit import util
import copy
from StringIO import StringIO


def _make_header(text):
    header = StringIO()
    header.write("-" * 80)
    header.write("\n")
    header.write(text.center(80, ' '))
    header.write("\n")
    header.write("-" * 80)
    header.write("\n")
    return header.getvalue()


def handle(name, cfg, cloud, log, args):
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
    for k in ['log_cfgs']:
        dump_cfg.pop(k, None)
    all_keys = list(dump_cfg.keys())
    for k in all_keys:
        if k.startswith("_"):
            dump_cfg.pop(k, None)
    # Now dump it...
    to_print = StringIO()
    to_print.write(_make_header("Config"))
    to_print.write(util.yaml_dumps(dump_cfg))
    to_print.write("\n")
    to_print.write(_make_header("MetaData"))
    to_print.write(util.yaml_dumps(cloud.datasource.metadata))
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
        util.write_file(out_file, "".join(content_to_file), 0644, "w")
    else:
        util.multi_log("".join(content_to_file), console=True, stderr=False)
