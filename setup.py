# vi: ts=4 expandtab
#
#    Distutils magic for ec2-init
#
#    Copyright (C) 2009 Canonical Ltd.
#    Copyright (C) 2012 Yahoo! Inc.
#
#    Author: Soren Hansen <soren@canonical.com>
#    Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License version 3, as
#    published by the Free Software Foundation.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

from glob import glob

import os

import setuptools
from setuptools.command.install import install

from distutils.errors import DistutilsArgError

import subprocess


def is_f(p):
    return os.path.isfile(p)


INITSYS_FILES = {
    'sysvinit': [f for f in glob('sysvinit/redhat/*') if is_f(f)],
    'sysvinit_deb': [f for f in glob('sysvinit/debian/*') if is_f(f)],
    'systemd': [f for f in glob('systemd/*') if is_f(f)],
    'upstart': [f for f in glob('upstart/*') if is_f(f)],
}
INITSYS_ROOTS = {
    'sysvinit': '/etc/rc.d/init.d',
    'sysvinit_deb': '/etc/init.d',
    'systemd': '/etc/systemd/system/',
    'upstart': '/etc/init/',
}
INITSYS_TYPES = sorted(list(INITSYS_ROOTS.keys()))


def tiny_p(cmd, capture=True):
    # Darn python 2.6 doesn't have check_output (argggg)
    stdout = subprocess.PIPE
    stderr = subprocess.PIPE
    if not capture:
        stdout = None
        stderr = None
    sp = subprocess.Popen(cmd, stdout=stdout,
                    stderr=stderr, stdin=None)
    (out, err) = sp.communicate()
    ret = sp.returncode  # pylint: disable=E1101
    if ret not in [0]:
        raise RuntimeError("Failed running %s [rc=%s] (%s, %s)"
                            % (cmd, ret, out, err))
    return (out, err)


def get_version():
    cmd = ['tools/read-version']
    (ver, _e) = tiny_p(cmd)
    return str(ver).strip()


def read_requires():
    cmd = ['tools/read-dependencies']
    (deps, _e) = tiny_p(cmd)
    return str(deps).splitlines()


# TODO: Is there a better way to do this??
class InitsysInstallData(install):
    init_system = None
    user_options = install.user_options + [
        # This will magically show up in member variable 'init_sys'
        ('init-system=', None,
            ('init system to configure (%s) [default: None]') %
                (", ".join(INITSYS_TYPES))
        ),
    ]

    def initialize_options(self):
        install.initialize_options(self)
        self.init_system = None

    def finalize_options(self):
        install.finalize_options(self)
        if self.init_system and self.init_system not in INITSYS_TYPES:
            raise DistutilsArgError(("You must specify one of (%s) when"
                 " specifying a init system!") % (", ".join(INITSYS_TYPES)))
        elif self.init_system:
            self.distribution.data_files.append(
                (INITSYS_ROOTS[self.init_system],
                 INITSYS_FILES[self.init_system]))
            # Force that command to reinitalize (with new file list)
            self.distribution.reinitialize_command('install_data', True)


setuptools.setup(name='cloud-init',
      version=get_version(),
      description='EC2 initialisation magic',
      author='Scott Moser',
      author_email='scott.moser@canonical.com',
      url='http://launchpad.net/cloud-init/',
      packages=setuptools.find_packages(exclude=['tests']),
      scripts=['bin/cloud-init',
               'tools/cloud-init-per',
               ],
      license='GPLv3',
      data_files=[('/etc/cloud', glob('config/*.cfg')),
                  ('/etc/cloud/cloud.cfg.d', glob('config/cloud.cfg.d/*')),
                  ('/etc/cloud/templates', glob('templates/*')),
                  ('/usr/share/cloud-init', []),
                  ('/usr/lib/cloud-init',
                    ['tools/uncloud-init',
                     'tools/write-ssh-key-fingerprints']),
                  ('/usr/share/doc/cloud-init',
                   [f for f in glob('doc/*') if is_f(f)]),
                  ('/usr/share/doc/cloud-init/examples',
                   [f for f in glob('doc/examples/*') if is_f(f)]),
                  ('/usr/share/doc/cloud-init/examples/seed',
                   [f for f in glob('doc/examples/seed/*') if is_f(f)]),
                 ],
      install_requires=read_requires(),
      cmdclass={
          # Use a subclass for install that handles
          # adding on the right init system configuration files
          'install': InitsysInstallData,
      },
      )
