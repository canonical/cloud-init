#!/usr/bin/python
#
#    Fetch login credentials for EC2 
#    Copyright (C) 2008-2009 Canonical Ltd.
#
#    Author: Chuck Short <chuck.short@canonical.com>
#            Soren Hansen <soren@canonical.com>
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
from Cheetah.Template import Template

import ec2init

def main():
    ec2 = ec2init.EC2Init()

    hostname = ec2.get_hostname()

    subprocess.Popen(['hostname', hostname']).communicate()

    # replace the ubuntu hostname in /etc/hosts
    mp = {'hostname': hostname}
    t = Template(file="/etc/ec2-init/templates/hosts.tmpl", searchList=[mp])

    f = open("/etc/hosts", "w")
    f.write(t.respond())
    f.close()

if __name__ == '__main__':
    main()
