# Copyright (C) 2009-2010 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""
Byobu
-----
**Summary:** enable/disable byobu system wide and for default user

This module controls whether byobu is enabled or disabled system wide and for
the default system user. If byobu is to be enabled, this module will ensure it
is installed. Likewise, if it is to be disabled, it will be removed if
installed.

Valid configuration options for this module are:

  - ``enable-system``: enable byobu system wide
  - ``enable-user``: enable byobu for the default user
  - ``disable-system``: disable byobu system wide
  - ``disable-user``: disable byobu for the default user
  - ``enable``: enable byobu both system wide and for default user
  - ``disable``: disable byobu for all users
  - ``user``: alias for ``enable-user``
  - ``system``: alias for ``enable-system``

**Internal name:** ``cc_byobu``

**Module frequency:** per instance

**Supported distros:** ubuntu, debian

**Config keys**::

    byobu_by_default: <user/system>
"""

from cloudinit.distros import ug_util
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
        (users, _groups) = ug_util.normalize_users_groups(cfg, cloud.distro)
        (user, _user_config) = ug_util.extract_default(users)
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

# vi: ts=4 expandtab
