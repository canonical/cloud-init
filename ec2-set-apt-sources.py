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
import socket
import apt
import apt_pkg
from Cheetah.Template import Template

def checkServer():
	s = socket.socket()
	try:
	  address = '169.254.169.254'
          port = 80
	  s.connect((address,port))
	except socket.error, e:
	  print "!!! Unable to connect to %s." % address
	  sys.exit(0)

def detectZone():
        api_ver = '2008-02-01'

	base_url = 'http://169.254.169.254/%s/meta-data' % api_ver
	zone = urllib.urlopen('%s/placement/availability-zone' % base_url).read()
	if zone.startswith("us"):
		archive = "http://us.ec2.archive.ubuntu.com/ubuntu/"
	elif zone.startswith("eu"):
		archive = "http://eu.ec2.archive.ubuntu.com/ubuntu/"

	return(archive)

def updateList(filename):
	mirror = detectZone()
	if not os.path.exists("/var/run/ec2/sources.lists"):
		t = os.popen("lsb_release -c").read()
		codename = t.split()
		distro = codename[1]

		mp = {'mirror' : mirror, 'codename' : distro}
		t = Template(file="/etc/ec2-init/templates/sources.list.tmpl", searchList=[mp])
		f = open("/var/run/ec2/sources.list", "w")
		f.write('%s' %(t))
		f.close()

	if not os.path.exists("/etc/apt/sources.list-ec2-init"):
		os.system("mv /etc/apt/sources.list /etc/apt/sources.list-ec2-init")
		os.symlink("/var/run/ec2/sources.list", "/etc/apt/sources.list")
		cache = apt.Cache(apt.progress.OpProgress())
		prog = apt.progress.FetchProgress()
		cache.update(prog)

	os.system('touch %s' %(filename))

def get_ami_id():
    api_ver = '2008-02-01'

    url = 'http://169.254.169.254/%s/meta-data' % api_ver
    ami_id = urllib.urlopen('%s/ami-id/' %url).read()
    return ami_id


checkServer()

ami_id = get_ami_id()
filename = '/var/ec2/.apt-already-ran.%s' %ami_id

if os.path.exists(filename):
   print "ec2-set-apt-sources already ran....skipping."
else:
   updateList(filename)
