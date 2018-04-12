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
from cloudinit import temp_utils
from cloudinit import templater
from cloudinit import type_utils
from cloudinit import util

import copy
import os
import six
from textwrap import dedent

LOG = logging.getLogger(__name__)

frequency = PER_INSTANCE
NTP_CONF = '/etc/ntp.conf'
NR_POOL_SERVERS = 4
distros = ['centos', 'debian', 'fedora', 'opensuse', 'rhel', 'sles', 'ubuntu']

NTP_CLIENT_CONFIG = {
    'chrony': {
        'check_exe': 'chronyd',
        'confpath': '/etc/chrony.conf',
        'packages': ['chrony'],
        'service_name': 'chrony',
        'template_name': 'chrony.conf.{distro}',
        'template': None,
    },
    'ntp': {
        'check_exe': 'ntpd',
        'confpath': NTP_CONF,
        'packages': ['ntp'],
        'service_name': 'ntp',
        'template_name': 'ntp.conf.{distro}',
        'template': None,
    },
    'ntpdate': {
        'check_exe': 'ntpdate',
        'confpath': NTP_CONF,
        'packages': ['ntpdate'],
        'service_name': 'ntpdate',
        'template_name': 'ntp.conf.{distro}',
        'template': None,
    },
    'systemd-timesyncd': {
        'check_exe': '/lib/systemd/systemd-timesyncd',
        'confpath': '/etc/systemd/timesyncd.conf.d/cloud-init.conf',
        'packages': [],
        'service_name': 'systemd-timesyncd',
        'template_name': 'timesyncd.conf',
        'template': None,
    },
}

# This is Distro-specific configuration overrides of the base config
DISTRO_CLIENT_CONFIG = {
    'debian': {
        'chrony': {
            'confpath': '/etc/chrony/chrony.conf',
        },
    },
    'opensuse': {
        'chrony': {
            'service_name': 'chronyd',
        },
        'ntp': {
            'confpath': '/etc/ntp.conf',
            'service_name': 'ntpd',
        },
        'systemd-timesyncd': {
            'check_exe': '/usr/lib/systemd/systemd-timesyncd',
        },
    },
    'sles': {
        'chrony': {
            'service_name': 'chronyd',
        },
        'ntp': {
            'confpath': '/etc/ntp.conf',
            'service_name': 'ntpd',
        },
        'systemd-timesyncd': {
            'check_exe': '/usr/lib/systemd/systemd-timesyncd',
        },
    },
    'ubuntu': {
        'chrony': {
            'confpath': '/etc/chrony/chrony.conf',
        },
    },
}


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
        # Override ntp with chrony configuration on Ubuntu
        ntp:
          enabled: true
          ntp_client: chrony  # Uses cloud-init default chrony configuration
        """),
        dedent("""\
        # Provide a custom ntp client configuration
        ntp:
          enabled: true
          ntp_client: myntpclient
          config:
             confpath: /etc/myntpclient/myntpclient.conf
             check_exe: myntpclientd
             packages:
               - myntpclient
             service_name: myntpclient
             template: |
                 ## template:jinja
                 # My NTP Client config
                 {% if pools -%}# pools{% endif %}
                 {% for pool in pools -%}
                 pool {{pool}} iburst
                 {% endfor %}
                 {%- if servers %}# servers
                 {% endif %}
                 {% for server in servers -%}
                 server {{server}} iburst
                 {% endfor %}
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
                },
                'ntp_client': {
                    'type': 'string',
                    'default': 'auto',
                    'description': dedent("""\
                        Name of an NTP client to use to configure system NTP.
                         When unprovided or 'auto' the default client preferred
                         by the distribution will be used. The following
                         built-in client names can be used to override existing
                         configuration defaults: chrony, ntp, ntpdate,
                         systemd-timesyncd."""),
                },
                'enabled': {
                    'type': 'boolean',
                    'default': True,
                    'description': dedent("""\
                        Attempt to enable ntp clients if set to True.  If set
                         to False, ntp client will not be configured or
                         installed"""),
                },
                'config': {
                    'description': dedent("""\
                        Configuration settings or overrides for the
                         ``ntp_client`` specified."""),
                    'type': ['object'],
                    'properties': {
                        'confpath': {
                            'type': 'string',
                            'description': dedent("""\
                                The path to where the ``ntp_client``
                                 configuration is written."""),
                        },
                        'check_exe': {
                            'type': 'string',
                            'description': dedent("""\
                                The executable name for the ``ntp_client``.
                                 For example, ntp service ``check_exe`` is
                                 'ntpd' because it runs the ntpd binary."""),
                        },
                        'packages': {
                            'type': 'array',
                            'items': {
                                'type': 'string',
                            },
                            'uniqueItems': True,
                            'description': dedent("""\
                                List of packages needed to be installed for the
                                 selected ``ntp_client``."""),
                        },
                        'service_name': {
                            'type': 'string',
                            'description': dedent("""\
                                The systemd or sysvinit service name used to
                                 start and stop the ``ntp_client``
                                 service."""),
                        },
                        'template': {
                            'type': 'string',
                            'description': dedent("""\
                                Inline template allowing users to define their
                                 own ``ntp_client`` configuration template.
                                 The value must start with '## template:jinja'
                                 to enable use of templating support.
                                """),
                        },
                    },
                    # Don't use REQUIRED_NTP_CONFIG_KEYS to allow for override
                    # of builtin client values.
                    'required': [],
                    'minProperties': 1,  # If we have config, define something
                    'additionalProperties': False
                },
            },
            'required': [],
            'additionalProperties': False
        }
    }
}
REQUIRED_NTP_CONFIG_KEYS = frozenset([
    'check_exe', 'confpath', 'packages', 'service_name'])


