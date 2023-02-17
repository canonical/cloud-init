# Author: Mike Milner <mike.milner@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""CA Certs: Add ca certificates."""

import os
from logging import Logger
from textwrap import dedent

from cloudinit import log as logging
from cloudinit import subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.settings import PER_INSTANCE

LOG = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "ca_cert_path": None,
    "ca_cert_local_path": "/usr/local/share/ca-certificates/",
    "ca_cert_filename": "cloud-init-ca-cert-{cert_index}.crt",
    "ca_cert_config": "/etc/ca-certificates.conf",
    "ca_cert_update_cmd": ["update-ca-certificates"],
}
DISTRO_OVERRIDES = {
    "rhel": {
        "ca_cert_path": "/etc/pki/ca-trust/",
        "ca_cert_local_path": "/usr/share/pki/ca-trust-source/",
        "ca_cert_filename": "anchors/cloud-init-ca-cert-{cert_index}.crt",
        "ca_cert_config": None,
        "ca_cert_update_cmd": ["update-ca-trust"],
    },
}

MODULE_DESCRIPTION = """\
This module adds CA certificates to the system's CA store and updates any
related files using the appropriate OS-specific utility. The default CA
certificates can be disabled/deleted from use by the system with the
configuration option ``remove_defaults``.

.. note::
    certificates must be specified using valid yaml. in order to specify a
    multiline certificate, the yaml multiline list syntax must be used

.. note::
    Alpine Linux requires the ca-certificates package to be installed in
    order to provide the ``update-ca-certificates`` command.
"""
distros = ["alpine", "debian", "rhel", "ubuntu"]

meta: MetaSchema = {
    "id": "cc_ca_certs",
    "name": "CA Certificates",
    "title": "Add ca certificates",
    "description": MODULE_DESCRIPTION,
    "distros": distros,
    "frequency": PER_INSTANCE,
    "examples": [
        dedent(
            """\
            ca_certs:
              remove_defaults: true
              trusted:
                - single_line_cert
                - |
                  -----BEGIN CERTIFICATE-----
                  YOUR-ORGS-TRUSTED-CA-CERT-HERE
                  -----END CERTIFICATE-----
            """
        )
    ],
    "activate_by_schema_keys": ["ca_certs", "ca-certs"],
}

__doc__ = get_meta_doc(meta)


def _distro_ca_certs_configs(distro_name):
    """Return a distro-specific ca_certs config dictionary

    @param distro_name: String providing the distro class name.
    @returns: Dict of distro configurations for ca_cert.
    """
    cfg = DISTRO_OVERRIDES.get(distro_name, DEFAULT_CONFIG)
    cfg["ca_cert_full_path"] = os.path.join(
        cfg["ca_cert_local_path"], cfg["ca_cert_filename"]
    )
    return cfg


def update_ca_certs(distro_cfg):
    """
    Updates the CA certificate cache on the current machine.

    @param distro_cfg: A hash providing _distro_ca_certs_configs function.
    """
    subp.subp(distro_cfg["ca_cert_update_cmd"], capture=False)


def add_ca_certs(distro_cfg, certs):
    """
    Adds certificates to the system. To actually apply the new certificates
    you must also call the appropriate distro-specific utility such as
    L{update_ca_certs}.

    @param distro_cfg: A hash providing _distro_ca_certs_configs function.
    @param certs: A list of certificate strings.
    """
    if not certs:
        return
    # Write each certificate to a separate file.
    for cert_index, c in enumerate(certs, 1):
        # First ensure they are strings...
        cert_file_contents = str(c)
        cert_file_name = distro_cfg["ca_cert_full_path"].format(
            cert_index=cert_index
        )
        util.write_file(cert_file_name, cert_file_contents, mode=0o644)


