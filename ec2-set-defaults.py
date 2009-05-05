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

api_ver = '2008-02-01'
metadata = None

base_url = 'http://169.254.169.254/%s/meta-data' % api_ver
zone = urllib.urlopen('%s/placement/availability-zone' % base_url).read()

if zone.startswith("us"):
	archive = "http://us.ec2.archive.ubuntu.com/ubuntu"
elif zone.startswith("eu"):
	archive = "http://eu.ec2.archive.ubuntu.com/ubuntu"

def set_language(location,filename):
	if location.startswith("us"):
	   lang='en_US.UTF-8'
	   os.system('locale-gen %s 2>&1 > /dev/null' %(lang))
	   os.system('update-locale %s 2>&1 > /dev/null' %(lang))
	elif location.startswith("eu"):
	   lang='en_GB.UTF-8'
	   os.system('locale-gen %s 2>&1 > /dev/null' %(lang))
	   os.system('update-locale %s 2>&1 > /dev/null' %(lang))
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
