#!/usr/bin/python
#
#    Fetch login credentials for EC2 
#    Copyright 2008 Canonical Ltd.
#
#    Author: Soren Hansen <soren@canonical.com>
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
import pwd

import ec2init

def setup_user_keys(keys, user, key_prefix):
    pwent = pwd.getpwnam(user)

    os.umask(077)
    if not os.path.exists('%s/.ssh' % pwent.pw_dir):
        os.mkdir('%s/.ssh' % pwent.pw_dir)

    authorized_keys = '%s/.ssh/authorized_keys' % pwent.pw_dir
    fp = open(authorized_keys, 'a')
    fp.write(''.join(['%s%s\n' % (key_prefix, key) for key in keys]))
    fp.close()

    os.chown(authorized_keys, pwent.pw_uid, pwent.pw_gid)

def main():
    ec2 = ec2init.EC2Init()

    user = ec2.get_cfg_option_str('user')
    disable_root = ec2.get_cfg_option_bool('disable_root')

    keys = ec2.get_ssh_keys()

    if user:
        setup_user_keys(keys, user, '')
     
    if disable_root:
        key_prefix = 'command="echo \'Please login as the ubuntu user rather than root user.\';echo;sleep 10" ' 
    else:
        key_prefix = ''

    setup_root_user(keys, 'root', key_prefix)

if __name__ == '__main__':
    main()