def disable_default_ca_certs(distro_name, distro_cfg):
    """
    Disables all default trusted CA certificates. For Alpine, Debian and
    Ubuntu to actually apply the changes you must also call
    L{update_ca_certs}.

    @param distro_name: String providing the distro class name.
    @param distro_cfg: A hash providing _distro_ca_certs_configs function.
    """
    if distro_name == "rhel":
        remove_default_ca_certs(distro_cfg)
    elif distro_name in ["alpine", "debian", "ubuntu"]:
        disable_system_ca_certs(distro_cfg)

        if distro_name in ["debian", "ubuntu"]:
            debconf_sel = (
                "ca-certificates ca-certificates/trust_new_crts " + "select no"
            )
            subp.subp(("debconf-set-selections", "-"), debconf_sel)


def disable_system_ca_certs(distro_cfg):
    """
    For every entry in the CA_CERT_CONFIG file prefix the entry with a "!"
    in order to disable it.

    @param distro_cfg: A hash providing _distro_ca_certs_configs function.
    """
    if distro_cfg["ca_cert_config"] is None:
        return
    header_comment = (
        "# Modified by cloud-init to deselect certs due to user-data"
    )
    added_header = False
    if os.stat(distro_cfg["ca_cert_config"]).st_size != 0:
        orig = util.load_file(distro_cfg["ca_cert_config"])
        out_lines = []
        for line in orig.splitlines():
            if line == header_comment:
                added_header = True
                out_lines.append(line)
            elif line == "" or line[0] in ("#", "!"):
                out_lines.append(line)
            else:
                if not added_header:
                    out_lines.append(header_comment)
                    added_header = True
                out_lines.append("!" + line)
    util.write_file(
        distro_cfg["ca_cert_config"], "\n".join(out_lines) + "\n", omode="wb"
    )


def remove_default_ca_certs(distro_cfg):
    """
    Removes all default trusted CA certificates from the system.

    @param distro_cfg: A hash providing _distro_ca_certs_configs function.
    """
    if distro_cfg["ca_cert_path"] is None:
        return

    LOG.debug("Deleting system CA certificates")
    util.delete_dir_contents(distro_cfg["ca_cert_path"])
    util.delete_dir_contents(distro_cfg["ca_cert_local_path"])


def handle(
    name: str, cfg: Config, cloud: Cloud, log: Logger, args: list
) -> None:
    """
    Call to handle ca_cert sections in cloud-config file.

    @param name: The module name "ca_cert" from cloud.cfg
    @param cfg: A nested dict containing the entire cloud config contents.
    @param cloud: The L{CloudInit} object in use.
    @param log: Pre-initialized Python logger object to use for logging.
    @param args: Any module arguments from cloud.cfg
    """
    if "ca-certs" in cfg:
        LOG.warning(
            "DEPRECATION: key 'ca-certs' is now deprecated. Use 'ca_certs'"
            " instead."
        )
    elif "ca_certs" not in cfg:
        LOG.debug(
            "Skipping module named %s, no 'ca_certs' key in configuration",
            name,
        )
        return

    if "ca-certs" in cfg and "ca_certs" in cfg:
        LOG.warning(
            "Found both ca-certs (deprecated) and ca_certs config keys."
            " Ignoring ca-certs."
        )
    ca_cert_cfg = cfg.get("ca_certs", cfg.get("ca-certs"))
    distro_cfg = _distro_ca_certs_configs(cloud.distro.name)

    # If there is a remove_defaults option set to true, disable the system
    # default trusted CA certs first.
    if "remove-defaults" in ca_cert_cfg:
        LOG.warning(
            "DEPRECATION: key 'ca-certs.remove-defaults' is now deprecated."
            " Use 'ca_certs.remove_defaults' instead."
        )
    if ca_cert_cfg.get(
        "remove_defaults", ca_cert_cfg.get("remove-defaults", False)
    ):
        LOG.debug("Disabling/removing default certificates")
        disable_default_ca_certs(cloud.distro.name, distro_cfg)

    # If we are given any new trusted CA certs to add, add them.
    if "trusted" in ca_cert_cfg:
        trusted_certs = util.get_cfg_option_list(ca_cert_cfg, "trusted")
        if trusted_certs:
            LOG.debug("Adding %d certificates", len(trusted_certs))
            add_ca_certs(distro_cfg, trusted_certs)

    # Update the system with the new cert configuration.
    LOG.debug("Updating certificates")
    update_ca_certs(distro_cfg)


# vi: ts=4 expandtab
