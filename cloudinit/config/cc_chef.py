# vi: ts=4 expandtab
#
#    Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
#    Author: Avishai Ish-Shalom <avishai@fewbytes.com>
#    Author: Mike Moulton <mike@meltmedia.com>
#    Author: Juerg Haefliger <juerg.haefliger@hp.com>
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

import json
import os

from cloudinit import templater
from cloudinit import url_helper
from cloudinit import util

RUBY_VERSION_DEFAULT = "1.8"

CHEF_DIRS = [
    '/etc/chef',
    '/var/log/chef',
    '/var/lib/chef',
    '/var/cache/chef',
    '/var/backups/chef',
    '/var/run/chef',
]

OMNIBUS_URL = "https://www.opscode.com/chef/install.sh"


def handle(name, cfg, cloud, log, _args):

    # If there isn't a chef key in the configuration don't do anything
    if 'chef' not in cfg:
        log.debug(("Skipping module named %s,"
                  " no 'chef' key in configuration"), name)
        return
    chef_cfg = cfg['chef']

    # Ensure the chef directories we use exist
    for d in CHEF_DIRS:
        util.ensure_dir(d)

    # Set the validation key based on the presence of either 'validation_key'
    # or 'validation_cert'. In the case where both exist, 'validation_key'
    # takes precedence
    for key in ('validation_key', 'validation_cert'):
        if key in chef_cfg and chef_cfg[key]:
            util.write_file('/etc/chef/validation.pem', chef_cfg[key])
            break

    # Create the chef config from template
    template_fn = cloud.get_template_filename('chef_client.rb')
    if template_fn:
        iid = str(cloud.datasource.get_instance_id())
        params = {
            'server_url': chef_cfg['server_url'],
            'node_name': util.get_cfg_option_str(chef_cfg, 'node_name', iid),
            'environment': util.get_cfg_option_str(chef_cfg, 'environment',
                                                   '_default'),
            'validation_name': chef_cfg['validation_name']
        }
        templater.render_to_file(template_fn, '/etc/chef/client.rb', params)
    else:
        log.warn("No template found, not rendering to /etc/chef/client.rb")

    # set the firstboot json
    initial_json = {}
    if 'run_list' in chef_cfg:
        initial_json['run_list'] = chef_cfg['run_list']
    if 'initial_attributes' in chef_cfg:
        initial_attributes = chef_cfg['initial_attributes']
        for k in list(initial_attributes.keys()):
            initial_json[k] = initial_attributes[k]
    util.write_file('/etc/chef/firstboot.json', json.dumps(initial_json))

    # If chef is not installed, we install chef based on 'install_type'
    if (not os.path.isfile('/usr/bin/chef-client') or
            util.get_cfg_option_bool(chef_cfg,
                'force_install', default=False)):

        install_type = util.get_cfg_option_str(chef_cfg, 'install_type',
                                               'packages')
        if install_type == "gems":
            # this will install and run the chef-client from gems
            chef_version = util.get_cfg_option_str(chef_cfg, 'version', None)
            ruby_version = util.get_cfg_option_str(chef_cfg, 'ruby_version',
                                                   RUBY_VERSION_DEFAULT)
            install_chef_from_gems(cloud.distro, ruby_version, chef_version)
            # and finally, run chef-client
            log.debug('Running chef-client')
            util.subp(['/usr/bin/chef-client',
                       '-d', '-i', '1800', '-s', '20'], capture=False)
        elif install_type == 'packages':
            # this will install and run the chef-client from packages
            cloud.distro.install_packages(('chef',))
        elif install_type == 'omnibus':
            url = util.get_cfg_option_str(chef_cfg, "omnibus_url", OMNIBUS_URL)
            content = url_helper.readurl(url=url, retries=5)
            with util.tempdir() as tmpd:
                # use tmpd over tmpfile to avoid 'Text file busy' on execute
                tmpf = "%s/chef-omnibus-install" % tmpd
                util.write_file(tmpf, str(content), mode=0700)
                util.subp([tmpf], capture=False)
        else:
            log.warn("Unknown chef install type %s", install_type)


def get_ruby_packages(version):
    # return a list of packages needed to install ruby at version
    pkgs = ['ruby%s' % version, 'ruby%s-dev' % version]
    if version == "1.8":
        pkgs.extend(('libopenssl-ruby1.8', 'rubygems1.8'))
    return pkgs


def install_chef_from_gems(ruby_version, chef_version, distro):
    distro.install_packages(get_ruby_packages(ruby_version))
    if not os.path.exists('/usr/bin/gem'):
        util.sym_link('/usr/bin/gem%s' % ruby_version, '/usr/bin/gem')
    if not os.path.exists('/usr/bin/ruby'):
        util.sym_link('/usr/bin/ruby%s' % ruby_version, '/usr/bin/ruby')
    if chef_version:
        util.subp(['/usr/bin/gem', 'install', 'chef',
                  '-v %s' % chef_version, '--no-ri',
                  '--no-rdoc', '--bindir', '/usr/bin', '-q'], capture=False)
    else:
        util.subp(['/usr/bin/gem', 'install', 'chef',
                  '--no-ri', '--no-rdoc', '--bindir',
                  '/usr/bin', '-q'], capture=False)
