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
filename='/etc/ec2-init/ec2-config.cfg'

base_url = 'http://169.254.169.254/%s/meta-data' % api_ver
zone = urllib.urlopen('%s/placement/availability-zone' % base_url).read()

if zone.startswith("us"):
	archive = "http://us.ec2.archive.ubuntu.com/ubuntu"
elif zone.startswith("eu"):
	archive = "http://eu.ec2.archive.ubuntu.com/ubuntu"

def set_utc_clock():
	os.system('ln -s -f /usr/share/zoneinfo/UTC /etc/localime')

def set_language(location):
	if location.startswith("us"):
	   lang='en_US.UTF-8'
	   os.system('locale-gen %s' %(lang))
	   os.system('update-locale %s' %(lang))
	elif location.startswith("eu"):
	   lang='en_GB.UTF-8'
	   os.system('locale-gen %s' %(lang))
	   os.system('update-locale %s' %(lang))

set_utc_clock()
set_language(zone)
