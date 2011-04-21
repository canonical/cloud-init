# vi: ts=4 expandtab
#
#    Author: Avishai Ish-Shalom <avishai@fewbytes.com>
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

ruby_packages = {'1.8': ('ruby', 'rubygems', 'ruby-dev', 'libopenssl-ruby'),
        '1.9.1': ('ruby1.9.1', 'rubygems1.9.1', 'ruby1.9.1-dev', 'libruby1.9.1'),
        '1.9': ('ruby1.9', 'rubygems1.9', 'ruby1.9-dev', 'libruby1.9') }

def handle(name,cfg,cloud,log,args):
    # If there isn't a chef key in the configuration don't do anything
    if not cfg.has_key('chef'): return
    chef_cfg = cfg['chef']
    ruby_version = '1.8'

    # Install chef packages from selected source
    if chef_cfg['install_type'] == "gems":
        if chef_cfg.has_key('ruby_version'):
            ruby_version = chef_cfg['ruby_version']
        cc.install_packages(ruby_packages['ruby_version'])
        chef_version_arg = ""
        if chef_cfg.has_key('version'):
            chef_version_arg = '-v %s' % chef_cfg['version']
        subprocess.check_call([gem_bin,'install','chef',chef_version_arg, '--no-ri','--no-rdoc','--no-test','-q'])
        os.mkdirs('/etc/chef', '/var/log/chef', '/var/lib/chef', '/var/cache/chef', '/var/backups/chef', '/var/run/chef')
        os.symlink('/var/lib/gem/%s/bin/chef-client' % ruby_version, '/usr/bin/chef-client')
    else:
        cc.install_packages(('chef',))

    # set the validation cert
    if chef_cfg.has_key('validation_cert'):
        with open('/etc/chef/validation.cert', 'w') as validation_cert_fh:
            validation_cert_fh.write(chef_cfg['validation_cert'])
    
    # create the chef config from template
    util.render_to_file('chef_client.rb', '/etc/chef/client.rb',
            {'server_url': chef_cfg['server_url'], 'validation_name': chef_cfg['validation_name'] || 'chef-validator'})

    chef_args = []
    # set the firstboot json
    if chef_cfg.has_key('run_list'):
        with open('/etc/chef/firstboot.json') as firstboot_json_fh:
            firstboot_json_fh.write("{\n\"run_list\":\n[\n")
            for runlist_item in chef_cfg['run_list']:
                firstboot_json_fh.write(runlist_item + "\n")
            firstboot_json_fh.write("]\n\}")
        chef_args.append('-j /etc/chef/firstboot.json')

    # and finally, run chef
    subprocess.check_call(['/usr/bin/chef-client'] + chef_args)
