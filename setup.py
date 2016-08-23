#!/usr/bin/python
# vi: ts=4 expandtab
#
#    Distutils magic for ec2-init
#    Copyright (C) 2009 Canonical Ltd.
#
#    Author: Soren Hansen <soren@canonical.com>
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
#
from distutils.core import setup
from glob import glob
import os.path
import subprocess

def is_f(p):
    return(os.path.isfile(p))

setup(name='cloud-init',
      version='0.6.3',
      description='EC2 initialisation magic',
      author='Scott Moser',
      author_email='scott.moser@canonical.com',
      url='http://launchpad.net/cloud-init/',
      packages=['cloudinit', 'cloudinit.CloudConfig' ],
      scripts=['cloud-init.py',
               'cloud-init-cfg.py',
               'tools/cloud-init-per',
               ],
      data_files=[('/etc/cloud', glob('config/*.cfg')),
                  ('/etc/cloud/cloud.cfg.d', glob('config/cloud.cfg.d/*')),
                  ('/etc/cloud/templates', glob('templates/*')),
                  ('/etc/init', glob('upstart/*.conf')),
                  ('/usr/share/cloud-init', []),
                  ('/usr/lib/cloud-init', 
                    ['tools/uncloud-init', 'tools/write-ssh-key-fingerprints']),
                  ('/usr/share/doc/cloud-init', filter(is_f,glob('doc/*'))),
                  ('/usr/share/doc/cloud-init/examples', filter(is_f,glob('doc/examples/*'))),
                  ('/usr/share/doc/cloud-init/examples/seed', filter(is_f,glob('doc/examples/seed/*'))),
                  ('/etc/profile.d', ['tools/Z99-cloud-locale-test.sh']),
                  ],
      )
