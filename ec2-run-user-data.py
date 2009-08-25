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
from xml.dom.minidom import parse, parseString

import ec2init

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
        return
    if payload.startswith('<appliance>'):
        content_type_handlers['text/x-appliance-config'](payload)


def handle_appliance_config(payload):
    app = ApplianceConfig(payload)
    app.handle()

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

content_type_handlers = { 'text/x-shellscript' : handle_shell_script,
                          'text/x-ebs-mount-description' : handle_ebs_mount_description,
                          'text/x-appliance-config': handle_appliance_config }

class ApplianceConfig(object):
    def __init__(self, data):
        self.data = data

    def handle(self):
        self.dom = parseString(self.data)

        if self.dom.childNodes[0].tagName == 'appliance':
            root = self.dom.childNodes[0]
        else:
            return

        for node in root.childNodes:
            if node.tagName == 'package':
                pkg = None
                for subnode in node.childNodes:
                    if subnode.nodeType == root.TEXT_NODE:
                        pkg = subnode.nodeValue
                if not pkg:
                    # Something's fishy. We should have been passed the name of
                    # a package.
                    return
                if node.getAttribute('action') == 'remove':
                    remove_package(pkg)
                else:
                    install_package(pkg)

def main():
    ec2 = ec2init.EC2Init()

    user_data = ec2.get_user_data()
    msg = parse_user_data(user_data)
    handle_part(msg)

def parse_user_data(user_data):
    return email.message_from_string(user_data)

def install_remove_package(pkg, action):
    apt_get = subprocess.Popen(['apt-get', action, pkg], stdout=subprocess.PIPE)
    logger_process = subprocess.Popen(['logger', '-t', 'user-data'], stdin=apt_get.stdout)
    logger_process.communicate()

def install_package(pkg):
    return install_remove_package(pkg, 'install')

def remove_package(pkg):
    return install_remove_package(pkg, 'remove')

if __name__ == '__main__':
    main()
