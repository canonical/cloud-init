#
#    Common code for the EC2 initialisation scripts in Ubuntu
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

import os
import socket
import urllib2
from   configobj import ConfigObj

import boto.utils

class EC2Init():
    api_ver  = '2008-02-01'
    conffile = '/etc/ec2-init/ec2-config.cfg'

    def __init__(self):
        self.meta_data_base_url = 'http://169.254.169.254/%s/meta-data' % self.api_ver
        self.user_data_base_url = 'http://169.254.169.254/%s/user-data' % self.api_ver
        self.config = ConfigObj(self.conffile)

    def wait_or_bail(self):
        if self.wait_for_metadata_service():
            return True
        else:
            bailout_command = self.get_cfg_option_str('bailout_command')
            if bailout_command:
                os.system(bailout_command)
            return False

    def get_cfg_option_bool(self, key):
        val = self.config[key]
        if val.lower() in ['1', 'on', 'yes']:
            return True
        return False

    def get_cfg_option_str(self, key):
        return config[key]

    def get_ssh_keys(self):
        conn = urllib2.urlopen('%s/public-keys/' % self.meta_data_base_url)
        data = conn.read()
        keyids = [line.split('=')[0] for line in data.split('\n')]
        return [urllib.urlopen('%s/public-keys/%d/openssh-key' % (self.meta_data_base_url, int(keyid))).read().rstrip() for keyid in keyids]

    def get_user_data(self):
        return boto.utils.get_instance_userdata()

    def get_instance_metadata(self):
        self.instance_metadata = getattr(self, 'instance_metadata', boto.utils.get_instance_metadata())
        return self.instance_metadata 

    def get_ami_id(self):
        return self.get_instance_metadata()['ami-id']
    
    def get_availability_zone(self):
        return self.get_instance_metadata()['availability-zone']

    def get_hostname(self):
        return self.get_instance_metadata()['local-hostname']

    def get_mirror_for_availability_zone(self):
        availability_zone = self.get_availability_zone()
        if zone.startswith("us"):
            return 'http://us.ec2.archive.ubuntu.com/ubuntu/'
        elif zone.startswith("eu"):
            return 'http://eu.ec2.archive.ubuntu.com/ubuntu/'

        return 'http://archive.ubuntu.com/ubuntu/'

    def wait_for_metadata_service(self):
        timeout = 2
        # This gives us about half an hour before we ultimately bail out
        for x in range(10):
            s = socket.socket()
            try:
                address = '169.254.169.254'
                port = 80
                s.connect((address,port))
                s.close()
                return True
            except socket.error, e:
                time.sleep(timeout)
                timeout = timeout * 2
        return False
