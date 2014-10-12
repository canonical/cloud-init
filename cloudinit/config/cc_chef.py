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

import itertools
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
REQUIRED_CHEF_DIRS = [
    '/etc/chef',
]

OMNIBUS_URL = "https://www.opscode.com/chef/install.sh"
OMNIBUS_URL_RETRIES = 5

CHEF_RB_TPL_DEFAULTS = {
    # These are ruby symbols...
    'ssl_verify_mode': ':verify_none',
    'log_level': ':info',
    # These are not symbols...
    'log_location': '/var/log/chef/client.log',
    'validation_key': "/etc/chef/validation.pem",
    'client_key': "/etc/chef/client.pem",
    'json_attribs': "/etc/chef/firstboot.json",
    'file_cache_path': "/var/cache/chef",
    'file_backup_path': "/var/backups/chef",
    'pid_file': "/var/run/chef/client.pid",
    'show_time': True,
}
CHEF_RB_TPL_BOOL_KEYS = frozenset(['show_time'])
CHEF_RB_TPL_KEYS = list(CHEF_RB_TPL_DEFAULTS.keys())
CHEF_RB_TPL_KEYS.extend(CHEF_RB_TPL_BOOL_KEYS)
CHEF_RB_TPL_KEYS.extend([
    'server_url',
    'node_name',
    'environment',
    'validation_name',
])
CHEF_RB_TPL_KEYS = frozenset(CHEF_RB_TPL_KEYS)
CHEF_RB_PATH = '/etc/chef/client.rb'
CHEF_FB_PATH = '/etc/chef/firstboot.json'
CHEF_EXEC_PATH = '/usr/bin/chef-client'
CHEF_EXEC_DEF_ARGS = tuple(['-d', '-i', '1800', '-s', '20'])


def is_installed():
    if not os.path.isfile(CHEF_EXEC_PATH):
        return False
    if not os.access(CHEF_EXEC_PATH, os.X_OK):
        return False
    return True


def get_template_params(iid, chef_cfg, log):
    params = CHEF_RB_TPL_DEFAULTS.copy()
    # Allow users to overwrite any of the keys they want (if they so choose),
    # when a value is None, then the value will be set to None and no boolean
    # or string version will be populated...
    for (k, v) in chef_cfg.items():
        if k not in CHEF_RB_TPL_KEYS:
            log.debug("Skipping unknown chef template key '%s'", k)
            continue
        if v is None:
            params[k] = None
        else:
            # This will make the value a boolean or string...
            if k in CHEF_RB_TPL_BOOL_KEYS:
                params[k] = util.get_cfg_option_bool(chef_cfg, k)
            else:
                params[k] = util.get_cfg_option_str(chef_cfg, k)
    # These ones are overwritten to be exact values...
    params.update({
        'generated_by': util.make_header(),
        'server_url': util.get_cfg_option_str(chef_cfg, 'server_url'),
        'node_name': util.get_cfg_option_str(chef_cfg, 'node_name',
                                             default=iid),
        'environment': util.get_cfg_option_str(chef_cfg, 'environment',
                                               default='_default'),
        'validation_name': util.get_cfg_option_str(chef_cfg,
                                                   'validation_name'),
    })
    return params


def handle(name, cfg, cloud, log, _args):

    # If there isn't a chef key in the configuration don't do anything
    if 'chef' not in cfg:
        log.debug(("Skipping module named %s,"
                  " no 'chef' key in configuration"), name)
        return
    chef_cfg = cfg['chef']

    # Ensure the chef directories we use exist
    chef_dirs = util.get_cfg_option_list(chef_cfg, 'directories')
    if not chef_dirs:
        chef_dirs = list(CHEF_DIRS)
    for d in itertools.chain(chef_dirs, REQUIRED_CHEF_DIRS):
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
        params = get_template_params(iid, chef_cfg, log)
        templater.render_to_file(template_fn, CHEF_RB_PATH, params)
    else:
        log.warn("No template found, not rendering to %s",
                 CHEF_RB_PATH)

    # Set the firstboot json
    fb_filename = util.get_cfg_option_str(chef_cfg, 'firstboot_path',
                                          default=CHEF_FB_PATH)
    if not fb_filename:
        log.info("First boot path empty, not writing first boot json file")
    else:
        initial_json = {}
        if 'run_list' in chef_cfg:
            initial_json['run_list'] = chef_cfg['run_list']
        if 'initial_attributes' in chef_cfg:
            initial_attributes = chef_cfg['initial_attributes']
            for k in list(initial_attributes.keys()):
                initial_json[k] = initial_attributes[k]
        util.write_file(fb_filename, json.dumps(initial_json))

    # Try to install chef, if its not already installed...
    force_install = util.get_cfg_option_bool(chef_cfg,
                                             'force_install', default=False)
    if not is_installed() or force_install:
        run_after = install_chef(cloud, chef_cfg, log)
        if run_after:
            run_chef(chef_cfg, log)


def run_chef(chef_cfg, log):
    log.debug('Running chef-client')
    cmd = [CHEF_EXEC_PATH]
    if 'exec_arguments' in chef_cfg:
        cmd_args = chef_cfg['exec_arguments']
        if isinstance(cmd_args, (list, tuple)):
            cmd.extend(cmd_args)
        elif isinstance(cmd_args, (str, basestring)):
            cmd.append(cmd_args)
        else:
            log.warn("Unknown type %s provided for chef"
                     " 'exec_arguments' expected list, tuple,"
                     " or string", type(cmd_args))
            cmd.extend(CHEF_EXEC_DEF_ARGS)
    else:
        cmd.extend(CHEF_EXEC_DEF_ARGS)
    util.subp(cmd, capture=False)


def install_chef(cloud, chef_cfg, log):
    # If chef is not installed, we install chef based on 'install_type'
    install_type = util.get_cfg_option_str(chef_cfg, 'install_type',
                                           'packages')
    run_after = util.get_cfg_option_bool(chef_cfg, 'exec_after_install',
                                         default=False)
    if install_type == "gems":
        # This will install and run the chef-client from gems
        chef_version = util.get_cfg_option_str(chef_cfg, 'version', None)
        ruby_version = util.get_cfg_option_str(chef_cfg, 'ruby_version',
                                               RUBY_VERSION_DEFAULT)
        install_chef_from_gems(cloud.distro, ruby_version, chef_version)
        # Retain backwards compat, but preferring True instead of False
        # when not provided/overriden...
        run_after = util.get_cfg_option_bool(chef_cfg, 'exec_after_install',
                                             default=True)
    elif install_type == 'packages':
        # This will install and run the chef-client from packages
        cloud.distro.install_packages(('chef',))
    elif install_type == 'omnibus':
        # This will install as a omnibus unified package
        url = util.get_cfg_option_str(chef_cfg, "omnibus_url", OMNIBUS_URL)
        retries = max(0, util.get_cfg_option_int(chef_cfg,
                                                 "omnibus_url_retries",
                                                 default=OMNIBUS_URL_RETRIES))
        content = url_helper.readurl(url=url, retries=retries)
        with util.tempdir() as tmpd:
            # Use tmpdir over tmpfile to avoid 'text file busy' on execute
            tmpf = "%s/chef-omnibus-install" % tmpd
            util.write_file(tmpf, str(content), mode=0700)
            util.subp([tmpf], capture=False)
    else:
        log.warn("Unknown chef install type '%s'", install_type)
        run_after = False
    return run_after


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
