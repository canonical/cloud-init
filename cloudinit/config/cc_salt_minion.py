# Author: Jeff Bauer <jbauer@rubic.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Salt Minion: Setup and run salt minion"""

import logging
import os

from cloudinit import safeyaml, subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.distros import ALL_DISTROS
from cloudinit.settings import PER_INSTANCE

meta: MetaSchema = {
    "id": "cc_salt_minion",
    "distros": [ALL_DISTROS],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": ["salt_minion"],
}  # type: ignore

LOG = logging.getLogger(__name__)

# Note: see https://docs.saltstack.com/en/latest/topics/installation/
# Note: see https://docs.saltstack.com/en/latest/ref/configuration/


class SaltConstants:
    """
    defines default distribution specific salt variables
    """

    def __init__(self, cfg):
        # constants tailored for FreeBSD
        if util.is_FreeBSD():
            self.pkg_name = "py-salt"
            self.srv_name = "salt_minion"
            self.conf_dir = "/usr/local/etc/salt"
        # constants for any other OS
        else:
            self.pkg_name = "salt-minion"
            self.srv_name = "salt-minion"
            self.conf_dir = "/etc/salt"

        # if there are constants given in cloud config use those
        self.pkg_name = util.get_cfg_option_str(cfg, "pkg_name", self.pkg_name)
        self.conf_dir = util.get_cfg_option_str(
            cfg, "config_dir", self.conf_dir
        )
        self.srv_name = util.get_cfg_option_str(
            cfg, "service_name", self.srv_name
        )


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    # If there isn't a salt key in the configuration don't do anything
    if "salt_minion" not in cfg:
        LOG.debug(
            "Skipping module named %s, no 'salt_minion' key in configuration",
            name,
        )
        return

    s_cfg = cfg["salt_minion"]
    const = SaltConstants(cfg=s_cfg)

    # Start by installing the salt package ...
    cloud.distro.install_packages([const.pkg_name])

    # Ensure we can configure files at the right dir
    util.ensure_dir(const.conf_dir)

    minion_data = None

    # ... and then update the salt configuration
    if "conf" in s_cfg:
        # Add all sections from the conf object to minion config file
        minion_config = os.path.join(const.conf_dir, "minion")
        minion_data = s_cfg.get("conf")
        util.write_file(minion_config, safeyaml.dumps(minion_data))

    if "grains" in s_cfg:
        # add grains to /etc/salt/grains
        grains_config = os.path.join(const.conf_dir, "grains")
        grains_data = safeyaml.dumps(s_cfg.get("grains"))
        util.write_file(grains_config, grains_data)

    # ... copy the key pair if specified
    if "public_key" in s_cfg and "private_key" in s_cfg:
        pki_dir_default = os.path.join(const.conf_dir, "pki/minion")
        if not os.path.isdir(pki_dir_default):
            pki_dir_default = os.path.join(const.conf_dir, "pki")

        pki_dir = s_cfg.get("pki_dir", pki_dir_default)
        with util.umask(0o77):
            util.ensure_dir(pki_dir)
            pub_name = os.path.join(pki_dir, "minion.pub")
            pem_name = os.path.join(pki_dir, "minion.pem")
            util.write_file(pub_name, s_cfg["public_key"])
            util.write_file(pem_name, s_cfg["private_key"])

    minion_daemon = not bool(
        minion_data and minion_data.get("file_client") == "local"
    )

    cloud.distro.manage_service(
        "enable" if minion_daemon else "disable", const.srv_name
    )
    cloud.distro.manage_service(
        "restart" if minion_daemon else "stop", const.srv_name
    )

    if not minion_daemon:
        # if salt-minion was configured as masterless, we should not run
        # salt-minion as a daemon
        # Note: see https://docs.saltproject.io/en/latest/topics/tutorials/quickstart.html  # noqa: E501
        subp.subp(["salt-call", "--local", "state.apply"], capture=False)
