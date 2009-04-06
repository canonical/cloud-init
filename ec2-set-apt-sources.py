#!/usr/bin/python
#
#    Fetch the availabity zone and create the sources.list
#    Copyright 2009 Canonical Ltd.
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
import os
import sys
import urllib
from Cheetah.Template import Template

def detectZone():
	api_ver = '2008-02-01'
	metadat = None

	base_url = 'http://169.254.169.254/%s/meta-data' % api_ver
	zone = urllib.urlopen('%s/placement/availability-zone' % base_url).read()
	if zone.startswith("us"):
		archive = "http://us.ec2.archive.ubuntu.com/ubuntu/"
	elif zone.startswith("eu"):
		archive = "http://eu.ec2.archive.ubuntu.com/ubuntu/"

	return(archive)

t = os.popen("lsb_release -c").read()
codename = t.split()
mirror = detectZone()
distro = codename[1]

mp = {'mirror' : mirror, 'codename' : distro}
t = Template(file="/etc/ec2-init/templates/sources.list.tmpl", searchList=[mp])

f = open("/var/run/ec2/sources.list", "w")
f.write('%s' %(t))
f.close()

os.system("mv /etc/apt/sources.list /etc/apt/sources.list-ec2-init")
os.system("ln -s /var/run/ec2/sources.list /etc/apt/sources.list")
os.system("apt-get update 2>&1 > /dev/null")
