# vi: ts=4 expandtab
#
#    Copyright (C) 2011 Canonical Ltd.
#
#    Author: Ben Howard <ben.howard@canonical.com>
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

import cloudinit.util as util
import re
import os
from cloudinit.CloudConfig import per_instance

frequency = per_instance
default_file = "/etc/apt/apt.conf.d/90cloud-init-pipeling"

def handle(_name, cfg, cloud, log, _args):

    apt_pipe_value = util.get_cfg_option_str(cfg, "apt_pipelining", False)
    apt_pipe_value = str(apt_pipe_value).lower()

    if apt_pipe_value in ("false", "default", False):
        write_apt_snippet(0, log)

    elif apt_pipe_value in ("none", "unchanged", "os"):
        return

    elif apt_pipe_value in str(range(1, 5)):
        write_apt_snippet(apt_pipe_value, log)

    else:
        log.warn("Invalid option for apt_pipeling")

def write_apt_snippet(setting, log, f_name=default_file):
    """
        Reads f_name and determines if the setting matches or not. Sets to
        desired value
    """

    acquire_pipeline_depth = 'Acquire::http::Pipeline-Depth "%s";\n'
    try:
        if os.path.exists(f_name):
            skip_re = re.compile('^//CLOUD-INIT-IGNORE.*')

            for line in tweak.readlines():
                if skip_re.match(line):
                    tweak.close()
                    return

            tweak.close()

        file_contents = ("//Cloud-init Tweaks\n//Disables APT HTTP pipelining"\
                        "\n" + (acquire_pipeline_depth % setting))

        util.write_file(f_name, file_contents)

        log.debug("Wrote %s with APT pipeline setting" % f_name )

    except IOError as e:
        log.debug("Unable to update pipeline settings in %s\n%s" % (f_name, e))
