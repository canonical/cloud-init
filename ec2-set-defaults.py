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

import subprocess

import ec2init

def get_location_from_availability_zone(availability_zone):
    if availability.startswith('us-'):
        return 'us'
    elif availability.startswith('eu-'):
        return 'eu'
    raise Exception('Could not determine location')
    
location_archive_map = { 
    'us' : 'http://us.ec2.archive.ubuntu.com/ubuntu',
    'eu' : 'http://eu.ec2.archive.ubuntu.com/ubuntu'
}

location_locale_map = { 
    'us' : 'en_US.UTF-8',
    'eu' : 'en_GB.UTF-8'
}

def main():
    ec2 = ec2init.EC2Init()

    location = get_location_from_availability_zone(ec2.get_availability_zone())

    locale = location_locale_map[location]
	subprocess.Popen(['locale-gen', locale]).communicate()
	subprocess.Popen(['update-locale', locale]).communicate()

if __name__ == '__main__':
    main()
