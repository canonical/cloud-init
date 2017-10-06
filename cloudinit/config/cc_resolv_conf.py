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
As Debian/Ubuntu will, by default, utilize resovlconf, and similarly RedHat
will use sysconfig, this module is likely to be of little use unless those
are configured correctly.

.. note::
    For RedHat with sysconfig, be sure to set PEERDNS=no for all DHCP
    enabled NICs.

.. note::
    And, in Ubuntu/Debian it is recommended that DNS be configured via the
    standard /etc/network/interfaces configuration file.

**Internal name:** ``cc_resolv_conf``

**Module frequency:** per instance

**Supported distros:** fedora, rhel, sles

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
from cloudinit.settings import PER_INSTANCE
from cloudinit import templater
from cloudinit import util

LOG = logging.getLogger(__name__)

frequency = PER_INSTANCE

distros = ['fedora', 'opensuse', 'rhel', 'sles']


def generate_resolv_conf(template_fn, params, target_fname="/etc/resolv.conf"):
    flags = []
    false_flags = []

    if 'options' in params:
        for key, val in params['options'].items():
            if isinstance(val, bool):
                if val:
                    flags.append(key)
                else:
                    false_flags.append(key)

    for flag in flags + false_flags:
        del params['options'][flag]

    if not params.get('options'):
        params['options'] = {}

    params['flags'] = flags
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
        log.debug(("Skipping module named %s,"
                   " no 'manage_resolv_conf' key in configuration"), name)
        return

    if not util.get_cfg_option_bool(cfg, "manage_resolv_conf", False):
        log.debug(("Skipping module named %s,"
                   " 'manage_resolv_conf' present but set to False"), name)
        return

    if "resolv_conf" not in cfg:
        log.warn("manage_resolv_conf True but no parameters provided!")

    template_fn = cloud.get_template_filename('resolv.conf')
    if not template_fn:
        log.warn("No template found, not rendering /etc/resolv.conf")
        return

    generate_resolv_conf(template_fn=template_fn, params=cfg["resolv_conf"])
    return

# vi: ts=4 expandtab
