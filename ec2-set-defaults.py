#!/usr/bin/python
#
#    Fetch the availabity zone and create the sources.list
#    Copyright (C) 2008-2009 Canonical Ltd.
#
#    Authors: Chuck Short <chuck.short@canonical.com>
#             Soren Hansen <soren@canonical.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License version 3, as
#    published by the Free Software Foundation.
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

def main():
    ec2 = ec2init.EC2Init()

    availability_zone = ec2.get_availability_zone()
    location          = ec2.get_location_from_availability_zone(availability_zone)
    mirror            = ec2.get_mirror_from_availability_zone(availability_zone)

    locale = ec2.location_locale_map[location]
    apply_locale(locale)

    generate_sources_list(mirror)

def apply_locale(locale):
    subprocess.Popen(['locale-gen', locale]).communicate()
    subprocess.Popen(['update-locale', locale]).communicate()

def generate_sources_list(self, mirror)
    stdout, stderr = subprocess.Popen(['lsb_release', '-cs'], stdout=subprocess.PIPE).communicate()
    codename = stdout.strip()

    mp = { 'mirror' : mirror, 'codename' : codename }
    t = Template(file='/etc/ec2-init/templates/sources.list.tmpl', searchList=[mp])
    f = open(SOURCES_LIST, 'w')
    f.write(t.respond())
    f.close()

if __name__ == '__main__':
    main()
