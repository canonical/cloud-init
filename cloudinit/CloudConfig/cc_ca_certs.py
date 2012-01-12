# vi: ts=4 expandtab
#
#    Author: Mike Milner <mike.milner@canonical.com>
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
import os
import pwd
import socket
import subprocess
import json
import StringIO
import ConfigParser
import cloudinit.CloudConfig as cc
import cloudinit.util as util

def handle(name, cfg, cloud, log, args):
    # If there isn't a chef key in the configuration don't do anything
    if not cfg.has_key('ca-certs'):
        return
    ca_cert_cfg = cfg['ca-certs']

    # set the validation key based on the presence of either 'validation_key'
    # or 'validation_cert'. In the case where both exist, 'validation_key'
    # takes precedence
    if ca_cert_cfg.has_key('trusted'):
        trusted_certs = util.get_cfg_option_str(chef_cfg, 'trusted')
        with open('/etc/cert.pem', 'w') as cert_file:
            cert_file.write(trusted_certs)
