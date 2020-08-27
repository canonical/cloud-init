# This file is part of cloud-init. See LICENSE file for license information.

"""ubuntu_advantage: Configure Ubuntu Advantage support services"""

from textwrap import dedent

from cloudinit.config.schema import (
    get_schema_doc, validate_cloudconfig_schema)
from cloudinit import log as logging
from cloudinit.settings import PER_INSTANCE
from cloudinit import subp
from cloudinit import util


UA_URL = 'https://ubuntu.com/advantage'

distros = ['ubuntu']

schema = {
    'id': 'cc_ubuntu_advantage',
    'name': 'Ubuntu Advantage',
    'title': 'Configure Ubuntu Advantage support services',
    'description': dedent("""\
        Attach machine to an existing Ubuntu Advantage support contract and
        enable or disable support services such as Livepatch, ESM,
        FIPS and FIPS Updates. When attaching a machine to Ubuntu Advantage,
        one can also specify services to enable.  When the 'enable'
        list is present, any named service will be enabled and all absent
        services will remain disabled.

        Note that when enabling FIPS or FIPS updates you will need to schedule
        a reboot to ensure the machine is running the FIPS-compliant kernel.
        See :ref:`Power State Change` for information on how to configure
        cloud-init to perform this reboot.
        """),
    'distros': distros,
    'examples': [dedent("""\
        # Attach the machine to an Ubuntu Advantage support contract with a
        # UA contract token obtained from %s.
        ubuntu_advantage:
          token: <ua_contract_token>
    """ % UA_URL), dedent("""\
        # Attach the machine to an Ubuntu Advantage support contract enabling
        # only fips and esm services. Services will only be enabled if
        # the environment supports said service. Otherwise warnings will
        # be logged for incompatible services specified.
        ubuntu-advantage:
          token: <ua_contract_token>
          enable:
          - fips
          - esm
    """), dedent("""\
        # Attach the machine to an Ubuntu Advantage support contract and enable
        # the FIPS service.  Perform a reboot once cloud-init has
        # completed.
        power_state:
          mode: reboot
        ubuntu-advantage:
          token: <ua_contract_token>
          enable:
          - fips
        """)],
    'frequency': PER_INSTANCE,
    'type': 'object',
    'properties': {
        'ubuntu_advantage': {
            'type': 'object',
            'properties': {
                'enable': {
                    'type': 'array',
                    'items': {'type': 'string'},
                },
                'token': {
                    'type': 'string',
                    'description': (
                        'A contract token obtained from %s.' % UA_URL)
                }
            },
            'required': ['token'],
            'additionalProperties': False
        }
    }
}

__doc__ = get_schema_doc(schema)  # Supplement python help()

LOG = logging.getLogger(__name__)


def configure_ua(token=None, enable=None):
    """Call ua commandline client to attach or enable services."""
    error = None
    if not token:
        error = ('ubuntu_advantage: token must be provided')
        LOG.error(error)
        raise RuntimeError(error)

    if enable is None:
        enable = []
    elif isinstance(enable, str):
        LOG.warning('ubuntu_advantage: enable should be a list, not'
                    ' a string; treating as a single enable')
        enable = [enable]
    elif not isinstance(enable, list):
        LOG.warning('ubuntu_advantage: enable should be a list, not'
                    ' a %s; skipping enabling services',
                    type(enable).__name__)
        enable = []

    attach_cmd = ['ua', 'attach', token]
    LOG.debug('Attaching to Ubuntu Advantage. %s', ' '.join(attach_cmd))
    try:
        subp.subp(attach_cmd)
    except subp.ProcessExecutionError as e:
        msg = 'Failure attaching Ubuntu Advantage:\n{error}'.format(
            error=str(e))
        util.logexc(LOG, msg)
        raise RuntimeError(msg) from e
    enable_errors = []
    for service in enable:
        try:
            cmd = ['ua', 'enable', service]
            subp.subp(cmd, capture=True)
        except subp.ProcessExecutionError as e:
            enable_errors.append((service, e))
    if enable_errors:
        for service, error in enable_errors:
            msg = 'Failure enabling "{service}":\n{error}'.format(
                service=service, error=str(error))
            util.logexc(LOG, msg)
        raise RuntimeError(
            'Failure enabling Ubuntu Advantage service(s): {}'.format(
                ', '.join('"{}"'.format(service)
                          for service, _ in enable_errors)))


def maybe_install_ua_tools(cloud):
    """Install ubuntu-advantage-tools if not present."""
    if subp.which('ua'):
        return
    try:
        cloud.distro.update_package_sources()
    except Exception:
        util.logexc(LOG, "Package update failed")
        raise
    try:
        cloud.distro.install_packages(['ubuntu-advantage-tools'])
    except Exception:
        util.logexc(LOG, "Failed to install ubuntu-advantage-tools")
        raise


def handle(name, cfg, cloud, log, args):
    ua_section = None
    if 'ubuntu-advantage' in cfg:
        LOG.warning('Deprecated configuration key "ubuntu-advantage" provided.'
                    ' Expected underscore delimited "ubuntu_advantage"; will'
                    ' attempt to continue.')
        ua_section = cfg['ubuntu-advantage']
    if 'ubuntu_advantage' in cfg:
        ua_section = cfg['ubuntu_advantage']
    if ua_section is None:
        LOG.debug("Skipping module named %s,"
                  " no 'ubuntu_advantage' configuration found", name)
        return
    validate_cloudconfig_schema(cfg, schema)
    if 'commands' in ua_section:
        msg = (
            'Deprecated configuration "ubuntu-advantage: commands" provided.'
            ' Expected "token"')
        LOG.error(msg)
        raise RuntimeError(msg)

    maybe_install_ua_tools(cloud)
    configure_ua(token=ua_section.get('token'),
                 enable=ua_section.get('enable'))

# vi: ts=4 expandtab
