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

api_ver = '2008-02-01'
metadata = None

def get_ssh_keys():
    base_url = 'http://169.254.169.254/%s/meta-data' % api_ver
    data = urllib.urlopen('%s/public-keys/' % base_url).read()
    keyids = [line.split('=')[0] for line in data.split('\n')]
    return [urllib.urlopen('%s/public-keys/%d/openssh-key' % (base_url, int(keyid))).read().rstrip() for keyid in keyids]

keys = get_ssh_keys()

os.umask(077)

if not os.path.exists('/root/.ssh'):
    os.mkdir('/root/.ssh')

fp = open('/root/.ssh/authorized_keys', 'a')
fp.write(''.join(['%s\n' % key for key in keys]))
fp.close()

