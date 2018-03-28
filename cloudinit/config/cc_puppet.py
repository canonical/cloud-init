# Copyright (C) 2009-2010 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""
Puppet
------
**Summary:** install, configure and start puppet

This module handles puppet installation and configuration. If the ``puppet``
key does not exist in global configuration, no action will be taken. If a
config entry for ``puppet`` is present, then by default the latest version of
puppet will be installed. If ``install`` is set to ``false``, puppet will not
be installed. However, this will result in an error if puppet is not already
present on the system. The version of puppet to be installed can be specified
under ``version``, and defaults to ``none``, which selects the latest version
in the repos. If the ``puppet`` config key exists in the config archive, this
module will attempt to start puppet even if no installation was performed.

The module also provides keys for configuring the new puppet 4 paths and
installing the puppet package from the puppetlabs repositories:
https://docs.puppet.com/puppet/4.2/reference/whered_it_go.html
The keys are ``package_name``, ``conf_file`` and ``ssl_dir``. If unset, their
values will default to ones that work with puppet 3.x and with distributions
that ship modified puppet 4.x that uses the old paths.

Puppet configuration can be specified under the ``conf`` key. The
configuration is specified as a dictionary containing high-level ``<section>``
keys and lists of ``<key>=<value>`` pairs within each section. Each section
name and ``<key>=<value>`` pair is written directly to ``puppet.conf``. As
such,  section names should be one of: ``main``, ``master``, ``agent`` or
``user`` and keys should be valid puppet configuration options. The
``certname`` key supports string substitutions for ``%i`` and ``%f``,
corresponding to the instance id and fqdn of the machine respectively.
If ``ca_cert`` is present, it will not be written to ``puppet.conf``, but
instead will be used as the puppermaster certificate. It should be specified
in pem format as a multi-line string (using the ``|`` yaml notation).

**Internal name:** ``cc_puppet``

**Module frequency:** per instance

**Supported distros:** all

**Config keys**::

    puppet:
        install: <true/false>
        version: <version>
        conf_file: '/etc/puppet/puppet.conf'
        ssl_dir: '/var/lib/puppet/ssl'
        package_name: 'puppet'
        conf:
            agent:
                server: "puppetmaster.example.org"
                certname: "%i.%f"
                ca_cert: |
                    -------BEGIN CERTIFICATE-------
                    <cert data>
                    -------END CERTIFICATE-------
"""

from six import StringIO

import os
import socket

from cloudinit import helpers
from cloudinit import util

PUPPET_CONF_PATH = '/etc/puppet/puppet.conf'
PUPPET_SSL_DIR = '/var/lib/puppet/ssl'
PUPPET_PACKAGE_NAME = 'puppet'


class PuppetConstants(object):

    def __init__(self, puppet_conf_file, puppet_ssl_dir, log):
        self.conf_path = puppet_conf_file
        self.ssl_dir = puppet_ssl_dir
        self.ssl_cert_dir = os.path.join(puppet_ssl_dir, "certs")
        self.ssl_cert_path = os.path.join(self.ssl_cert_dir, "ca.pem")


def _autostart_puppet(log):
    # Set puppet to automatically start
    if os.path.exists('/etc/default/puppet'):
        util.subp(['sed', '-i',
                   '-e', 's/^START=.*/START=yes/',
                   '/etc/default/puppet'], capture=False)
    elif os.path.exists('/bin/systemctl'):
        util.subp(['/bin/systemctl', 'enable', 'puppet.service'],
                  capture=False)
    elif os.path.exists('/sbin/chkconfig'):
        util.subp(['/sbin/chkconfig', 'puppet', 'on'], capture=False)
    else:
        log.warn(("Sorry we do not know how to enable"
                  " puppet services on this system"))


def handle(name, cfg, cloud, log, _args):
    # If there isn't a puppet key in the configuration don't do anything
    if 'puppet' not in cfg:
        log.debug(("Skipping module named %s,"
                   " no 'puppet' configuration found"), name)
        return

    puppet_cfg = cfg['puppet']
    # Start by installing the puppet package if necessary...
    install = util.get_cfg_option_bool(puppet_cfg, 'install', True)
    version = util.get_cfg_option_str(puppet_cfg, 'version', None)
    package_name = util.get_cfg_option_str(
        puppet_cfg, 'package_name', PUPPET_PACKAGE_NAME)
    conf_file = util.get_cfg_option_str(
        puppet_cfg, 'conf_file', PUPPET_CONF_PATH)
    ssl_dir = util.get_cfg_option_str(puppet_cfg, 'ssl_dir', PUPPET_SSL_DIR)

    p_constants = PuppetConstants(conf_file, ssl_dir, log)
    if not install and version:
        log.warn(("Puppet install set false but version supplied,"
                  " doing nothing."))
    elif install:
        log.debug(("Attempting to install puppet %s,"),
                  version if version else 'latest')

        cloud.distro.install_packages((package_name, version))

    # ... and then update the puppet configuration
    if 'conf' in puppet_cfg:
        # Add all sections from the conf object to puppet.conf
        contents = util.load_file(p_constants.conf_path)
        # Create object for reading puppet.conf values
        puppet_config = helpers.DefaultingConfigParser()
        # Read puppet.conf values from original file in order to be able to
        # mix the rest up. First clean them up
        # (TODO(harlowja) is this really needed??)
        cleaned_lines = [i.lstrip() for i in contents.splitlines()]
        cleaned_contents = '\n'.join(cleaned_lines)
        # Move to puppet_config.read_file when dropping py2.7
        puppet_config.readfp(   # pylint: disable=W1505
            StringIO(cleaned_contents),
            filename=p_constants.conf_path)
        for (cfg_name, cfg) in puppet_cfg['conf'].items():
            # Cert configuration is a special case
            # Dump the puppet master ca certificate in the correct place
            if cfg_name == 'ca_cert':
                # Puppet ssl sub-directory isn't created yet
                # Create it with the proper permissions and ownership
                util.ensure_dir(p_constants.ssl_dir, 0o771)
                util.chownbyname(p_constants.ssl_dir, 'puppet', 'root')
                util.ensure_dir(p_constants.ssl_cert_dir)

                util.chownbyname(p_constants.ssl_cert_dir, 'puppet', 'root')
                util.write_file(p_constants.ssl_cert_path, cfg)
                util.chownbyname(p_constants.ssl_cert_path, 'puppet', 'root')
            else:
                # Iterate through the config items, we'll use ConfigParser.set
                # to overwrite or create new items as needed
                for (o, v) in cfg.items():
                    if o == 'certname':
                        # Expand %f as the fqdn
                        # TODO(harlowja) should this use the cloud fqdn??
                        v = v.replace("%f", socket.getfqdn())
                        # Expand %i as the instance id
                        v = v.replace("%i", cloud.get_instance_id())
                        # certname needs to be downcased
                        v = v.lower()
                    puppet_config.set(cfg_name, o, v)
            # We got all our config as wanted we'll rename
            # the previous puppet.conf and create our new one
            util.rename(p_constants.conf_path, "%s.old"
                        % (p_constants.conf_path))
            util.write_file(p_constants.conf_path, puppet_config.stringify())

    # Set it up so it autostarts
    _autostart_puppet(log)

    # Start puppetd
    util.subp(['service', 'puppet', 'start'], capture=False)

# vi: ts=4 expandtab
