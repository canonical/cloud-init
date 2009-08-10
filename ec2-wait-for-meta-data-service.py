#!/usr/bin/python
#
#    Wait for the meta-data service to turn up. If it never does, execute
#    the configured bailout
#    Copyright (C) 2009 Canonical Ltd.
#
#    Author: Soren Hansen <soren@canonical.com>
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
import sys

import ec2init

def main():
    ec2 = ec2init.EC2Init()
    if ec2.wait_or_bail():
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == '__main__':
    main()
