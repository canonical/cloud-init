# This file is part of cloud-init. See LICENSE file for license information.

# RELEASE_BLOCKER: Remove this deprecated module in 18.3
"""
Snappy
------
**Summary:** snappy modules allows configuration of snappy.

**Deprecated**: Use :ref:`snap` module instead. This module will not exist
in cloud-init 18.3.

The below example config config would install ``etcd``, and then install
``pkg2.smoser`` with a ``<config-file>`` argument where ``config-file`` has
``config-blob`` inside it. If ``pkgname`` is installed already, then
``snappy config pkgname <file>``
will be called where ``file`` has ``pkgname-config-blob`` as its content.

Entries in ``config`` can be namespaced or non-namespaced for a package.
In either case, the config provided to snappy command is non-namespaced.
The package name is provided as it appears.

If ``packages_dir`` has files in it that end in ``.snap``, then they are
installed.  Given 3 files:

  - <packages_dir>/foo.snap
  - <packages_dir>/foo.config
  - <packages_dir>/bar.snap

cloud-init will invoke:

  - snappy install <packages_dir>/foo.snap <packages_dir>/foo.config
  - snappy install <packages_dir>/bar.snap

.. note::
    that if provided a ``config`` entry for ``ubuntu-core``, then
    cloud-init will invoke: snappy config ubuntu-core <config>
    Allowing you to configure ubuntu-core in this way.

The ``ssh_enabled`` key controls the system's ssh service. The default value
is ``auto``. Options are:

  - **True:** enable ssh service
  - **False:** disable ssh service
  - **auto:** enable ssh service if either ssh keys have been provided
    or user has requested password authentication (ssh_pwauth).

**Internal name:** ``cc_snappy``

**Module frequency:** per instance

**Supported distros:** ubuntu

**Config keys**::

    #cloud-config
    snappy:
        system_snappy: auto
        ssh_enabled: auto
        packages: [etcd, pkg2.smoser]
        config:
            pkgname:
                key2: value2
            pkg2:
                key1: value1
        packages_dir: '/writable/user-data/cloud-init/snaps'
"""

from cloudinit import log as logging
from cloudinit.settings import PER_INSTANCE
from cloudinit import temp_utils
from cloudinit import util

import glob
import os

LOG = logging.getLogger(__name__)

frequency = PER_INSTANCE
SNAPPY_CMD = "snappy"
NAMESPACE_DELIM = '.'

BUILTIN_CFG = {
    'packages': [],
    'packages_dir': '/writable/user-data/cloud-init/snaps',
    'ssh_enabled': "auto",
    'system_snappy': "auto",
    'config': {},
}

distros = ['ubuntu']


def parse_filename(fname):
    fname = os.path.basename(fname)
    fname_noext = fname.rpartition(".")[0]
    name = fname_noext.partition("_")[0]
    shortname = name.partition(".")[0]
    return(name, shortname, fname_noext)


def get_fs_package_ops(fspath):
    if not fspath:
        return []
    ops = []
    for snapfile in sorted(glob.glob(os.path.sep.join([fspath, '*.snap']))):
        (name, shortname, fname_noext) = parse_filename(snapfile)
        cfg = None
        for cand in (fname_noext, name, shortname):
            fpcand = os.path.sep.join([fspath, cand]) + ".config"
            if os.path.isfile(fpcand):
                cfg = fpcand
                break
        ops.append(makeop('install', name, config=None,
                   path=snapfile, cfgfile=cfg))
    return ops


def makeop(op, name, config=None, path=None, cfgfile=None):
    return({'op': op, 'name': name, 'config': config, 'path': path,
            'cfgfile': cfgfile})


def get_package_config(configs, name):
    # load the package's config from the configs dict.
    # prefer full-name entry (config-example.canonical)
    # over short name entry (config-example)
    if name in configs:
        return configs[name]
    return configs.get(name.partition(NAMESPACE_DELIM)[0])


def get_package_ops(packages, configs, installed=None, fspath=None):
    # get the install an config operations that should be done
    if installed is None:
        installed = read_installed_packages()
    short_installed = [p.partition(NAMESPACE_DELIM)[0] for p in installed]

    if not packages:
        packages = []
    if not configs:
        configs = {}

    ops = []
    ops += get_fs_package_ops(fspath)

    for name in packages:
        ops.append(makeop('install', name, get_package_config(configs, name)))

    to_install = [f['name'] for f in ops]
    short_to_install = [f['name'].partition(NAMESPACE_DELIM)[0] for f in ops]

    for name in configs:
        if name in to_install:
            continue
        shortname = name.partition(NAMESPACE_DELIM)[0]
        if shortname in short_to_install:
            continue
        if name in installed or shortname in short_installed:
            ops.append(makeop('config', name,
                              config=get_package_config(configs, name)))

    # prefer config entries to filepath entries
    for op in ops:
        if op['op'] != 'install' or not op['cfgfile']:
            continue
        name = op['name']
        fromcfg = get_package_config(configs, op['name'])
        if fromcfg:
            LOG.debug("preferring configs[%(name)s] over '%(cfgfile)s'", op)
            op['cfgfile'] = None
            op['config'] = fromcfg

    return ops


