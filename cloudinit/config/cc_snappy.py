# vi: ts=4 expandtab
#

from cloudinit import log as logging
from cloudinit import templater
from cloudinit import util
from cloudinit.settings import PER_INSTANCE

import glob
import os

LOG = logging.getLogger(__name__)

frequency = PER_INSTANCE
SNAPPY_ENV_PATH = "/writable/system-data/etc/snappy.env"

BUILTIN_CFG = {
    'packages': [],
    'packages_dir': '/writable/user-data/cloud-init/click_packages',
    'ssh_enabled': False,
    'system_snappy': "auto"
}

"""
snappy:
  system_snappy: auto
  ssh_enabled: True
  packages:
    - etcd
    - {'name': 'pkg1', 'config': "wark"}
"""


def install_package(pkg_name, config=None):
    cmd = ["snappy", "install"]
    if config:
        if os.path.isfile(config):
            cmd.append("--config-file=" + config)
        else:
            cmd.append("--config=" + config)
    cmd.append(pkg_name)
    util.subp(cmd)


def install_packages(package_dir, packages):
    local_pkgs = glob.glob(os.path.sep.join([package_dir, '*.click']))
    LOG.debug("installing local packages %s" % local_pkgs)
    if local_pkgs:
        for pkg in local_pkgs:
            cfg = pkg.replace(".click", ".config")
            if not os.path.isfile(cfg):
                cfg = None
            install_package(pkg, config=cfg)

    LOG.debug("installing click packages")
    if packages:
        for pkg in packages:
            if not pkg:
                continue
            if isinstance(pkg, str):
                name = pkg
                config = None
            elif pkg:
                name = pkg.get('name', pkg)
                config = pkg.get('config')
            install_package(pkg_name=name, config=config)


def disable_enable_ssh(enabled):
    LOG.debug("setting enablement of ssh to: %s", enabled)
    # do something here that would enable or disable
    not_to_be_run = "/etc/ssh/sshd_not_to_be_run"
    if enabled:
        util.del_file(not_to_be_run)
        # this is an indempotent operation
        util.subp(["systemctl", "start", "ssh"])
    else:
        # this is an indempotent operation
        util.subp(["systemctl", "stop", "ssh"])
        util.write_file(not_to_be_run, "cloud-init\n")


def system_is_snappy():
    # channel.ini is configparser loadable.
    # snappy will move to using /etc/system-image/config.d/*.ini
    # this is certainly not a perfect test, but good enough for now.
    content = util.load_file("/etc/system-image/channel.ini")
    if 'ubuntu-core' in content.lower():
        return True
    if os.path.isdir("/etc/system-image/config.d/"):
        return True
    return False


def handle(name, cfg, cloud, log, args):
    cfgin = cfg.get('snappy')
    if not cfgin:
        cfgin = {}
    mycfg = util.mergemanydict([BUILTIN_CFG, cfgin])

    sys_snappy = mycfg.get("system_snappy", "auto")
    if util.is_false(sys_snappy):
        LOG.debug("%s: System is not snappy. disabling", name)
        return

    if sys_snappy.lower() == "auto" and not(system_is_snappy()):
        LOG.debug("%s: 'auto' mode, and system not snappy", name)
        return

    install_packages(ci_cfg['packages_dir'],
                     ci_cfg['packages'])

    disable_enable_ssh(ci_cfg.get('ssh_enabled', False))