__doc__ = get_schema_doc(schema)  # Supplement python help()


def distro_ntp_client_configs(distro):
    """Construct a distro-specific ntp client config dictionary by merging
       distro specific changes into base config.

    @param distro: String providing the distro class name.
    @returns: Dict of distro configurations for ntp clients.
    """
    dcfg = DISTRO_CLIENT_CONFIG
    cfg = copy.copy(NTP_CLIENT_CONFIG)
    if distro in dcfg:
        cfg = util.mergemanydict([cfg, dcfg[distro]], reverse=True)
    return cfg


def select_ntp_client(ntp_client, distro):
    """Determine which ntp client is to be used, consulting the distro
       for its preference.

    @param ntp_client: String name of the ntp client to use.
    @param distro: Distro class instance.
    @returns: Dict of the selected ntp client or {} if none selected.
    """

    # construct distro-specific ntp_client_config dict
    distro_cfg = distro_ntp_client_configs(distro.name)

    # user specified client, return its config
    if ntp_client and ntp_client != 'auto':
        LOG.debug('Selected NTP client "%s" via user-data configuration',
                  ntp_client)
        return distro_cfg.get(ntp_client, {})

    # default to auto if unset in distro
    distro_ntp_client = distro.get_option('ntp_client', 'auto')

    clientcfg = {}
    if distro_ntp_client == "auto":
        for client in distro.preferred_ntp_clients:
            cfg = distro_cfg.get(client)
            if util.which(cfg.get('check_exe')):
                LOG.debug('Selected NTP client "%s", already installed',
                          client)
                clientcfg = cfg
                break

        if not clientcfg:
            client = distro.preferred_ntp_clients[0]
            LOG.debug(
                'Selected distro preferred NTP client "%s", not yet installed',
                client)
            clientcfg = distro_cfg.get(client)
    else:
        LOG.debug('Selected NTP client "%s" via distro system config',
                  distro_ntp_client)
        clientcfg = distro_cfg.get(distro_ntp_client, {})

    return clientcfg


def install_ntp_client(install_func, packages=None, check_exe="ntpd"):
    """Install ntp client package if not already installed.

    @param install_func: function.  This parameter is invoked with the contents
    of the packages parameter.
    @param packages: list.  This parameter defaults to ['ntp'].
    @param check_exe: string.  The name of a binary that indicates the package
    the specified package is already installed.
    """
    if util.which(check_exe):
        return
    if packages is None:
        packages = ['ntp']

    install_func(packages)


def rename_ntp_conf(confpath=None):
    """Rename any existing ntp client config file

    @param confpath: string. Specify a path to an existing ntp client
    configuration file.
    """
    if os.path.exists(confpath):
        util.rename(confpath, confpath + ".dist")


def generate_server_names(distro):
    """Generate a list of server names to populate an ntp client configuration
    file.

    @param distro: string.  Specify the distro name
    @returns: list: A list of strings representing ntp servers for this distro.
    """
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


def write_ntp_config_template(distro_name, servers=None, pools=None,
                              path=None, template_fn=None, template=None):
    """Render a ntp client configuration for the specified client.

    @param distro_name: string.  The distro class name.
    @param servers: A list of strings specifying ntp servers. Defaults to empty
    list.
    @param pools: A list of strings specifying ntp pools. Defaults to empty
    list.
    @param path: A string to specify where to write the rendered template.
    @param template_fn: A string to specify the template source file.
    @param template: A string specifying the contents of the template. This
    content will be written to a temporary file before being used to render
    the configuration file.

    @raises: ValueError when path is None.
    @raises: ValueError when template_fn is None and template is None.
    """
    if not servers:
        servers = []
    if not pools:
        pools = []

    if len(servers) == 0 and len(pools) == 0:
        pools = generate_server_names(distro_name)
        LOG.debug(
            'Adding distro default ntp pool servers: %s', ','.join(pools))

    if not path:
        raise ValueError('Invalid value for path parameter')

    if not template_fn and not template:
        raise ValueError('Not template_fn or template provided')

    params = {'servers': servers, 'pools': pools}
    if template:
        tfile = temp_utils.mkstemp(prefix='template_name-', suffix=".tmpl")
        template_fn = tfile[1]  # filepath is second item in tuple
        util.write_file(template_fn, content=template)

    templater.render_to_file(template_fn, path, params)
    # clean up temporary template
    if template:
        util.del_file(template_fn)


