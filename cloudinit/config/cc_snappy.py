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

CI_SNAPPY_CFG = {
    'env_file_path': SNAPPY_ENV_PATH,
    'packages': [],
    'packages_dir': '/writable/user-data/cloud-init/click_packages',
    'ssh_enabled': False
}

"""
snappy:
  ssh_enabled: True
  packages:
    - etcd
    - {'name': 'pkg1', 'config': "wark"}
"""


def flatten(data, fill=None, tok="_", prefix='', recurse=True):
    if fill is None:
        fill = {}
    for key, val in data.items():
        key = key.replace("-", "_")
        if isinstance(val, dict) and recurse:
            flatten(val, fill, tok=tok, prefix=prefix + key + tok,
                    recurse=recurse)
        elif isinstance(key, str):
            fill[prefix + key] = val
    return fill


def render2env(data, tok="_", prefix=''):
    flat = flatten(data, tok=tok, prefix=prefix)
    ret = ["%s='%s'" % (key, val) for key, val in flat.items()]
    return '\n'.join(ret) + '\n'


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


def handle(name, cfg, cloud, log, args):
    mycfg = cfg.get('snappy', {'ssh_enabled': False})

    if not mycfg:
        LOG.debug("%s: no top level found", name)
        return

    # take out of 'cfg' the cfg keys that cloud-init uses, so
    # mycfg has only content external to cloud-init.
    ci_cfg = CI_SNAPPY_CFG.copy()
    for i in ci_cfg:
        if i in mycfg:
            ci_cfg[i] = mycfg[i]
            del mycfg[i]

    # render the flattened environment variable style file to a path
    # this was useful for systemd config environment files.  given:
    # snappy:
    #   foo:
    #     bar: wark
    #     cfg1:
    #       key1: value
    # you get the following in env_file_path.
    #   foo_bar=wark
    #   foo_cfg1_key1=value
    contents = render2env(mycfg)
    header = '# for internal use only, not a guaranteed interface\n'
    util.write_file(ci_cfg['env_file_path'], header + render2env(mycfg))

    install_packages(ci_cfg['packages_dir'],
                     ci_cfg['packages'])

    disable_enable_ssh(ci_cfg.get('ssh_enabled', False))
