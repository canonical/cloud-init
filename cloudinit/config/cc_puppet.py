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
from typing import List, Union

import yaml

from cloudinit import helpers, subp, temp_utils, url_helper, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.distros import ALL_DISTROS, Distro, PackageInstallerError
from cloudinit.settings import PER_INSTANCE

AIO_INSTALL_URL = "https://raw.githubusercontent.com/puppetlabs/install-puppet/main/install.sh"  # noqa: E501
PUPPET_AGENT_DEFAULT_ARGS = ["--test"]
PUPPET_PACKAGE_NAMES = ("puppet-agent", "puppet")

meta: MetaSchema = {
    "id": "cc_puppet",
    "distros": [ALL_DISTROS],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": ["puppet"],
}  # type: ignore

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
            if package_name is None:  # conf has no package_name
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
