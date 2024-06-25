# This file is part of cloud-init. See LICENSE file for license information.

"""Ubuntu Drivers: Interact with third party drivers in Ubuntu."""

import logging
import os

from cloudinit.cloud import Cloud
from cloudinit.distros import Distro

try:
    import debconf

    HAS_DEBCONF = True
except ImportError:
    debconf = None
    HAS_DEBCONF = False


from cloudinit import subp, temp_utils, type_utils, util
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.settings import PER_INSTANCE

LOG = logging.getLogger(__name__)

meta: MetaSchema = {
    "id": "cc_ubuntu_drivers",
    "distros": ["ubuntu"],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": ["drivers"],
}  # type: ignore

OLD_UBUNTU_DRIVERS_STDERR_NEEDLE = (
    "ubuntu-drivers: error: argument <command>: invalid choice: 'install'"
)


# Use a debconf template to configure a global debconf variable
# (linux/nvidia/latelink) setting this to "true" allows the
# 'linux-restricted-modules' deb to accept the NVIDIA EULA and the package
# will automatically link the drivers to the running kernel.

NVIDIA_DEBCONF_CONTENT = """\
Template: linux/nvidia/latelink
Type: boolean
Default: true
Description: Late-link NVIDIA kernel modules?
 Enable this to link the NVIDIA kernel modules in cloud-init and
 make them available for use.
"""


X_LOADTEMPLATEFILE = "X_LOADTEMPLATEFILE"


def install_drivers(cfg, pkg_install_func, distro: Distro):
    if not isinstance(cfg, dict):
        raise TypeError(
            "'drivers' config expected dict, found '%s': %s"
            % (type_utils.obj_name(cfg), cfg)
        )

    cfgpath = "nvidia/license-accepted"
    # Call translate_bool to ensure that we treat string values like "yes" as
    # acceptance and _don't_ treat string values like "nah" as acceptance
    # because they're True-ish
    nv_acc = util.translate_bool(util.get_cfg_by_path(cfg, cfgpath))
    if not nv_acc:
        LOG.debug("Not installing NVIDIA drivers. %s=%s", cfgpath, nv_acc)
        return

    if not subp.which("ubuntu-drivers"):
        LOG.debug(
            "'ubuntu-drivers' command not available.  "
            "Installing ubuntu-drivers-common"
        )
        pkg_install_func(["ubuntu-drivers-common"])

    driver_arg = "nvidia"
    version_cfg = util.get_cfg_by_path(cfg, "nvidia/version")
    if version_cfg:
        driver_arg += ":{}".format(version_cfg)

    LOG.debug(
        "Installing and activating NVIDIA drivers (%s=%s, version=%s)",
        cfgpath,
        nv_acc,
        version_cfg if version_cfg else "latest",
    )

    # Register and set debconf selection linux/nvidia/latelink = true
    tdir = temp_utils.mkdtemp(dir=distro.get_tmp_exec_path(), needs_exe=True)
    debconf_file = os.path.join(tdir, "nvidia.template")
    try:
        util.write_file(debconf_file, NVIDIA_DEBCONF_CONTENT)
        with debconf.DebconfCommunicator("cloud-init") as dc:
            dc.command(X_LOADTEMPLATEFILE, debconf_file)
    except Exception as e:
        util.logexc(
            LOG, "Failed to register NVIDIA debconf template: %s", str(e)
        )
        raise
    finally:
        if os.path.isdir(tdir):
            util.del_dir(tdir)

    try:
        subp.subp(["ubuntu-drivers", "install", "--gpgpu", driver_arg])
    except subp.ProcessExecutionError as exc:
        if OLD_UBUNTU_DRIVERS_STDERR_NEEDLE in exc.stderr:
            LOG.warning(
                "the available version of ubuntu-drivers is"
                " too old to perform requested driver installation"
            )
        elif "No drivers found for installation." in exc.stdout:
            LOG.warning("ubuntu-drivers found no drivers for installation")
        raise


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    if "drivers" not in cfg:
        LOG.debug("Skipping module named %s, no 'drivers' key in config", name)
        return
    if not HAS_DEBCONF:
        LOG.warning(
            "Skipping module named %s, 'python3-debconf' is not installed",
            name,
        )
        return

    install_drivers(
        cfg["drivers"], cloud.distro.install_packages, cloud.distro
    )
