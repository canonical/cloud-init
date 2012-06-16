# vi: ts=4 expandtab
#
#    Author: Jeff Bauer <jbauer@rubic.com>
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
import os.path
import subprocess
import cloudinit.CloudConfig as cc
import yaml


def handle(_name, cfg, _cloud, _log, _args):
    # If there isn't a salt key in the configuration don't do anything
    if 'salt_minion' not in cfg:
        return
    salt_cfg = cfg['salt_minion']
    # Start by installing the salt package ...
    cc.install_packages(("salt",))
    config_dir = '/etc/salt'
    if not os.path.isdir(config_dir):
        os.makedirs(config_dir)
    # ... and then update the salt configuration
    if 'conf' in salt_cfg:
        # Add all sections from the conf object to /etc/salt/minion
        minion_config = os.path.join(config_dir, 'minion')
        yaml.dump(salt_cfg['conf'],
                  file(minion_config, 'w'),
                  default_flow_style=False)
    # ... copy the key pair if specified
    if 'public_key' in salt_cfg and 'private_key' in salt_cfg:
        pki_dir = '/etc/salt/pki'
        cumask = os.umask(077)
        if not os.path.isdir(pki_dir):
            os.makedirs(pki_dir)
        pub_name = os.path.join(pki_dir, 'minion.pub')
        pem_name = os.path.join(pki_dir, 'minion.pem')
        with open(pub_name, 'w') as f:
            f.write(salt_cfg['public_key'])
        with open(pem_name, 'w') as f:
            f.write(salt_cfg['private_key'])
        os.umask(cumask)

    # Start salt-minion
    subprocess.check_call(['service', 'salt-minion', 'start'])
