# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Avishai Ish-Shalom <avishai@fewbytes.com>
# Author: Mike Moulton <mike@meltmedia.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""
Chef
----
**Summary:** module that configures, starts and installs chef.

This module enables chef to be installed (from packages or
from gems, or from omnibus). Before this occurs chef configurations are
written to disk (validation.pem, client.pem, firstboot.json, client.rb),
and needed chef folders/directories are created (/etc/chef and /var/log/chef
and so-on). Then once installing proceeds correctly if configured chef will
be started (in daemon mode or in non-daemon mode) and then once that has
finished (if ran in non-daemon mode this will be when chef finishes
converging, if ran in daemon mode then no further actions are possible since
chef will have forked into its own process) then a post run function can
run that can do finishing activities (such as removing the validation pem
file).

**Internal name:** ``cc_chef``

**Module frequency:** per always

**Supported distros:** all

**Config keys**::

    chef:
       directories: (defaulting to /etc/chef, /var/log/chef, /var/lib/chef,
                     /var/cache/chef, /var/backups/chef, /var/run/chef)
       validation_cert: (optional string to be written to file validation_key)
                        special value 'system' means set use existing file
       validation_key: (optional the path for validation_cert. default
                        /etc/chef/validation.pem)
       firstboot_path: (path to write run_list and initial_attributes keys that
                        should also be present in this configuration, defaults
                        to /etc/chef/firstboot.json)
       exec: boolean to run or not run chef (defaults to false, unless
                                             a gem installed is requested
                                             where this will then default
                                             to true)

    chef.rb template keys (if falsey, then will be skipped and not
                           written to /etc/chef/client.rb)

    chef:
      client_key:
      environment:
      file_backup_path:
      file_cache_path:
      json_attribs:
      log_level:
      log_location:
      node_name:
      pid_file:
      server_url:
      show_time:
      ssl_verify_mode:
      validation_cert:
      validation_key:
      validation_name:
