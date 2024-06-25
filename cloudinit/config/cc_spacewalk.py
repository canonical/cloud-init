# This file is part of cloud-init. See LICENSE file for license information.
"""Spacewalk: Install and configure spacewalk"""

import logging

from cloudinit import subp
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.settings import PER_INSTANCE

meta: MetaSchema = {
    "id": "cc_spacewalk",
    "distros": ["rhel", "fedora", "openeuler"],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": ["spacewalk"],
}  # type: ignore

LOG = logging.getLogger(__name__)

distros = ["redhat", "fedora"]
required_packages = ["rhn-setup"]
def_ca_cert_path = "/usr/share/rhn/RHN-ORG-TRUSTED-SSL-CERT"


def is_registered():
    # Check to see if already registered and don't bother; this is
    # apparently done by trying to sync and if that fails then we
    # assume we aren't registered; which is sorta ghetto...
    already_registered = False
    try:
        subp.subp(["rhn-profile-sync", "--verbose"], capture=False)
        already_registered = True
    except subp.ProcessExecutionError as e:
        if e.exit_code != 1:
            raise
    return already_registered


def do_register(
    server,
    profile_name,
    ca_cert_path=def_ca_cert_path,
    proxy=None,
    activation_key=None,
):
    LOG.info(
        "Registering using `rhnreg_ks` profile '%s' into server '%s'",
        profile_name,
        server,
    )
    cmd = ["rhnreg_ks"]
    cmd.extend(["--serverUrl", "https://%s/XMLRPC" % server])
    cmd.extend(["--profilename", str(profile_name)])
    if proxy:
        cmd.extend(["--proxy", str(proxy)])
    if ca_cert_path:
        cmd.extend(["--sslCACert", str(ca_cert_path)])
    if activation_key:
        cmd.extend(["--activationkey", str(activation_key)])
    subp.subp(cmd, capture=False)


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    if "spacewalk" not in cfg:
        LOG.debug(
            "Skipping module named %s, no 'spacewalk' key in configuration",
            name,
        )
        return
    cfg = cfg["spacewalk"]
    spacewalk_server = cfg.get("server")
    if spacewalk_server:
        # Need to have this installed before further things will work.
        cloud.distro.install_packages(required_packages)
        if not is_registered():
            do_register(
                spacewalk_server,
                cloud.datasource.get_hostname(fqdn=True).hostname,
                proxy=cfg.get("proxy"),
                activation_key=cfg.get("activation_key"),
            )
    else:
        LOG.debug(
            "Skipping module named %s, 'spacewalk/server' key"
            " was not found in configuration",
            name,
        )
