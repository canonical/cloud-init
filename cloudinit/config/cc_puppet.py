# Copyright (C) 2009-2010 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Puppet: Install, configure and start puppet"""

import logging
import os
import socket
from contextlib import suppress
from io import StringIO
from textwrap import dedent
from typing import List, Union

import yaml

from cloudinit import helpers, subp, temp_utils, url_helper, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.distros import ALL_DISTROS, Distro, PackageInstallerError
from cloudinit.settings import PER_INSTANCE

AIO_INSTALL_URL = "https://raw.githubusercontent.com/puppetlabs/install-puppet/main/install.sh"  # noqa: E501
PUPPET_AGENT_DEFAULT_ARGS = ["--test"]
PUPPET_PACKAGE_NAMES = ("puppet-agent", "puppet")

MODULE_DESCRIPTION = """\
This module handles puppet installation and configuration. If the ``puppet``
key does not exist in global configuration, no action will be taken. If a
config entry for ``puppet`` is present, then by default the latest version of
puppet will be installed. If the ``puppet`` config key exists in the config
archive, this module will attempt to start puppet even if no installation was
performed.

The module also provides keys for configuring the new puppet 4 paths and
installing the puppet package from the puppetlabs repositories:
https://docs.puppet.com/puppet/4.2/reference/whered_it_go.html
The keys are ``package_name``, ``conf_file``, ``ssl_dir`` and
``csr_attributes_path``. If unset, their values will default to
ones that work with puppet 3.x and with distributions that ship modified
puppet 4.x that uses the old paths.
"""

meta: MetaSchema = {
    "id": "cc_puppet",
    "name": "Puppet",
    "title": "Install, configure and start puppet",
    "description": MODULE_DESCRIPTION,
    "distros": [ALL_DISTROS],
    "frequency": PER_INSTANCE,
    "examples": [
        dedent(
            """\
            puppet:
                install: true
                version: "7.7.0"
                install_type: "aio"
                collection: "puppet7"
                aio_install_url: 'https://git.io/JBhoQ'
                cleanup: true
                conf_file: "/etc/puppet/puppet.conf"
                ssl_dir: "/var/lib/puppet/ssl"
                csr_attributes_path: "/etc/puppet/csr_attributes.yaml"
                exec: true
                exec_args: ['--test']
                conf:
                    agent:
                        server: "puppetserver.example.org"
                        certname: "%i.%f"
                    ca_cert: |
                        -----BEGIN CERTIFICATE-----
                        MIICCTCCAXKgAwIBAgIBATANBgkqhkiG9w0BAQUFADANMQswCQYDVQQDDAJjYTAe
                        Fw0xMDAyMTUxNzI5MjFaFw0xNTAyMTQxNzI5MjFaMA0xCzAJBgNVBAMMAmNhMIGf
                        MA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCu7Q40sm47/E1Pf+r8AYb/V/FWGPgc
                        b014OmNoX7dgCxTDvps/h8Vw555PdAFsW5+QhsGr31IJNI3kSYprFQcYf7A8tNWu
                        1MASW2CfaEiOEi9F1R3R4Qlz4ix+iNoHiUDTjazw/tZwEdxaQXQVLwgTGRwVa+aA
                        qbutJKi93MILLwIDAQABo3kwdzA4BglghkgBhvhCAQ0EKxYpUHVwcGV0IFJ1Ynkv
                        T3BlblNTTCBHZW5lcmF0ZWQgQ2VydGlmaWNhdGUwDwYDVR0TAQH/BAUwAwEB/zAd
                        BgNVHQ4EFgQUu4+jHB+GYE5Vxo+ol1OAhevspjAwCwYDVR0PBAQDAgEGMA0GCSqG
                        SIb3DQEBBQUAA4GBAH/rxlUIjwNb3n7TXJcDJ6MMHUlwjr03BDJXKb34Ulndkpaf
                        +GAlzPXWa7bO908M9I8RnPfvtKnteLbvgTK+h+zX1XCty+S2EQWk29i2AdoqOTxb
                        hppiGMp0tT5Havu4aceCXiy2crVcudj3NFciy8X66SoECemW9UYDCb9T5D0d
                        -----END CERTIFICATE-----
                csr_attributes:
                    custom_attributes:
                        1.2.840.113549.1.9.7: 342thbjkt82094y0uthhor289jnqthpc2290
                    extension_requests:
                        pp_uuid: ED803750-E3C7-44F5-BB08-41A04433FE2E
                        pp_image_name: my_ami_image
                        pp_preshared_key: 342thbjkt82094y0uthhor289jnqthpc2290
            """  # noqa: E501
        ),
        dedent(
            """\
            puppet:
                install_type: "packages"
                package_name: "puppet"
                exec: false
            """
        ),
    ],
    "activate_by_schema_keys": ["puppet"],
}

