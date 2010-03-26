#!/usr/bin/python
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

setup(name='cloud-init',
      version='0.5.10',
      description='EC2 initialisation magic',
      author='Scott Moser',
      author_email='scott.moser@canonical.com',
      url='http://launchpad.net/cloud-init/',
      packages=['cloudinit'],
      scripts=['cloud-init.py',
               'cloud-init-run-module.py',
               'cloud-init-cfg.py'
               ],
      data_files=[('/etc/cloud', ['cloud.cfg']),
                  ('/etc/cloud/templates', glob('templates/*')),
                  ('/etc/init', glob('upstart/*.conf')),
                  ('/usr/share/cloud-init', []),
                  ('/usr/share/doc/cloud-init', glob('doc/*.txt')),
                  ('/usr/share/doc/cloud-init/examples', glob('doc/examples/*')),
                  ],
      )
