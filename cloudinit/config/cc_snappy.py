# vi: ts=4 expandtab
#

from cloudinit import log as logging
from cloudinit import templater
from cloudinit import util
from cloudinit.settings import PER_INSTANCE

import glob
import six
import tempfile
import os

LOG = logging.getLogger(__name__)

frequency = PER_INSTANCE
SNAPPY_CMD = "snappy"

BUILTIN_CFG = {
    'packages': [],
    'packages_dir': '/writable/user-data/cloud-init/click_packages',
    'ssh_enabled': False,
    'system_snappy': "auto",
    'configs': {},
}

"""
snappy:
  system_snappy: auto
  ssh_enabled: True
  packages:
    - etcd
    - pkg2
  configs:
    pkgname: config-blob
    pkgname2: config-blob
"""


def get_fs_package_ops(fspath):
    if not fspath:
        return []
    ops = []
    for snapfile in glob.glob(os.path.sep.join([fspath, '*.snap'])):
        cfg = snapfile.rpartition(".")[0] + ".config"
        name = os.path.basename(snapfile).rpartition(".")[0]
        if not os.path.isfile(cfg):
            cfg = None
        ops.append(makeop('install', name, config=None,
                   path=snapfile, cfgfile=cfg))
    return ops


def makeop(op, name, config=None, path=None, cfgfile=None):
    return({'op': op, 'name': name, 'config': config, 'path': path,
            'cfgfile': cfgfile})


def get_package_ops(packages, configs, installed=None, fspath=None):
    # get the install an config operations that should be done
    if installed is None:
        installed = read_installed_packages()

    if not packages:
        packages = []
    if not configs:
        configs = {}

    ops = []
    ops += get_fs_package_ops(fspath)

    for name in packages:
        ops.append(makeop('install', name, configs.get('name')))

    to_install = [f['name'] for f in ops]

    for name in configs:
        if name in installed and name not in to_install:
            ops.append(makeop('config', name, config=configs[name]))

    # prefer config entries to filepath entries
    for op in ops:
        name = op['name']
        if name in configs and op['op'] == 'install' and 'cfgfile' in op:
            LOG.debug("preferring configs[%s] over '%s'", name, op['cfgfile'])
            op['cfgfile'] = None
            op['config'] = configs[op['name']]

    return ops


def render_snap_op(op, name, path=None, cfgfile=None, config=None):
    if op not in ('install', 'config'):
        raise ValueError("cannot render op '%s'" % op)

    try:
        cfg_tmpf = None
        if config is not None:
            if isinstance(config, six.binary_type):
                cfg_bytes = config
            elif isinstance(config, six.text_type):
                cfg_bytes = config.encode()
            else:
                cfg_bytes = util.yaml_dumps(config).encode()

            (fd, cfg_tmpf) = tempfile.mkstemp()
            os.write(fd, cfg_bytes)
            os.close(fd)
            cfgfile = cfg_tmpf

        cmd = [SNAPPY_CMD, op]
        if op == 'install':
            if cfgfile:
                cmd.append('--config=' + cfgfile)
            if path:
                cmd.append(path)
            else:
                cmd.append(name)
        elif op == 'config':
            cmd += [name, cfgfile]

        util.subp(cmd)

    finally:
        if cfg_tmpf:
            os.unlink(cfg_tmpf)


def read_installed_packages():
    return [p[0] for p in read_pkg_data()]


def read_pkg_data():
    out, err = util.subp([SNAPPY_CMD, "list"])
    for line in out.splitlines()[1:]:
        toks = line.split(sep=None, maxsplit=3)
        if len(toks) == 3:
            (name, date, version) = toks
            dev = None
        else:
            (name, date, version, dev) = toks
        pkgs.append((name, date, version, dev,))


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
    content = util.load_file("/etc/system-image/channel.ini", quiet=True)
    if 'ubuntu-core' in content.lower():
        return True
    if os.path.isdir("/etc/system-image/config.d/"):
        return True
    return False


def set_snappy_command():
    if util.which("snappy-go"):
        SNAPPY_COMMAND = "snappy-go"
    else:
        SNAPPY_COMMAND = "snappy"
    LOG.debug("snappy command is '%s'", SNAPPY_COMMAND)


def handle(name, cfg, cloud, log, args):
    cfgin = cfg.get('snappy')
    if not cfgin:
        cfgin = {}
    mycfg = util.mergemanydict([cfgin, BUILTIN_CFG])

    sys_snappy = str(mycfg.get("system_snappy", "auto"))
    if util.is_false(sys_snappy):
        LOG.debug("%s: System is not snappy. disabling", name)
        return

    if sys_snappy.lower() == "auto" and not(system_is_snappy()):
        LOG.debug("%s: 'auto' mode, and system not snappy", name)
        return

    pkg_ops = get_package_ops(packages=mycfg['packages'],
                              configs=mycfg['configs'],
                              fspath=mycfg['packages_dir'])

    set_snappy_command()

    fails = []
    for pkg_op in pkg_ops:
        try:
            render_snap_op(**pkg_op)
        except Exception as e:
            fails.append((pkg_op, e,))
            LOG.warn("'%s' failed for '%s': %s",
                     pkg_op['op'], pkg_op['name'], e)

    disable_enable_ssh(mycfg.get('ssh_enabled', False))

    if fails:
        raise Exception("failed to install/configure snaps")
