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

setup(name='EC2-init',
      version='0.4.999',
      description='EC2 initialisation magic',
      author='Soren Hansen',
      author_email='soren@canonical.com',
      url='http://launchpad.net/ec2-init/',
      packages=['ec2init'],
      scripts=['ec2-fetch-credentials.py',
               'ec2-get-info.py',
               'ec2-run-user-data.py',
               'ec2-set-defaults.py',
               'ec2-set-hostname.py',
               'ec2-wait-for-meta-data-service.py',
               'ec2-is-compat-env'],
      data_files=[('/etc/ec2-init', ['ec2-config.cfg']),
                  ('/etc/ec2-init/templates', glob('templates/*')),
                  ('/etc/init.d', ['ec2-init']),
                  ('/usr/share/ec2-init', ['ec2-init-appliance-ebs-volume-mount.sh']),
                  ],
      )
