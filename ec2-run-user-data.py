#!/usr/bin/python
#
#    Fetch and run user-data from EC2
#    Copyright (C) 2008-2009 Canonical Ltd.
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

import email
import os
import subprocess
import tempfile

import ec2init

content_type_handlers = { 'text/x-shellscript' : handle_shell_script,
                          'text/x-ebs-mount-description' : handle_ebs_mount_description }

def main():
    ec2 = ec2init.EC2Init()

    user_data = ec2.get_user_data()

    msg = email.message_from_string(user_data)
    handle_part(msg)

def handle_part(part):
    if part.is_multipart():
        for p in part.get_payload():
            handle_part(p)
    else:
        if part.get_content_type() in content_type_handlers:
            content_type_handlers[part.get_content_type](part.get_payload())
            return

        handle_unknown_payload(part.get_payload())

def handle_unknown_payload(payload):
    # Try to detect magic
    if payload.startswith('#!'):
        content_type_handlers['text/x-shellscript'](payload)

def handle_ebs_mount_description(payload):
    (volume_description, path) = payload.split(':')
    (identifier_type, identifier) = volume_description.split('=')

    if identifier_type == 'device':
        device = identifier
#    Perhaps some day the volume id -> device path mapping
#    will be exposed through meta-data.
#    elif identifier_type == 'volume':
#        device = extract_device_name_from_meta_data
    else:
        return

def handle_shell_script(payload):
    (fd, path) = tempfile.mkstemp()
    fp = os.fdopen(fd, 'a')
    fp.write(payload)
    fp.close()
    os.chmod(path, 0700)

    # Run the user data script and pipe its output to logger
    user_data_process = subprocess.Popen([path], stdout=subprocess.PIPE)
    logger_process = subprocess.Popen(['logger', '-t', 'user-data'], stdin=user_data_process.stdout)
    logger_process.communicate()
    
    os.unlink(path)

if __name__ == '__main__':
    main()
