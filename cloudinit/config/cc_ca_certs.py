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

**Supported distros:** alpine, debian, ubuntu

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

CA_CERT_PATH = "/usr/share/ca-certificates/"
CA_CERT_FILENAME = "cloud-init-ca-certs.crt"
CA_CERT_CONFIG = "/etc/ca-certificates.conf"
CA_CERT_SYSTEM_PATH = "/etc/ssl/certs/"
CA_CERT_FULL_PATH = os.path.join(CA_CERT_PATH, CA_CERT_FILENAME)

distros = ['alpine', 'debian', 'ubuntu']


def update_ca_certs():
    """
    Updates the CA certificate cache on the current machine.
    """
    subp.subp(["update-ca-certificates"], capture=False)


def add_ca_certs(certs):
    """
    Adds certificates to the system. To actually apply the new certificates
    you must also call L{update_ca_certs}.

    @param certs: A list of certificate strings.
    """
    if certs:
        # First ensure they are strings...
        cert_file_contents = "\n".join([str(c) for c in certs])
        util.write_file(CA_CERT_FULL_PATH, cert_file_contents, mode=0o644)

        if os.stat(CA_CERT_CONFIG).st_size == 0:
            # If the CA_CERT_CONFIG file is empty (i.e. all existing
            # CA certs have been deleted) then simply output a single
            # line with the cloud-init cert filename.
            out = "%s\n" % CA_CERT_FILENAME
        else:
            # Append cert filename to CA_CERT_CONFIG file.
            # We have to strip the content because blank lines in the file
            # causes subsequent entries to be ignored. (LP: #1077020)
            orig = util.load_file(CA_CERT_CONFIG)
            cur_cont = '\n'.join([line for line in orig.splitlines()
                                  if line != CA_CERT_FILENAME])
            out = "%s\n%s\n" % (cur_cont.rstrip(), CA_CERT_FILENAME)
        util.write_file(CA_CERT_CONFIG, out, omode="wb")


def remove_default_ca_certs(distro_name):
    """
    Removes all default trusted CA certificates from the system. To actually
    apply the change you must also call L{update_ca_certs}.
    """
    util.delete_dir_contents(CA_CERT_PATH)
    util.delete_dir_contents(CA_CERT_SYSTEM_PATH)
    util.write_file(CA_CERT_CONFIG, "", mode=0o644)

    if distro_name != 'alpine':
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

    # If there is a remove-defaults option set to true, remove the system
    # default trusted CA certs first.
    if ca_cert_cfg.get("remove-defaults", False):
        log.debug("Removing default certificates")
        remove_default_ca_certs(cloud.distro.name)

    # If we are given any new trusted CA certs to add, add them.
    if "trusted" in ca_cert_cfg:
        trusted_certs = util.get_cfg_option_list(ca_cert_cfg, "trusted")
        if trusted_certs:
            log.debug("Adding %d certificates" % len(trusted_certs))
            add_ca_certs(trusted_certs)

    # Update the system with the new cert configuration.
    log.debug("Updating certificates")
    update_ca_certs()

# vi: ts=4 expandtab
