#!/usr/bin/python
#
#    Fetch login credentials for EC2 
#    Copyright 2008 Canonical Ltd.
#
#    Author: Soren Hansen <soren@canonical.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
import urllib
import os
import socket
import sys
from configobj import ConfigObj

api_ver = '2008-02-01'
metadata = None
filename='/etc/ec2-init/ec2-config.cfg'

config = ConfigObj(filename)
user = config['user']
config_root = config['DISABLE_ROOT']

def get_ssh_keys():
    base_url = 'http://169.254.169.254/%s/meta-data' % api_ver
    data = urllib.urlopen('%s/public-keys/' % base_url).read()
    keyids = [line.split('=')[0] for line in data.split('\n')]
    return [urllib.urlopen('%s/public-keys/%d/openssh-key' % (base_url, int(keyid))).read().rstrip() for keyid in keyids]

def setup_user_keys(k,user):
    if not os.path.exists('/home/%s/.ssh' %(user)):
	os.mkdir('/home/%s/.ssh' %(user))

    authorized_keys = '/home/%s/.ssh/authorized_keys' % user
    fp = open(authorized_keys, 'a')
    fp.write(''.join(['%s\n' % key for key in keys]))
    fp.close()
    os.system('chown -R %s:%s /home/%s/.ssh' %(user,user,user))

def setup_root_user(k,root_config):
    if root_config == "1":
	if not os.path.exists('/root/.ssh'):
            os.mkdir('/root/.ssh/')

        fp = open('/root/.ssh/authorized_keys', 'a')
	fp.write("command=\"echo \'Please login as the ubuntu user rather than root user.\';echo;sleep 10\" ") 
	fp.write(''.join(['%s\n' % key for key in keys]))
	fp.close()
    elif root_config == "0":
	print "You choose to disable the root user, god help you."
    else:
	print "%s - I dont understand that opion."

def checkServer():
    s = socket.socket()
    try:
      address = '169.254.169.254'
      port = 80
      s.connect((address,port))
    except socket.error, e:
      print "!!! Unable to connect to %s" % address
      sys.exit(0)

os.umask(077)
if user == "":
	print "User must exist in %s" %(filename)
	sys.exit(0)

keys = get_ssh_keys()
setup_user_keys(keys,user)
setup_root_user(keys,config_root)
