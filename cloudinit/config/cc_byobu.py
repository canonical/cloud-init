# vi: ts=4 expandtab
#
#    Copyright (C) 2009-2010 Canonical Ltd.
#    Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
#    Author: Scott Moser <scott.moser@canonical.com>
#    Author: Juerg Haefliger <juerg.haefliger@hp.com>
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

# Ensure this is aliased to a name not 'distros'
# since the module attribute 'distros'
# is a list of distros that are supported, not a sub-module
from cloudinit import distros as ds

from cloudinit import util

distros = ['ubuntu', 'debian']


def handle(name, cfg, cloud, log, args):
    if len(args) != 0:
        value = args[0]
    else:
        value = util.get_cfg_option_str(cfg, "byobu_by_default", "")

    if not value:
        log.debug("Skipping module named %s, no 'byobu' values found", name)
        return

    if value == "user" or value == "system":
        value = "enable-%s" % value

    valid = ("enable-user", "enable-system", "enable",
             "disable-user", "disable-system", "disable")
    if value not in valid:
        log.warn("Unknown value %s for byobu_by_default", value)

    mod_user = value.endswith("-user")
    mod_sys = value.endswith("-system")
    if value.startswith("enable"):
        bl_inst = "install"
        dc_val = "byobu byobu/launch-by-default boolean true"
        mod_sys = True
    else:
        if value == "disable":
            mod_user = True
            mod_sys = True
        bl_inst = "uninstall"
        dc_val = "byobu byobu/launch-by-default boolean false"

    shcmd = ""
    if mod_user:
        (users, _groups) = ds.normalize_users_groups(cfg, cloud.distro)
        (user, _user_config) = ds.extract_default(users)
        if not user:
            log.warn(("No default byobu user provided, "
                      "can not launch %s for the default user"), bl_inst)
        else:
            shcmd += " sudo -Hu \"%s\" byobu-launcher-%s" % (user, bl_inst)
            shcmd += " || X=$(($X+1)); "
    if mod_sys:
        shcmd += "echo \"%s\" | debconf-set-selections" % dc_val
        shcmd += " && dpkg-reconfigure byobu --frontend=noninteractive"
        shcmd += " || X=$(($X+1)); "

    if len(shcmd):
        cmd = ["/bin/sh", "-c", "%s %s %s" % ("X=0;", shcmd, "exit $X")]
        log.debug("Setting byobu to %s", value)
        util.subp(cmd, capture=False)
