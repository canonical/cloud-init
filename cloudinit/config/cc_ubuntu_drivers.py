# This file is part of cloud-init. See LICENSE file for license information.

"""Ubuntu Drivers: Interact with third party drivers in Ubuntu."""

from textwrap import dedent

from cloudinit.config.schema import (
    get_schema_doc, validate_cloudconfig_schema)
from cloudinit import log as logging
from cloudinit.settings import PER_INSTANCE
from cloudinit import type_utils
from cloudinit import util

LOG = logging.getLogger(__name__)

frequency = PER_INSTANCE
distros = ['ubuntu']
schema = {
    'id': 'cc_ubuntu_drivers',
    'name': 'Ubuntu Drivers',
    'title': 'Interact with third party drivers in Ubuntu.',
    'description': dedent("""\
        This module interacts with the 'ubuntu-drivers' command to install
        third party driver packages."""),
    'distros': distros,
    'examples': [dedent("""\
        drivers:
          nvidia:
            license-accepted: true
        """)],
    'frequency': frequency,
    'type': 'object',
    'properties': {
        'drivers': {
            'type': 'object',
            'additionalProperties': False,
            'properties': {
                'nvidia': {
                    'type': 'object',
                    'additionalProperties': False,
                    'required': ['license-accepted'],
                    'properties': {
                        'license-accepted': {
                            'type': 'boolean',
                            'description': ("Do you accept the NVIDIA driver"
                                            " license?"),
                        },
                        'version': {
                            'type': 'string',
                            'description': (
                                'The version of the driver to install (e.g.'
                                ' "390", "410"). Defaults to the latest'
                                ' version.'),
                        },
                    },
                },
            },
        },
    },
}
OLD_UBUNTU_DRIVERS_STDERR_NEEDLE = (
    "ubuntu-drivers: error: argument <command>: invalid choice: 'install'")

__doc__ = get_schema_doc(schema)  # Supplement python help()


def install_drivers(cfg, pkg_install_func):
    if not isinstance(cfg, dict):
        raise TypeError(
            "'drivers' config expected dict, found '%s': %s" %
            (type_utils.obj_name(cfg), cfg))

    cfgpath = 'nvidia/license-accepted'
    # Call translate_bool to ensure that we treat string values like "yes" as
    # acceptance and _don't_ treat string values like "nah" as acceptance
    # because they're True-ish
    nv_acc = util.translate_bool(util.get_cfg_by_path(cfg, cfgpath))
    if not nv_acc:
        LOG.debug("Not installing NVIDIA drivers. %s=%s", cfgpath, nv_acc)
        return

    if not util.which('ubuntu-drivers'):
        LOG.debug("'ubuntu-drivers' command not available.  "
                  "Installing ubuntu-drivers-common")
        pkg_install_func(['ubuntu-drivers-common'])

    driver_arg = 'nvidia'
    version_cfg = util.get_cfg_by_path(cfg, 'nvidia/version')
    if version_cfg:
        driver_arg += ':{}'.format(version_cfg)

    LOG.debug("Installing NVIDIA drivers (%s=%s, version=%s)",
              cfgpath, nv_acc, version_cfg if version_cfg else 'latest')

    try:
        util.subp(['ubuntu-drivers', 'install', '--gpgpu', driver_arg])
    except util.ProcessExecutionError as exc:
        if OLD_UBUNTU_DRIVERS_STDERR_NEEDLE in exc.stderr:
            LOG.warning('the available version of ubuntu-drivers is'
                        ' too old to perform requested driver installation')
        elif 'No drivers found for installation.' in exc.stdout:
            LOG.warning('ubuntu-drivers found no drivers for installation')
        raise


def handle(name, cfg, cloud, log, _args):
    if "drivers" not in cfg:
        log.debug("Skipping module named %s, no 'drivers' key in config", name)
        return

    validate_cloudconfig_schema(cfg, schema)
    install_drivers(cfg['drivers'], cloud.distro.install_packages)