def reload_ntp(service, systemd=False):
    """Restart or reload an ntp system service.

    @param service: A string specifying the name of the service to be affected.
    @param systemd: A boolean indicating if the distro uses systemd, defaults
    to False.
    @returns: A tuple of stdout, stderr results from executing the action.
    """
    if systemd:
        cmd = ['systemctl', 'reload-or-restart', service]
    else:
        cmd = ['service', service, 'restart']
    util.subp(cmd, capture=True)


def supplemental_schema_validation(ntp_config):
    """Validate user-provided ntp:config option values.

    This function supplements flexible jsonschema validation with specific
    value checks to aid in triage of invalid user-provided configuration.

    @param ntp_config: Dictionary of configuration value under 'ntp'.

    @raises: ValueError describing invalid values provided.
    """
    errors = []
    missing = REQUIRED_NTP_CONFIG_KEYS.difference(set(ntp_config.keys()))
    if missing:
        keys = ', '.join(sorted(missing))
        errors.append(
            'Missing required ntp:config keys: {keys}'.format(keys=keys))
    elif not any([ntp_config.get('template'),
                  ntp_config.get('template_name')]):
        errors.append(
            'Either ntp:config:template or ntp:config:template_name values'
            ' are required')
    for key, value in sorted(ntp_config.items()):
        keypath = 'ntp:config:' + key
        if key == 'confpath':
            if not all([value, isinstance(value, six.string_types)]):
                errors.append(
                    'Expected a config file path {keypath}.'
                    ' Found ({value})'.format(keypath=keypath, value=value))
        elif key == 'packages':
            if not isinstance(value, list):
                errors.append(
                    'Expected a list of required package names for {keypath}.'
                    ' Found ({value})'.format(keypath=keypath, value=value))
        elif key in ('template', 'template_name'):
            if value is None:  # Either template or template_name can be none
                continue
            if not isinstance(value, six.string_types):
                errors.append(
                    'Expected a string type for {keypath}.'
                    ' Found ({value})'.format(keypath=keypath, value=value))
        elif not isinstance(value, six.string_types):
            errors.append(
                'Expected a string type for {keypath}.'
                ' Found ({value})'.format(keypath=keypath, value=value))

    if errors:
        raise ValueError(r'Invalid ntp configuration:\n{errors}'.format(
            errors='\n'.join(errors)))


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

    # Allow users to explicitly enable/disable
    enabled = ntp_cfg.get('enabled', True)
    if util.is_false(enabled):
        LOG.debug("Skipping module named %s, disabled by cfg", name)
        return

    # Select which client is going to be used and get the configuration
    ntp_client_config = select_ntp_client(ntp_cfg.get('ntp_client'),
                                          cloud.distro)

    # Allow user ntp config to override distro configurations
    ntp_client_config = util.mergemanydict(
        [ntp_client_config, ntp_cfg.get('config', {})], reverse=True)

    supplemental_schema_validation(ntp_client_config)
    rename_ntp_conf(confpath=ntp_client_config.get('confpath'))

    template_fn = None
    if not ntp_client_config.get('template'):
        template_name = (
            ntp_client_config.get('template_name').replace('{distro}',
                                                           cloud.distro.name))
        template_fn = cloud.get_template_filename(template_name)
        if not template_fn:
            msg = ('No template found, not rendering %s' %
                   ntp_client_config.get('template_name'))
            raise RuntimeError(msg)

    write_ntp_config_template(cloud.distro.name,
                              servers=ntp_cfg.get('servers', []),
                              pools=ntp_cfg.get('pools', []),
                              path=ntp_client_config.get('confpath'),
                              template_fn=template_fn,
                              template=ntp_client_config.get('template'))

    install_ntp_client(cloud.distro.install_packages,
                       packages=ntp_client_config['packages'],
                       check_exe=ntp_client_config['check_exe'])
    try:
        reload_ntp(ntp_client_config['service_name'],
                   systemd=cloud.distro.uses_systemd())
    except util.ProcessExecutionError as e:
        LOG.exception("Failed to reload/start ntp service: %s", e)
        raise

# vi: ts=4 expandtab
