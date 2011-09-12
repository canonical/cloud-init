# vi: ts=4 expandtab
#
#    Author: Avishai Ish-Shalom <avishai@fewbytes.com>
#    Author: Mike Moulton <mike@meltmedia.com>
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
import StringIO
import ConfigParser
import cloudinit.CloudConfig as cc
import cloudinit.util as util

ruby_packages = {'1.8': ('ruby', 'rubygems', 'ruby-dev', 'libopenssl-ruby'),
        '1.9.1': ('ruby1.9.1', 'ruby1.9.1-dev', 'libruby1.9.1'),
        '1.9': ('ruby1.9', 'ruby1.9-dev', 'libruby1.9') }

def handle(name,cfg,cloud,log,args):
    # If there isn't a chef key in the configuration don't do anything
    if not cfg.has_key('chef'): return
    chef_cfg = cfg['chef']

    # ensure the chef directories we use exist
    mkdirs(['/etc/chef', '/var/log/chef', '/var/lib/chef',
            '/var/cache/chef', '/var/backups/chef', '/var/run/chef'])

    # set the validation key based on the presence of either 'validation_key'
    # or 'validation_cert'. In the case where both exist, 'validation_key'
    # takes precedence
    if chef_cfg.has_key('validation_key') or chef_cfg.has_key('validation_cert'):
        validation_key = util.get_cfg_option_str(chef_cfg, 'validation_key',
                                                 chef_cfg['validation_cert'])
        with open('/etc/chef/validation.pem', 'w') as validation_key_fh:
            validation_key_fh.write(validation_key)

    validation_name = chef_cfg.get('validation_name','chef-validator')
    # create the chef config from template
    util.render_to_file('chef_client.rb', '/etc/chef/client.rb',
            {'server_url': chef_cfg['server_url'], 
             'node_name': util.get_cfg_option_str(chef_cfg, 'node_name', 
                                                  cloud.datasource.get_instance_id()),
             'environment': util.get_cfg_option_str(chef_cfg, 'environment',
                                                    '_default'),
             'validation_name': chef_cfg['validation_name']})

    # set the firstboot json
    with open('/etc/chef/firstboot.json', 'w') as firstboot_json_fh:
        firstboot_json_fh.write("{\n")
        if chef_cfg.has_key('run_list'):
            firstboot_json_fh.write("  \"run_list\": [\n")
            firstboot_json_fh.write(",\n".join(["    \"%s\"" % runlist_item
                                                for runlist_item in chef_cfg['run_list']]))
            firstboot_json_fh.write("\n  ]\n")
        firstboot_json_fh.write("}\n")  

    # If chef is not installed, we install chef based on 'install_type'
    if not os.path.isfile('/usr/bin/chef-client'):
        install_type = util.get_cfg_option_str(chef_cfg, 'install_type', 'packages')
        if install_type == "gems":
            # this will install and run the chef-client from gems
            chef_version = util.get_cfg_option_str(chef_cfg, 'version', None)
            ruby_version = util.get_cfg_option_str(chef_cfg, 'ruby_version', '1.8')
            install_chef_from_gems(ruby_version, chef_version)
            # and finally, run chef-client
            log.debug('running chef-client')
            subprocess.check_call(['/usr/bin/chef-client', '-d', '-i', '1800', '-s', '20'])
        else:
            # this will install and run the chef-client from packages
            cc.install_packages(('chef',))

def install_chef_from_gems(ruby_version, chef_version = None):
    cc.install_packages(ruby_packages[ruby_version])
    if not os.path.exists('/usr/bin/gem'):
      os.symlink('/usr/bin/gem%s' % ruby_version, '/usr/bin/gem')
    if not os.path.exists('/usr/bin/ruby'):
      os.symlink('/usr/bin/ruby%s' % ruby_version, '/usr/bin/ruby')
    if chef_version:
        subprocess.check_call(['/usr/bin/gem','install','chef',
                               '-v %s' % chef_version, '--no-ri',
                               '--no-rdoc','--bindir','/usr/bin','-q'])
    else:
        subprocess.check_call(['/usr/bin/gem','install','chef',
                               '--no-ri','--no-rdoc','--bindir',
                               '/usr/bin','-q'])

def ensure_dir(d):
    if not os.path.exists(d):
        os.makedirs(d)

def mkdirs(dirs):
    for d in dirs:
        ensure_dir(d)
