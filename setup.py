# Copyright (C) 2009 Canonical Ltd.
# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Soren Hansen <soren@canonical.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init.  See LICENSE file for license information.

# Distutils magic for ec2-init

from glob import glob

import atexit
import os
import shutil
import sys
import tempfile

import setuptools
from setuptools.command.install import install
from setuptools.command.egg_info import egg_info

from distutils.errors import DistutilsArgError

import subprocess

RENDERED_TMPD_PREFIX = "RENDERED_TEMPD"
VARIANT = None

def is_f(p):
    return os.path.isfile(p)


def tiny_p(cmd, capture=True):
    # Darn python 2.6 doesn't have check_output (argggg)
    stdout = subprocess.PIPE
    stderr = subprocess.PIPE
    if not capture:
        stdout = None
        stderr = None
    sp = subprocess.Popen(cmd, stdout=stdout,
                          stderr=stderr, stdin=None,
                          universal_newlines=True)
    (out, err) = sp.communicate()
    ret = sp.returncode
    if ret not in [0]:
        raise RuntimeError("Failed running %s [rc=%s] (%s, %s)" %
                           (cmd, ret, out, err))
    return (out, err)


def pkg_config_read(library, var):
    fallbacks = {
        'systemd': {
            'systemdsystemunitdir': '/lib/systemd/system',
            'systemdsystemgeneratordir': '/lib/systemd/system-generators',
        }
    }
    cmd = ['pkg-config', '--variable=%s' % var, library]
    try:
        (path, err) = tiny_p(cmd)
        path = path.strip()
    except Exception:
        path = fallbacks[library][var]
    if path.startswith("/"):
        path = path[1:]

    return path


def in_virtualenv():
    try:
        if sys.real_prefix == sys.prefix:
            return False
        else:
            return True
    except AttributeError:
        return False


def get_version():
    cmd = [sys.executable, 'tools/read-version']
    (ver, _e) = tiny_p(cmd)
    return str(ver).strip()


def read_requires():
    cmd = [sys.executable, 'tools/read-dependencies']
    (deps, _e) = tiny_p(cmd)
    return str(deps).splitlines()


def render_tmpl(template):
    """render template into a tmpdir under same dir as setup.py

    This is rendered to a temporary directory under the top level
    directory with the name 'cloud.cfg'.  The reason for not just rendering
    to config/cloud.cfg is for a.) don't want to write over contents
    in that file if user had something there. b.) debuild will complain
    that files are different outside of the debian directory."""

    # older versions of tox use bdist (xenial), and then install from there.
    # newer versions just use install.
    if not (sys.argv[1] == 'install' or sys.argv[1].startswith('bdist*')):
        return template

    tmpl_ext = ".tmpl"
    # we may get passed a non-template file, just pass it back
    if not template.endswith(tmpl_ext):
        return template

    topdir = os.path.dirname(sys.argv[0])
    tmpd = tempfile.mkdtemp(dir=topdir, prefix=RENDERED_TMPD_PREFIX)
    atexit.register(shutil.rmtree, tmpd)
    bname = os.path.basename(template).rstrip(tmpl_ext)
    fpath = os.path.join(tmpd, bname)
    if VARIANT:
        tiny_p([sys.executable, './tools/render-cloudcfg', '--variant',
            VARIANT, template, fpath])
    else:
        tiny_p([sys.executable, './tools/render-cloudcfg', template, fpath])
    # return path relative to setup.py
    return os.path.join(os.path.basename(tmpd), bname)

# User can set the variant for template rendering
if '--distro' in sys.argv:
    idx = sys.argv.index('--distro')
    VARIANT = sys.argv[idx+1]
    del sys.argv[idx+1]
    sys.argv.remove('--distro')

INITSYS_FILES = {
    'sysvinit': [f for f in glob('sysvinit/redhat/*') if is_f(f)],
    'sysvinit_freebsd': [f for f in glob('sysvinit/freebsd/*') if is_f(f)],
    'sysvinit_deb': [f for f in glob('sysvinit/debian/*') if is_f(f)],
    'sysvinit_openrc': [f for f in glob('sysvinit/gentoo/*') if is_f(f)],
    'sysvinit_suse': [f for f in glob('sysvinit/suse/*') if is_f(f)],
    'systemd': [render_tmpl(f)
                for f in (glob('systemd/*.tmpl') +
                          glob('systemd/*.service') +
                          glob('systemd/*.target')) if is_f(f)],
    'systemd.generators': [f for f in glob('systemd/*-generator') if is_f(f)],
    'upstart': [f for f in glob('upstart/*') if is_f(f)],
}
INITSYS_ROOTS = {
    'sysvinit': 'etc/rc.d/init.d',
    'sysvinit_freebsd': 'usr/local/etc/rc.d',
    'sysvinit_deb': 'etc/init.d',
    'sysvinit_openrc': 'etc/init.d',
    'sysvinit_suse': 'etc/init.d',
    'systemd': pkg_config_read('systemd', 'systemdsystemunitdir'),
    'systemd.generators': pkg_config_read('systemd',
                                          'systemdsystemgeneratordir'),
    'upstart': 'etc/init/',
}
INITSYS_TYPES = sorted([f.partition(".")[0] for f in INITSYS_ROOTS.keys()])