__doc__ = get_meta_doc(meta)

LOG = logging.getLogger(__name__)


class PuppetConstants:
    def __init__(
        self,
        puppet_conf_file,
        puppet_ssl_dir,
        csr_attributes_path,
    ):
        self.conf_path = puppet_conf_file
        self.ssl_dir = puppet_ssl_dir
        self.ssl_cert_dir = os.path.join(puppet_ssl_dir, "certs")
        self.ssl_cert_path = os.path.join(self.ssl_cert_dir, "ca.pem")
        self.csr_attributes_path = csr_attributes_path


def _manage_puppet_services(cloud: Cloud, action: str):
    """Attempts to perform action on one of the puppet services"""
    service_managed: str = ""
    for puppet_name in PUPPET_PACKAGE_NAMES:
        try:
            cloud.distro.manage_service(action, f"{puppet_name}.service")
            service_managed = puppet_name
            break
        except subp.ProcessExecutionError:
            pass
    if not service_managed:
        LOG.warning(
            "Could not '%s' any of the following services: %s",
            action,
            ", ".join(PUPPET_PACKAGE_NAMES),
        )


def get_config_value(puppet_bin, setting):
    """Get the config value for a given setting using `puppet config print`
    :param puppet_bin: path to puppet binary
    :param setting: setting to query
    """
    out, _ = subp.subp([puppet_bin, "config", "print", setting])
    return out.rstrip()


