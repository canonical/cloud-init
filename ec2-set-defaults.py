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

import urllib
import os
import socket
import time
from Cheetah.Template import Template

api_ver = '2008-02-01'
metadata = None

def checkServer():
    for x in range(30*60):
        s = socket.socket()
        try:
            address = '169.254.169.254'
            port = 80
            s.connect((address,port))
            s.close()
            return
        except socket.error, e:
            time.sleep(1)

checkServer()

base_url = 'http://169.254.169.254/%s/meta-data' % api_ver
zone = urllib.urlopen('%s/placement/availability-zone' % base_url).read()

if zone.startswith("us"):
	archive = "http://us.ec2.archive.ubuntu.com/ubuntu"
elif zone.startswith("eu"):
	archive = "http://eu.ec2.archive.ubuntu.com/ubuntu"

def set_language(location,filename):
    if location.startswith("us"):
        lang='en_US.UTF-8'
    elif location.startswith("eu"):
        lang='en_GB.UTF-8'

    os.system('locale-gen %s' %(lang))

    mp = {'lang' : lang }
    T = Template(file="/etc/ec2-init/templates/locale.tmpl", searchList=[mp])
    f = open("/var/ec2/locale", "w")
    f.write('%s' %(T))
    f.close()

    os.system("mv /etc/default/locale /etc/default/locale-ec2-init")
    os.system("ln -s /var/ec2/locale /etc/default/locale")
    os.system(". /etc/default/locale")

    os.system('touch %s' %(filename))

def get_amid():
	url = 'http://169.254.169.254/%s/meta-data' % api_ver
	ami_id = urllib.urlopen('%s/ami-id/' %url).read()
	return ami_id

ami = get_amid()
filename = '/var/ec2/.defaults-already-ran.%s' %ami

if os.path.exists(filename):
   print "ec2-set-defaults already ran...skipping"
else:
   set_language(zone,filename)