# Install everything in the right location and take care of Linux (default) and
# FreeBSD systems.
USR = "usr"
ETC = "etc"
USR_LIB_EXEC = "usr/lib"
LIB = "lib"
if os.uname()[0] == 'FreeBSD':
    USR = "usr/local"
    USR_LIB_EXEC = "usr/local/lib"
elif os.path.isfile('/etc/redhat-release'):
    USR_LIB_EXEC = "usr/libexec"


class MyEggInfo(egg_info):
    """This makes sure to not include the rendered files in SOURCES.txt."""

    def find_sources(self):
        ret = egg_info.find_sources(self)
        # update the self.filelist.
        self.filelist.exclude_pattern(RENDERED_TMPD_PREFIX + ".*",
                                      is_regex=True)
        # but since mfname is already written we have to update it also.
        mfname = os.path.join(self.egg_info, "SOURCES.txt")
        if os.path.exists(mfname):
            with open(mfname) as fp:
                files = [f for f in fp
                         if not f.startswith(RENDERED_TMPD_PREFIX)]
            with open(mfname, "w") as fp:
                fp.write(''.join(files))
        return ret


# TODO: Is there a better way to do this??
class InitsysInstallData(install):
    init_system = None
    user_options = install.user_options + [
        # This will magically show up in member variable 'init_sys'
        ('init-system=', None,
         ('init system(s) to configure (%s) [default: None]' %
          (", ".join(INITSYS_TYPES)))),
    ]

    def initialize_options(self):
        install.initialize_options(self)
        self.init_system = ""

    def finalize_options(self):
        install.finalize_options(self)

        if self.init_system and isinstance(self.init_system, str):
            self.init_system = self.init_system.split(",")

        if len(self.init_system) == 0:
            self.init_system = ['systemd']

        bad = [f for f in self.init_system if f not in INITSYS_TYPES]
        if len(bad) != 0:
            raise DistutilsArgError(
                "Invalid --init-system: %s" % (','.join(bad)))

        for system in self.init_system:
            # add data files for anything that starts with '<system>.'
            datakeys = [k for k in INITSYS_ROOTS
                        if k.partition(".")[0] == system]
            for k in datakeys:
                if not INITSYS_FILES[k]:
                    continue
                self.distribution.data_files.append(
                    (INITSYS_ROOTS[k], INITSYS_FILES[k]))
        # Force that command to reinitalize (with new file list)
        self.distribution.reinitialize_command('install_data', True)


if not in_virtualenv():
    USR = "/" + USR
    ETC = "/" + ETC
    USR_LIB_EXEC = "/" + USR_LIB_EXEC
    LIB = "/" + LIB
    for k in INITSYS_ROOTS.keys():
        INITSYS_ROOTS[k] = "/" + INITSYS_ROOTS[k]

data_files = [
    (ETC + '/bash_completion.d', ['bash_completion/cloud-init']),
    (ETC + '/cloud', [render_tmpl("config/cloud.cfg.tmpl")]),
    (ETC + '/cloud/cloud.cfg.d', glob('config/cloud.cfg.d/*')),
    (ETC + '/cloud/templates', glob('templates/*')),
    (USR_LIB_EXEC + '/cloud-init', ['tools/ds-identify',
                                    'tools/uncloud-init',
                                    'tools/write-ssh-key-fingerprints']),
    (USR + '/share/doc/cloud-init', [f for f in glob('doc/*') if is_f(f)]),
    (USR + '/share/doc/cloud-init/examples',
        [f for f in glob('doc/examples/*') if is_f(f)]),
    (USR + '/share/doc/cloud-init/examples/seed',
        [f for f in glob('doc/examples/seed/*') if is_f(f)]),
]
if os.uname()[0] != 'FreeBSD':
    data_files.extend([
        (ETC + '/NetworkManager/dispatcher.d/',
         ['tools/hook-network-manager']),
        (ETC + '/dhcp/dhclient-exit-hooks.d/', ['tools/hook-dhclient']),
        (LIB + '/udev/rules.d', [f for f in glob('udev/*.rules')])
    ])
# Use a subclass for install that handles
# adding on the right init system configuration files
cmdclass = {
    'install': InitsysInstallData,
    'egg_info': MyEggInfo,
}

requirements = read_requires()

setuptools.setup(
    name='cloud-init',
    version=get_version(),
    description='Cloud instance initialisation magic',
    author='Scott Moser',
    author_email='scott.moser@canonical.com',
    url='http://launchpad.net/cloud-init/',
    packages=setuptools.find_packages(exclude=['tests.*', '*.tests', 'tests']),
    scripts=['tools/cloud-init-per'],
    license='Dual-licensed under GPLv3 or Apache 2.0',
    data_files=data_files,
    install_requires=requirements,
    cmdclass=cmdclass,
    entry_points={
        'console_scripts': [
            'cloud-init = cloudinit.cmd.main:main',
            'cloud-id = cloudinit.cmd.cloud_id:main'
        ],
    }
)


# vi: ts=4 expandtab
