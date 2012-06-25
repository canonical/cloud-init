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
import re

import setuptools

import subprocess

def tiny_p(cmd):
    sp = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, stdin=None)
    (out, err) = sp.communicate()
    return (out, err)


def is_f(p):
    return os.path.isfile(p)


def get_version():
    cmd = ['tools/read-version']
    (ver, _e) = tiny_p(cmd)
    return ver.strip()


def read_requires():
    cmd = ['tools/read-dependencies']
    (deps, _e) = tiny_p(cmd)
    return deps.splitlines()


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
                  # Only really need for upstart based systems
                  #('/etc/init', glob('upstart/*.conf')),
                  ('/usr/share/cloud-init', []),
                  ('/usr/lib/cloud-init',
                    ['tools/uncloud-init', 'tools/write-ssh-key-fingerprints']),
                  ('/usr/share/doc/cloud-init', filter(is_f, glob('doc/*'))),
                  ('/usr/share/doc/cloud-init/examples', filter(is_f, glob('doc/examples/*'))),
                  ('/usr/share/doc/cloud-init/examples/seed', filter(is_f, glob('doc/examples/seed/*'))),
                  # ??
                  # ('/etc/profile.d', ['tools/Z99-cloud-locale-test.sh']),
                  ],
      install_requires=read_requires(),
      )
