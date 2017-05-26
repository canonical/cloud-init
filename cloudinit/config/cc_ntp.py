# Copyright (C) 2016 Canonical Ltd.
#
# Author: Ryan Harper <ryan.harper@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""
NTP
---
**Summary:** enable and configure ntp

Handle ntp configuration. If ntp is not installed on the system and ntp
configuration is specified, ntp will be installed. If there is a default ntp
config file in the image or one is present in the distro's ntp package, it will
be copied to ``/etc/ntp.conf.dist`` before any changes are made. A list of ntp
pools and ntp servers can be provided under the ``ntp`` config key. If no ntp
servers or pools are provided, 4 pools will be used in the format
``{0-3}.{distro}.pool.ntp.org``.

**Internal name:** ``cc_ntp``

**Module frequency:** per instance

**Supported distros:** centos, debian, fedora, opensuse, ubuntu

**Config keys**::

    ntp:
        pools:
            - 0.company.pool.ntp.org
            - 1.company.pool.ntp.org
            - ntp.myorg.org
        servers:
            - my.ntp.server.local
            - ntp.ubuntu.com
            - 192.168.23.2
"""

from cloudinit import log as logging
from cloudinit.settings import PER_INSTANCE
from cloudinit import templater
from cloudinit import type_utils
from cloudinit import util

import os

LOG = logging.getLogger(__name__)

frequency = PER_INSTANCE
NTP_CONF = '/etc/ntp.conf'
NR_POOL_SERVERS = 4
distros = ['centos', 'debian', 'fedora', 'opensuse', 'ubuntu']


def handle(name, cfg, cloud, log, _args):
    """Enable and configure ntp."""

    if 'ntp' not in cfg:
        LOG.debug(
            "Skipping module named %s, not present or disabled by cfg", name)
        return

    ntp_cfg = cfg.get('ntp', {})

    if not isinstance(ntp_cfg, (dict)):
        raise RuntimeError(("'ntp' key existed in config,"
                            " but not a dictionary type,"
                            " is a %s %instead"), type_utils.obj_name(ntp_cfg))

    rename_ntp_conf()
    # ensure when ntp is installed it has a configuration file
    # to use instead of starting up with packaged defaults
    write_ntp_config_template(ntp_cfg, cloud)
    install_ntp(cloud.distro.install_packages, packages=['ntp'],
                check_exe="ntpd")
    # if ntp was already installed, it may not have started
    try:
        reload_ntp(systemd=cloud.distro.uses_systemd())
    except util.ProcessExecutionError as e:
        LOG.exception("Failed to reload/start ntp service: %s", e)
        raise


def install_ntp(install_func, packages=None, check_exe="ntpd"):
    if util.which(check_exe):
        return
    if packages is None:
        packages = ['ntp']

    install_func(packages)


def rename_ntp_conf(config=None):
    """Rename any existing ntp.conf file and render from template"""
    if config is None:  # For testing
        config = NTP_CONF
    if os.path.exists(config):
        util.rename(config, config + ".dist")


def generate_server_names(distro):
    names = []
    for x in range(0, NR_POOL_SERVERS):
        name = "%d.%s.pool.ntp.org" % (x, distro)
        names.append(name)
    return names


def write_ntp_config_template(cfg, cloud):
    servers = cfg.get('servers', [])
    pools = cfg.get('pools', [])

    if len(servers) == 0 and len(pools) == 0:
        pools = generate_server_names(cloud.distro.name)
        LOG.debug(
            'Adding distro default ntp pool servers: %s', ','.join(pools))

    params = {
        'servers': servers,
        'pools': pools,
    }

    template_fn = cloud.get_template_filename('ntp.conf.%s' %
                                              (cloud.distro.name))
    if not template_fn:
        template_fn = cloud.get_template_filename('ntp.conf')
        if not template_fn:
            raise RuntimeError(("No template found, "
                                "not rendering %s"), NTP_CONF)

    templater.render_to_file(template_fn, NTP_CONF, params)


def reload_ntp(systemd=False):
    service = 'ntp'
    if systemd:
        cmd = ['systemctl', 'reload-or-restart', service]
    else:
        cmd = ['service', service, 'restart']
    util.subp(cmd, capture=True)


# vi: ts=4 expandtab
