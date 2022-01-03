# Copyright (C) 2013 Craig Tracey
# Copyright (C) 2013 Hewlett-Packard Development Company, L.P.
#
# Author: Craig Tracey <craigtracey@gmail.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""
Resolv Conf
-----------
**Summary:** configure resolv.conf

This module is intended to manage resolv.conf in environments where early
configuration of resolv.conf is necessary for further bootstrapping and/or
where configuration management such as puppet or chef own dns configuration.
As Debian/Ubuntu will, by default, utilize resolvconf, and similarly Red Hat
will use sysconfig, this module is likely to be of little use unless those
are configured correctly.

.. note::
    For Red Hat with sysconfig, be sure to set PEERDNS=no for all DHCP
    enabled NICs.

.. note::
    And, in Ubuntu/Debian it is recommended that DNS be configured via the
    standard /etc/network/interfaces configuration file.

**Internal name:** ``cc_resolv_conf``

**Module frequency:** per instance

**Supported distros:** alpine, fedora, photon, rhel, sles

**Config keys**::

    manage_resolv_conf: <true/false>
    resolv_conf:
        nameservers: ['8.8.4.4', '8.8.8.8']
        searchdomains:
            - foo.example.com
            - bar.example.com
        domain: example.com
        options:
            rotate: <true/false>
            timeout: 1
"""

from cloudinit import log as logging
from cloudinit import templater, util
from cloudinit.settings import PER_INSTANCE

LOG = logging.getLogger(__name__)

frequency = PER_INSTANCE

distros = ["alpine", "fedora", "opensuse", "photon", "rhel", "sles"]

RESOLVE_CONFIG_TEMPLATE_MAP = {
    "/etc/resolv.conf": "resolv.conf",
    "/etc/systemd/resolved.conf": "systemd.resolved.conf",
}


def generate_resolv_conf(template_fn, params, target_fname):
    flags = []
    false_flags = []

    if "options" in params:
        for key, val in params["options"].items():
            if isinstance(val, bool):
                if val:
                    flags.append(key)
                else:
                    false_flags.append(key)

    for flag in flags + false_flags:
        del params["options"][flag]

    if not params.get("options"):
        params["options"] = {}

    params["flags"] = flags
    LOG.debug("Writing resolv.conf from template %s", template_fn)
    templater.render_to_file(template_fn, target_fname, params)


def handle(name, cfg, cloud, log, _args):
    """
    Handler for resolv.conf

    @param name: The module name "resolv-conf" from cloud.cfg
    @param cfg: A nested dict containing the entire cloud config contents.
    @param cloud: The L{CloudInit} object in use.
    @param log: Pre-initialized Python logger object to use for logging.
    @param args: Any module arguments from cloud.cfg
    """
    if "manage_resolv_conf" not in cfg:
        log.debug(
            "Skipping module named %s,"
            " no 'manage_resolv_conf' key in configuration",
            name,
        )
        return

    if not util.get_cfg_option_bool(cfg, "manage_resolv_conf", False):
        log.debug(
            "Skipping module named %s,"
            " 'manage_resolv_conf' present but set to False",
            name,
        )
        return

    if "resolv_conf" not in cfg:
        log.warning("manage_resolv_conf True but no parameters provided!")
        return

    try:
        template_fn = cloud.get_template_filename(
            RESOLVE_CONFIG_TEMPLATE_MAP[cloud.distro.resolve_conf_fn]
        )
    except KeyError:
        log.warning("No template found, not rendering resolve configs")
        return

    generate_resolv_conf(
        template_fn=template_fn,
        params=cfg["resolv_conf"],
        target_fname=cloud.distro.resolve_conf_fn,
    )
    return


# vi: ts=4 expandtab
