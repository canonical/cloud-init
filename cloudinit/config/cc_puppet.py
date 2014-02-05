# vi: ts=4 expandtab
#
#    Copyright (C) 2009-2010 Canonical Ltd.
#    Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
#    Author: Scott Moser <scott.moser@canonical.com>
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

from StringIO import StringIO

import os
import socket

from cloudinit import helpers
from cloudinit import util

PUPPET_CONF_PATH = '/etc/puppet/puppet.conf'
PUPPET_SSL_CERT_DIR = '/var/lib/puppet/ssl/certs/'
PUPPET_SSL_DIR = '/var/lib/puppet/ssl'
PUPPET_SSL_CERT_PATH = '/var/lib/puppet/ssl/certs/ca.pem'


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
    if not install and version:
        log.warn(("Puppet install set false but version supplied,"
                  " doing nothing."))
    elif install:
        log.debug(("Attempting to install puppet %s,"),
                   version if version else 'latest')
        cloud.distro.install_packages(('puppet', version))

    # ... and then update the puppet configuration
    if 'conf' in puppet_cfg:
        # Add all sections from the conf object to puppet.conf
        contents = util.load_file(PUPPET_CONF_PATH)
        # Create object for reading puppet.conf values
        puppet_config = helpers.DefaultingConfigParser()
        # Read puppet.conf values from original file in order to be able to
        # mix the rest up. First clean them up
        # (TODO(harlowja) is this really needed??)
        cleaned_lines = [i.lstrip() for i in contents.splitlines()]
        cleaned_contents = '\n'.join(cleaned_lines)
        puppet_config.readfp(StringIO(cleaned_contents),
                             filename=PUPPET_CONF_PATH)
        for (cfg_name, cfg) in puppet_cfg['conf'].iteritems():
            # Cert configuration is a special case
            # Dump the puppet master ca certificate in the correct place
            if cfg_name == 'ca_cert':
                # Puppet ssl sub-directory isn't created yet
                # Create it with the proper permissions and ownership
                util.ensure_dir(PUPPET_SSL_DIR, 0771)
                util.chownbyname(PUPPET_SSL_DIR, 'puppet', 'root')
                util.ensure_dir(PUPPET_SSL_CERT_DIR)
                util.chownbyname(PUPPET_SSL_CERT_DIR, 'puppet', 'root')
                util.write_file(PUPPET_SSL_CERT_PATH, str(cfg))
                util.chownbyname(PUPPET_SSL_CERT_PATH, 'puppet', 'root')
            else:
                # Iterate throug the config items, we'll use ConfigParser.set
                # to overwrite or create new items as needed
                for (o, v) in cfg.iteritems():
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
            util.rename(PUPPET_CONF_PATH, "%s.old" % (PUPPET_CONF_PATH))
            util.write_file(PUPPET_CONF_PATH, puppet_config.stringify())

    # Set it up so it autostarts
    _autostart_puppet(log)

    # Start puppetd
    util.subp(['service', 'puppet', 'start'], capture=False)
