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
    """
    Enable and configure ntp

    ntp:
       pools: ['0.{{distro}}.pool.ntp.org', '1.{{distro}}.pool.ntp.org']
       servers: ['192.168.2.1']

    """

    ntp_cfg = cfg.get('ntp', {})

    if not isinstance(ntp_cfg, (dict)):
        raise RuntimeError(("'ntp' key existed in config,"
                            " but not a dictionary type,"
                            " is a %s %instead"), type_utils.obj_name(ntp_cfg))

    if 'ntp' not in cfg:
        LOG.debug("Skipping module named %s,"
                  "not present or disabled by cfg", name)
        return True

    install_ntp(cloud.distro.install_packages, packages=['ntp'],
                check_exe="ntpd")
    rename_ntp_conf()
    write_ntp_config_template(ntp_cfg, cloud)


def install_ntp(install_func, packages=None, check_exe="ntpd"):
    if util.which(check_exe):
        return
    if packages is None:
        packages = ['ntp']

    install_func(packages)


def rename_ntp_conf(config=NTP_CONF):
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
        LOG.debug('Adding distro default ntp pool servers')
        pools = generate_server_names(cloud.distro.name)

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

# vi: ts=4 expandtab