def render_snap_op(op, name, path=None, cfgfile=None, config=None):
    if op not in ('install', 'config'):
        raise ValueError("cannot render op '%s'" % op)

    shortname = name.partition(NAMESPACE_DELIM)[0]
    try:
        cfg_tmpf = None
        if config is not None:
            # input to 'snappy config packagename' must have nested data. odd.
            # config:
            #   packagename:
            #      config
            # Note, however, we do not touch config files on disk.
            nested_cfg = {'config': {shortname: config}}
            (fd, cfg_tmpf) = temp_utils.mkstemp()
            os.write(fd, util.yaml_dumps(nested_cfg).encode())
            os.close(fd)
            cfgfile = cfg_tmpf

        cmd = [SNAPPY_CMD, op]
        if op == 'install':
            if path:
                cmd.append("--allow-unauthenticated")
                cmd.append(path)
            else:
                cmd.append(name)
            if cfgfile:
                cmd.append(cfgfile)
        elif op == 'config':
            cmd += [name, cfgfile]

        util.subp(cmd)

    finally:
        if cfg_tmpf:
            os.unlink(cfg_tmpf)


def read_installed_packages():
    ret = []
    for (name, _date, _version, dev) in read_pkg_data():
        if dev:
            ret.append(NAMESPACE_DELIM.join([name, dev]))
        else:
            ret.append(name)
    return ret


def read_pkg_data():
    out, _err = util.subp([SNAPPY_CMD, "list"])
    pkg_data = []
    for line in out.splitlines()[1:]:
        toks = line.split(sep=None, maxsplit=3)
        if len(toks) == 3:
            (name, date, version) = toks
            dev = None
        else:
            (name, date, version, dev) = toks
        pkg_data.append((name, date, version, dev,))
    return pkg_data


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


def set_snappy_command():
    global SNAPPY_CMD
    if util.which("snappy-go"):
        SNAPPY_CMD = "snappy-go"
    elif util.which("snappy"):
        SNAPPY_CMD = "snappy"
    else:
        SNAPPY_CMD = "snap"
    LOG.debug("snappy command is '%s'", SNAPPY_CMD)


def handle(name, cfg, cloud, log, args):
    cfgin = cfg.get('snappy')
    if not cfgin:
        cfgin = {}
    mycfg = util.mergemanydict([cfgin, BUILTIN_CFG])

    sys_snappy = str(mycfg.get("system_snappy", "auto"))
    if util.is_false(sys_snappy):
        LOG.debug("%s: System is not snappy. disabling", name)
        return

    if sys_snappy.lower() == "auto" and not(util.system_is_snappy()):
        LOG.debug("%s: 'auto' mode, and system not snappy", name)
        return

    log.warning(
        'DEPRECATION: snappy module will be dropped in 18.3 release.'
        ' Use snap module instead')

    set_snappy_command()

    pkg_ops = get_package_ops(packages=mycfg['packages'],
                              configs=mycfg['config'],
                              fspath=mycfg['packages_dir'])

    fails = []
    for pkg_op in pkg_ops:
        try:
            render_snap_op(**pkg_op)
        except Exception as e:
            fails.append((pkg_op, e,))
            LOG.warning("'%s' failed for '%s': %s",
                        pkg_op['op'], pkg_op['name'], e)

    # Default to disabling SSH
    ssh_enabled = mycfg.get('ssh_enabled', "auto")

    # If the user has not explicitly enabled or disabled SSH, then enable it
    # when password SSH authentication is requested or there are SSH keys
    if ssh_enabled == "auto":
        user_ssh_keys = cloud.get_public_ssh_keys() or None
        password_auth_enabled = cfg.get('ssh_pwauth', False)
        if user_ssh_keys:
            LOG.debug("Enabling SSH, ssh keys found in datasource")
            ssh_enabled = True
        elif cfg.get('ssh_authorized_keys'):
            LOG.debug("Enabling SSH, ssh keys found in config")
        elif password_auth_enabled:
            LOG.debug("Enabling SSH, password authentication requested")
            ssh_enabled = True
    elif ssh_enabled not in (True, False):
        LOG.warning("Unknown value '%s' in ssh_enabled", ssh_enabled)

    disable_enable_ssh(ssh_enabled)

    if fails:
        raise Exception("failed to install/configure snaps")

# vi: ts=4 expandtab
