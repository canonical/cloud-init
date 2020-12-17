# Author: Mike Milner <mike.milner@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""
CA Certs
--------
**Summary:** add ca certificates

This module adds CA certificates to ``/etc/ca-certificates.conf`` and updates
the ssl cert cache using ``update-ca-certificates``. The default certificates
can be removed from the system with the configuration option
``remove-defaults``.

.. note::
    certificates must be specified using valid yaml. in order to specify a
    multiline certificate, the yaml multiline list syntax must be used

.. note::
    For Alpine Linux the "remove-defaults" functionality works if the
    ca-certificates package is installed but not if the
    ca-certificates-bundle package is installed.

**Internal name:** ``cc_ca_certs``

**Module frequency:** per instance

**Supported distros:** alpine, debian, ubuntu, rhel

**Config keys**::

    ca-certs:
        remove-defaults: <true/false>
        trusted:
            - <single line cert>
            - |
              -----BEGIN CERTIFICATE-----
              YOUR-ORGS-TRUSTED-CA-CERT-HERE
              -----END CERTIFICATE-----
"""

import os

from cloudinit import subp
from cloudinit import util

DEFAULT_CONFIG = {
    'ca_cert_path': '/usr/share/ca-certificates/',
    'ca_cert_filename': 'cloud-init-ca-certs.crt',
    'ca_cert_config': '/etc/ca-certificates.conf',
    'ca_cert_system_path': '/etc/ssl/certs/',
    'ca_cert_update_cmd': ['update-ca-certificates']
}
DISTRO_OVERRIDES = {
    'rhel': {
        'ca_cert_path': '/usr/share/pki/ca-trust-source/',
        'ca_cert_filename': 'anchors/cloud-init-ca-certs.crt',
        'ca_cert_config': None,
        'ca_cert_system_path': '/etc/pki/ca-trust/',
        'ca_cert_update_cmd': ['update-ca-trust']
    }
}


distros = ['alpine', 'debian', 'ubuntu', 'rhel']


def _distro_ca_certs_configs(distro_name):
    """Return a distro-specific ca_certs config dictionary

    @param distro_name: String providing the distro class name.
    @returns: Dict of distro configurations for ca-cert.
    """
    cfg = DISTRO_OVERRIDES.get(distro_name, DEFAULT_CONFIG)
    cfg['ca_cert_full_path'] = os.path.join(cfg['ca_cert_path'],
                                            cfg['ca_cert_filename'])
    return cfg


def update_ca_certs(distro_cfg):
    """
    Updates the CA certificate cache on the current machine.

    @param distro_cfg: A hash providing _distro_ca_certs_configs function.
    """
    subp.subp(distro_cfg['ca_cert_update_cmd'], capture=False)


def add_ca_certs(distro_cfg, certs):
    """
    Adds certificates to the system. To actually apply the new certificates
    you must also call L{update_ca_certs}.

    @param distro_cfg: A hash providing _distro_ca_certs_configs function.
    @param certs: A list of certificate strings.
    """
    if not certs:
        return
    # First ensure they are strings...
    cert_file_contents = "\n".join([str(c) for c in certs])
    util.write_file(distro_cfg['ca_cert_full_path'],
                    cert_file_contents,
                    mode=0o644)
    update_cert_config(distro_cfg)


def update_cert_config(distro_cfg):
    """
    Update Certificate config file to add the file path managed cloud-init

    @param distro_cfg: A hash providing _distro_ca_certs_configs function.
    """
    if distro_cfg['ca_cert_config'] is None:
        return
    if os.stat(distro_cfg['ca_cert_config']).st_size == 0:
        # If the CA_CERT_CONFIG file is empty (i.e. all existing
        # CA certs have been deleted) then simply output a single
        # line with the cloud-init cert filename.
        out = "%s\n" % distro_cfg['ca_cert_filename']
    else:
        # Append cert filename to CA_CERT_CONFIG file.
        # We have to strip the content because blank lines in the file
        # causes subsequent entries to be ignored. (LP: #1077020)
        orig = util.load_file(distro_cfg['ca_cert_config'])
        cr_cont = '\n'.join([line for line in orig.splitlines()
                            if line != distro_cfg['ca_cert_filename']])
        out = "%s\n%s\n" % (cr_cont.rstrip(),
                            distro_cfg['ca_cert_filename'])
    util.write_file(distro_cfg['ca_cert_config'], out, omode="wb")


def remove_default_ca_certs(distro_name, distro_cfg):
    """
    Removes all default trusted CA certificates from the system. To actually
    apply the change you must also call L{update_ca_certs}.

    @param distro_name: String providing the distro class name.
    @param distro_cfg: A hash providing _distro_ca_certs_configs function.
    """
    util.delete_dir_contents(distro_cfg['ca_cert_path'])
    util.delete_dir_contents(distro_cfg['ca_cert_system_path'])
    util.write_file(distro_cfg['ca_cert_config'], "", mode=0o644)

    if distro_name in ['debian', 'ubuntu']:
        debconf_sel = (
            "ca-certificates ca-certificates/trust_new_crts " + "select no")
        subp.subp(('debconf-set-selections', '-'), debconf_sel)


def handle(name, cfg, cloud, log, _args):
    """
    Call to handle ca-cert sections in cloud-config file.

    @param name: The module name "ca-cert" from cloud.cfg
    @param cfg: A nested dict containing the entire cloud config contents.
    @param cloud: The L{CloudInit} object in use.
    @param log: Pre-initialized Python logger object to use for logging.
    @param args: Any module arguments from cloud.cfg
    """
    # If there isn't a ca-certs section in the configuration don't do anything
    if "ca-certs" not in cfg:
        log.debug(("Skipping module named %s,"
                   " no 'ca-certs' key in configuration"), name)
        return

    ca_cert_cfg = cfg['ca-certs']
    distro_cfg = _distro_ca_certs_configs(cloud.distro.name)

    # If there is a remove-defaults option set to true, remove the system
    # default trusted CA certs first.
    if ca_cert_cfg.get("remove-defaults", False):
        log.debug("Removing default certificates")
        remove_default_ca_certs(cloud.distro.name, distro_cfg)

    # If we are given any new trusted CA certs to add, add them.
    if "trusted" in ca_cert_cfg:
        trusted_certs = util.get_cfg_option_list(ca_cert_cfg, "trusted")
        if trusted_certs:
            log.debug("Adding %d certificates" % len(trusted_certs))
            add_ca_certs(distro_cfg, trusted_certs)

    # Update the system with the new cert configuration.
    log.debug("Updating certificates")
    update_ca_certs(distro_cfg)

# vi: ts=4 expandtab
