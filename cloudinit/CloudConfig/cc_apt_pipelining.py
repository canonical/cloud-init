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
import cloudinit.SshUtil as sshutil
import re
import os
from cloudinit.CloudConfig import per_always

frequency = per_always
default_file = "/etc/apt/apt.conf.d/90cloud-init-tweaks"

def handle(_name, cfg, cloud, log, _args):

    apt_pipelining_enabled = util.get_cfg_option_str(cfg, "apt-pipelining", False)

    if apt_pipelining_enabled in ("False", "false", False):
        write_apt_snippet(0, log)

    elif apt_pipelining_enabled in ("Default", "default", "True", "true", True):
        revert_os_default(log)

    else:
        write_apt_snippet(apt_pipelining_enabled, log)

def revert_os_default(log, f_name=default_file):
    try:

        if os.path.exists(f_name):
            os.unlink(f_name)

    except OSError:
        log.debug("Unable to remove %s" % f_name)


def write_apt_snippet(setting, log, f_name=default_file):
    """
        Reads f_name and determines if the setting matches or not. Sets to
        desired value
    """

    acquire_pipeline_depth = 'Acquire::http::Pipeline-Depth "%s";\n'
    try:
        if os.path.exists(f_name):
            update_file = False
            skip_re = re.compile('^//CLOUD-INIT-IGNORE.*')
            enabled_re = re.compile('Acquire::http::Pipeline-Depth.*')

            local_override = False
            tweak = open(f_name, 'r')
            new_file = []

            for line in tweak.readlines():
                if skip_re.match(line):
                    local_override = True
                    continue

                if enabled_re.match(line):

                    try:
                        value = line.replace('"','')
                        value = value.replace(';','')
                        enabled = value.split()[1]

                        if enabled != setting:
                            update_file = True
                            line = acquire_pipeline_depth % setting

                    except IndexError:
                        log.debug("Unable to determine current setting of 'Acquire::http::Pipeline-Depth'\n%s" % e)
                        return

                new_file.append(line)

            tweak.close()

            if local_override:
                log.debug("Not updating apt pipelining settings due to local override in %s" % f_name)
                return

            if update_file:
                tweak = open(f_name, 'w')
                for line in new_file:
                    tweak.write(line)
                tweak.close()

            return

        tweak = open(f_name, 'w')
        tweak.write("""//Cloud-init Tweaks\n//Disables APT HTTP pipelining\n""")
        tweak.write(acquire_pipeline_depth % setting)
        tweak.close()

        log.debug("Wrote %s with APT pipeline setting" % f_name )

    except IOError as e:
        log.debug("Unable to update pipeline settings in %s\n%s" % (f_name, e))
