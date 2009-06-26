from distutils.core import setup
from glob import glob
import os.path
import subprocess

setup(name='EC2-init',
      version='0.5',
      description='EC2 initialisation magic',
      author='Soren Hansen',
      author_email='soren@canonical.com',
      url='http://launchpad.net/ec2-init/',
      packages=['ec2init'],
      scripts=['ec2-fetch-credentials.py',
               'ec2-get-info.py',
               'ec2-run-user-data.py',
               'ec2-set-apt-sources.py',
               'ec2-set-defaults.py',
               'ec2-set-hostname.py'],
      data_files=[('/etc/ec2-init', ['debian/ec2-config.cfg']),
                  ('/etc/ec2-init/templates', glob('templates/*'))],
      )
