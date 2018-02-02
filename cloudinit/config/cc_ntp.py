# Copyright (C) 2016 Canonical Ltd.
#
# Author: Ryan Harper <ryan.harper@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""NTP: enable and configure ntp"""

from cloudinit.config.schema import (
    get_schema_doc, validate_cloudconfig_schema)
from cloudinit import log as logging
from cloudinit.settings import PER_INSTANCE
from cloudinit import templater
from cloudinit import type_utils
from cloudinit import util

import os
from textwrap import dedent

LOG = logging.getLogger(__name__)

frequency = PER_INSTANCE
NTP_CONF = '/etc/ntp.conf'
TIMESYNCD_CONF = '/etc/systemd/timesyncd.conf.d/cloud-init.conf'
NR_POOL_SERVERS = 4
distros = ['centos', 'debian', 'fedora', 'opensuse', 'sles', 'ubuntu']


# The schema definition for each cloud-config module is a strict contract for
# describing supported configuration parameters for each cloud-config section.
# It allows cloud-config to validate and alert users to invalid or ignored
# configuration options before actually attempting to deploy with said
# configuration.

schema = {
    'id': 'cc_ntp',
    'name': 'NTP',
    'title': 'enable and configure ntp',
    'description': dedent("""\
        Handle ntp configuration. If ntp is not installed on the system and
        ntp configuration is specified, ntp will be installed. If there is a
        default ntp config file in the image or one is present in the
        distro's ntp package, it will be copied to ``/etc/ntp.conf.dist``
        before any changes are made. A list of ntp pools and ntp servers can
        be provided under the ``ntp`` config key. If no ntp ``servers`` or
        ``pools`` are provided, 4 pools will be used in the format
        ``{0-3}.{distro}.pool.ntp.org``."""),
    'distros': distros,
    'examples': [
        dedent("""\
        ntp:
          pools: [0.int.pool.ntp.org, 1.int.pool.ntp.org, ntp.myorg.org]
          servers:
            - ntp.server.local
            - ntp.ubuntu.com
            - 192.168.23.2""")],
    'frequency': PER_INSTANCE,
    'type': 'object',
    'properties': {
        'ntp': {
            'type': ['object', 'null'],
            'properties': {
                'pools': {
                    'type': 'array',
                    'items': {
                        'type': 'string',
                        'format': 'hostname'
                    },
                    'uniqueItems': True,
                    'description': dedent("""\
                        List of ntp pools. If both pools and servers are
                         empty, 4 default pool servers will be provided of
                         the format ``{0-3}.{distro}.pool.ntp.org``.""")
                },
                'servers': {
                    'type': 'array',
                    'items': {
                        'type': 'string',
                        'format': 'hostname'
                    },
                    'uniqueItems': True,
                    'description': dedent("""\
                        List of ntp servers. If both pools and servers are
                         empty, 4 default pool servers will be provided with
                         the format ``{0-3}.{distro}.pool.ntp.org``.""")
                }
            },
            'required': [],
            'additionalProperties': False
        }
    }
}

__doc__ = get_schema_doc(schema)  # Supplement python help()


def handle(name, cfg, cloud, log, _args):
    """Enable and configure ntp."""
    if 'ntp' not in cfg:
        LOG.debug(
            "Skipping module named %s, not present or disabled by cfg", name)
        return
    ntp_cfg = cfg['ntp']
    if ntp_cfg is None:
        ntp_cfg = {}  # Allow empty config which will install the package

    # TODO drop this when validate_cloudconfig_schema is strict=True
    if not isinstance(ntp_cfg, (dict)):
        raise RuntimeError(
            "'ntp' key existed in config, but not a dictionary type,"
            " is a {_type} instead".format(_type=type_utils.obj_name(ntp_cfg)))

    validate_cloudconfig_schema(cfg, schema)
    if ntp_installable():
        service_name = 'ntp'
        confpath = NTP_CONF
        template_name = None
        packages = ['ntp']
        check_exe = 'ntpd'
    else:
        service_name = 'systemd-timesyncd'
        confpath = TIMESYNCD_CONF
        template_name = 'timesyncd.conf'
        packages = []
        check_exe = '/lib/systemd/systemd-timesyncd'

    rename_ntp_conf()
    # ensure when ntp is installed it has a configuration file
    # to use instead of starting up with packaged defaults
    write_ntp_config_template(ntp_cfg, cloud, confpath, template=template_name)
    install_ntp(cloud.distro.install_packages, packages=packages,
                check_exe=check_exe)

    try:
        reload_ntp(service_name, systemd=cloud.distro.uses_systemd())
    except util.ProcessExecutionError as e:
        LOG.exception("Failed to reload/start ntp service: %s", e)
        raise


def ntp_installable():
    """Check if we can install ntp package

    Ubuntu-Core systems do not have an ntp package available, so
    we always return False.  Other systems require package managers to install
    the ntp package If we fail to find one of the package managers, then we
    cannot install ntp.
    """
    if util.system_is_snappy():
        return False

    if any(map(util.which, ['apt-get', 'dnf', 'yum', 'zypper'])):
        return True

    return False


def install_ntp(install_func, packages=None, check_exe="ntpd"):
    if util.which(check_exe):
        return
    if packages is None:
        packages = ['ntp']

    install_func(packages)


def rename_ntp_conf(config=None):
    """Rename any existing ntp.conf file"""
    if config is None:  # For testing
        config = NTP_CONF
    if os.path.exists(config):
        util.rename(config, config + ".dist")


def generate_server_names(distro):
    names = []
    pool_distro = distro
    # For legal reasons x.pool.sles.ntp.org does not exist,
    # use the opensuse pool
    if distro == 'sles':
        pool_distro = 'opensuse'
    for x in range(0, NR_POOL_SERVERS):
        name = "%d.%s.pool.ntp.org" % (x, pool_distro)
        names.append(name)
    return names


def write_ntp_config_template(cfg, cloud, path, template=None):
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

    if template is None:
        template = 'ntp.conf.%s' % cloud.distro.name

    template_fn = cloud.get_template_filename(template)
    if not template_fn:
        template_fn = cloud.get_template_filename('ntp.conf')
        if not template_fn:
            raise RuntimeError(
                'No template found, not rendering {path}'.format(path=path))

    templater.render_to_file(template_fn, path, params)


def reload_ntp(service, systemd=False):
    if systemd:
        cmd = ['systemctl', 'reload-or-restart', service]
    else:
        cmd = ['service', service, 'restart']
    util.subp(cmd, capture=True)


# vi: ts=4 expandtab