"""

import itertools
import json
import os

from cloudinit import templater
from cloudinit import url_helper
from cloudinit import util

import six

RUBY_VERSION_DEFAULT = "1.8"

CHEF_DIRS = tuple([
    '/etc/chef',
    '/var/log/chef',
    '/var/lib/chef',
    '/var/cache/chef',
    '/var/backups/chef',
    '/var/run/chef',
])
REQUIRED_CHEF_DIRS = tuple([
    '/etc/chef',
])

# Used if fetching chef from a omnibus style package
OMNIBUS_URL = "https://www.getchef.com/chef/install.sh"
OMNIBUS_URL_RETRIES = 5

CHEF_VALIDATION_PEM_PATH = '/etc/chef/validation.pem'
CHEF_FB_PATH = '/etc/chef/firstboot.json'
CHEF_RB_TPL_DEFAULTS = {
    # These are ruby symbols...
    'ssl_verify_mode': ':verify_none',
    'log_level': ':info',
    # These are not symbols...
    'log_location': '/var/log/chef/client.log',
    'validation_key': CHEF_VALIDATION_PEM_PATH,
    'validation_cert': None,
    'client_key': "/etc/chef/client.pem",
    'json_attribs': CHEF_FB_PATH,
    'file_cache_path': "/var/cache/chef",
    'file_backup_path': "/var/backups/chef",
    'pid_file': "/var/run/chef/client.pid",
    'show_time': True,
}
CHEF_RB_TPL_BOOL_KEYS = frozenset(['show_time'])
CHEF_RB_TPL_PATH_KEYS = frozenset([
    'log_location',
    'validation_key',
    'client_key',
    'file_cache_path',
    'json_attribs',
    'file_cache_path',
    'pid_file',
])
CHEF_RB_TPL_KEYS = list(CHEF_RB_TPL_DEFAULTS.keys())
CHEF_RB_TPL_KEYS.extend(CHEF_RB_TPL_BOOL_KEYS)
CHEF_RB_TPL_KEYS.extend(CHEF_RB_TPL_PATH_KEYS)
CHEF_RB_TPL_KEYS.extend([
    'server_url',
    'node_name',
    'environment',
    'validation_name',
])
CHEF_RB_TPL_KEYS = frozenset(CHEF_RB_TPL_KEYS)
CHEF_RB_PATH = '/etc/chef/client.rb'
CHEF_EXEC_PATH = '/usr/bin/chef-client'
CHEF_EXEC_DEF_ARGS = tuple(['-d', '-i', '1800', '-s', '20'])


def is_installed():
    if not os.path.isfile(CHEF_EXEC_PATH):
        return False
    if not os.access(CHEF_EXEC_PATH, os.X_OK):
        return False
    return True


def post_run_chef(chef_cfg, log):
    delete_pem = util.get_cfg_option_bool(chef_cfg,
                                          'delete_validation_post_exec',
                                          default=False)
    if delete_pem and os.path.isfile(CHEF_VALIDATION_PEM_PATH):
        os.unlink(CHEF_VALIDATION_PEM_PATH)


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
        'node_name': util.get_cfg_option_str(chef_cfg, 'node_name',
                                             default=iid),
        'environment': util.get_cfg_option_str(chef_cfg, 'environment',
                                               default='_default'),
        # These two are mandatory...
        'server_url': chef_cfg['server_url'],
        'validation_name': chef_cfg['validation_name'],
    })
    return params


def handle(name, cfg, cloud, log, _args):
    """Handler method activated by cloud-init."""

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

    vkey_path = chef_cfg.get('validation_key', CHEF_VALIDATION_PEM_PATH)
    vcert = chef_cfg.get('validation_cert')
    # special value 'system' means do not overwrite the file
    # but still render the template to contain 'validation_key'
    if vcert:
        if vcert != "system":
            util.write_file(vkey_path, vcert)
        elif not os.path.isfile(vkey_path):
            log.warn("chef validation_cert provided as 'system', but "
                     "validation_key path '%s' does not exist.",
                     vkey_path)

    # Create the chef config from template
    template_fn = cloud.get_template_filename('chef_client.rb')
    if template_fn:
        iid = str(cloud.datasource.get_instance_id())
        params = get_template_params(iid, chef_cfg, log)
        # Do a best effort attempt to ensure that the template values that
        # are associated with paths have there parent directory created
        # before they are used by the chef-client itself.
        param_paths = set()
        for (k, v) in params.items():
            if k in CHEF_RB_TPL_PATH_KEYS and v:
                param_paths.add(os.path.dirname(v))
        util.ensure_dirs(param_paths)
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
        run = install_chef(cloud, chef_cfg, log)
    elif is_installed():
        run = util.get_cfg_option_bool(chef_cfg, 'exec', default=False)
    else:
        run = False
    if run:
        run_chef(chef_cfg, log)
        post_run_chef(chef_cfg, log)


def run_chef(chef_cfg, log):
    log.debug('Running chef-client')
    cmd = [CHEF_EXEC_PATH]
    if 'exec_arguments' in chef_cfg:
        cmd_args = chef_cfg['exec_arguments']
        if isinstance(cmd_args, (list, tuple)):
            cmd.extend(cmd_args)
        elif isinstance(cmd_args, six.string_types):
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
    run = util.get_cfg_option_bool(chef_cfg, 'exec', default=False)
    if install_type == "gems":
        # This will install and run the chef-client from gems
        chef_version = util.get_cfg_option_str(chef_cfg, 'version', None)
        ruby_version = util.get_cfg_option_str(chef_cfg, 'ruby_version',
                                               RUBY_VERSION_DEFAULT)
        install_chef_from_gems(ruby_version, chef_version, cloud.distro)
        # Retain backwards compat, by preferring True instead of False
        # when not provided/overriden...
        run = util.get_cfg_option_bool(chef_cfg, 'exec', default=True)
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
            util.write_file(tmpf, content, mode=0o700)
            util.subp([tmpf], capture=False)
    else:
        log.warn("Unknown chef install type '%s'", install_type)
        run = False
    return run


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

# vi: ts=4 expandtab
