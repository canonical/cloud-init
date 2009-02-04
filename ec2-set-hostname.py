#!/usr/bin/python
#
#    Fetch login credentials for EC2 
#    Copyright 2008 Canonical Ltd.
#
#    Author: Chuck Short <chuck.short@canonical.com>
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

base_url = 'http://169.254.169.254/%s/meta-data' % api_ver
my_hostname = urllib.urlopen('%s/local-hostname/' % base_url).read()
os.system('hostname %s' % my_hostname)

# replace the ubuntu hostname in /etc/hosts
my_public_hostname = urllib.urlopen('%s/public-hostname/' % base_url).read()

f = open("/etc/hosts", "r")
lines = f.read()
f.close()
file = open("/etc/hosts", "w")
file.write(lines.replace("127.0.1.1 ubuntu. ubuntu", "127.0.1.1 "+  my_public_hostname +" "+ my_hostname))
file.close()