def install_puppet_aio(
    distro: Distro,
    url=AIO_INSTALL_URL,
    version=None,
    collection=None,
    cleanup=True,
):
    """Install puppet-agent from the puppetlabs repositories using the one-shot
    shell script

    :param distro: Instance of Distro
    :param url: URL from where to download the install script
    :param version: version to install, blank defaults to latest
    :param collection: collection to install, blank defaults to latest
    :param cleanup: whether to purge the puppetlabs repo after installation
    """
    args = []
    if version is not None:
        args = ["-v", version]
    if collection is not None:
        args += ["-c", collection]

    # Purge puppetlabs repos after installation
    if cleanup:
        args += ["--cleanup"]
    content = url_helper.readurl(url=url, retries=5).contents

    # Use tmpdir over tmpfile to avoid 'text file busy' on execute
    with temp_utils.tempdir(
        dir=distro.get_tmp_exec_path(), needs_exe=True
    ) as tmpd:
        tmpf = os.path.join(tmpd, "puppet-install")
        util.write_file(tmpf, content, mode=0o700)
        return subp.subp([tmpf] + args, capture=False)


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    # If there isn't a puppet key in the configuration don't do anything
    if "puppet" not in cfg:
        LOG.debug(
            "Skipping module named %s, no 'puppet' configuration found", name
        )
        return

    puppet_cfg = cfg["puppet"]
    # Start by installing the puppet package if necessary...
    install = util.get_cfg_option_bool(puppet_cfg, "install", True)
    version = util.get_cfg_option_str(puppet_cfg, "version", None)
    collection = util.get_cfg_option_str(puppet_cfg, "collection", None)
    install_type = util.get_cfg_option_str(
        puppet_cfg, "install_type", "packages"
    )
    cleanup = util.get_cfg_option_bool(puppet_cfg, "cleanup", True)
    run = util.get_cfg_option_bool(puppet_cfg, "exec", default=False)
    start_puppetd = util.get_cfg_option_bool(
        puppet_cfg, "start_service", default=True
    )
    aio_install_url = util.get_cfg_option_str(
        puppet_cfg, "aio_install_url", default=AIO_INSTALL_URL
    )

    # AIO and distro packages use different paths
    if install_type == "aio":
        puppet_user = "root"
        puppet_bin = "/opt/puppetlabs/bin/puppet"
        puppet_package = "puppet-agent"
    else:  # default to 'packages'
        puppet_user = "puppet"
        puppet_bin = "puppet"
        puppet_package = None  # changes with distro

    package_name = util.get_cfg_option_str(
        puppet_cfg, "package_name", puppet_package
    )
    if not install and version:
        LOG.warning(
            "Puppet install set to false but version supplied, doing nothing."
        )
    elif install:
        LOG.debug(
            "Attempting to install puppet %s from %s",
            version if version else "latest",
            install_type,
        )

        if install_type == "packages":
            to_install: List[Union[str, List[str]]]
            if package_name is None:  # conf has no package_nam
                for puppet_name in PUPPET_PACKAGE_NAMES:
                    with suppress(PackageInstallerError):
                        to_install = (
                            [[puppet_name, version]]
                            if version
                            else [puppet_name]
                        )
                        cloud.distro.install_packages(to_install)
                        package_name = puppet_name
                        break
                if not package_name:
                    LOG.warning(
                        "No installable puppet package in any of: %s",
                        ", ".join(PUPPET_PACKAGE_NAMES),
                    )
            else:
                to_install = (
                    [[package_name, version]] if version else [package_name]
                )
                cloud.distro.install_packages(to_install)

        elif install_type == "aio":
            install_puppet_aio(
                cloud.distro, aio_install_url, version, collection, cleanup
            )
        else:
            LOG.warning("Unknown puppet install type '%s'", install_type)
            run = False

    conf_file = util.get_cfg_option_str(
        puppet_cfg, "conf_file", get_config_value(puppet_bin, "config")
    )
    ssl_dir = util.get_cfg_option_str(
        puppet_cfg, "ssl_dir", get_config_value(puppet_bin, "ssldir")
    )
    csr_attributes_path = util.get_cfg_option_str(
        puppet_cfg,
        "csr_attributes_path",
        get_config_value(puppet_bin, "csr_attributes"),
    )

    p_constants = PuppetConstants(conf_file, ssl_dir, csr_attributes_path)

    # ... and then update the puppet configuration
    if "conf" in puppet_cfg:
        # Add all sections from the conf object to puppet.conf
        contents = util.load_text_file(p_constants.conf_path)
        # Create object for reading puppet.conf values
        puppet_config = helpers.DefaultingConfigParser()
        # Read puppet.conf values from original file in order to be able to
        # mix the rest up. First clean them up
        # (TODO(harlowja) is this really needed??)
        cleaned_lines = [i.lstrip() for i in contents.splitlines()]
        cleaned_contents = "\n".join(cleaned_lines)
        puppet_config.read_file(
            StringIO(cleaned_contents), source=p_constants.conf_path
        )
        for cfg_name, cfg in puppet_cfg["conf"].items():
            # Cert configuration is a special case
            # Dump the puppetserver ca certificate in the correct place
            if cfg_name == "ca_cert":
                # Puppet ssl sub-directory isn't created yet
                # Create it with the proper permissions and ownership
                util.ensure_dir(p_constants.ssl_dir, 0o771)
                util.chownbyname(p_constants.ssl_dir, puppet_user, "root")
                util.ensure_dir(p_constants.ssl_cert_dir)

                util.chownbyname(p_constants.ssl_cert_dir, puppet_user, "root")
                util.write_file(p_constants.ssl_cert_path, cfg)
                util.chownbyname(
                    p_constants.ssl_cert_path, puppet_user, "root"
                )
            else:
                # Iterate through the config items, we'll use ConfigParser.set
                # to overwrite or create new items as needed
                for o, v in cfg.items():
                    if o == "certname":
                        # Expand %f as the fqdn
                        # TODO(harlowja) should this use the cloud fqdn??
                        v = v.replace("%f", socket.getfqdn())
                        # Expand %i as the instance id
                        v = v.replace("%i", cloud.get_instance_id())
                        # certname needs to be downcased
                        v = v.lower()
                    puppet_config.set(cfg_name, o, v)
            # We got all our config as wanted we'll rename
            # the previous puppet.conf and create our new one
            util.rename(
                p_constants.conf_path, "%s.old" % (p_constants.conf_path)
            )
            util.write_file(p_constants.conf_path, puppet_config.stringify())

    if "csr_attributes" in puppet_cfg:
        util.write_file(
            p_constants.csr_attributes_path,
            yaml.dump(puppet_cfg["csr_attributes"], default_flow_style=False),
        )

    if start_puppetd:
        # Enables the services
        _manage_puppet_services(cloud, "enable")

    # Run the agent if needed
    if run:
        LOG.debug("Running puppet-agent")
        cmd = [puppet_bin, "agent"]
        if "exec_args" in puppet_cfg:
            cmd_args = puppet_cfg["exec_args"]
            if isinstance(cmd_args, (list, tuple)):
                cmd.extend(cmd_args)
            elif isinstance(cmd_args, str):
                cmd.extend(cmd_args.split())
            else:
                LOG.warning(
                    "Unknown type %s provided for puppet"
                    " 'exec_args' expected list, tuple,"
                    " or string",
                    type(cmd_args),
                )
                cmd.extend(PUPPET_AGENT_DEFAULT_ARGS)
        else:
            cmd.extend(PUPPET_AGENT_DEFAULT_ARGS)
        subp.subp(cmd, capture=False)

    if start_puppetd:
        # Start puppetd
        _manage_puppet_services(cloud, "start")
