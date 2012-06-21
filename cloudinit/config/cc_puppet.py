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
import pwd
import socket

from cloudinit import helpers
from cloudinit import util


def handle(name, cfg, cloud, log, _args):
    # If there isn't a puppet key in the configuration don't do anything
    if 'puppet' not in cfg:
        log.debug(("Skipping transform named %s,"
                   " no 'puppet' configuration found"), name)
        return

    puppet_cfg = cfg['puppet']

    # Start by installing the puppet package ...
    cloud.distro.install_packages(["puppet"])

    # ... and then update the puppet configuration
    if 'conf' in puppet_cfg:
        # Add all sections from the conf object to puppet.conf
        puppet_conf_fn = cloud.paths.join(False, '/etc/puppet/puppet.conf')
        contents = util.load_file(puppet_conf_fn)
        # Create object for reading puppet.conf values
        puppet_config = helpers.DefaultingConfigParser()
        # Read puppet.conf values from original file in order to be able to
        # mix the rest up. First clean them up (TODO is this really needed??)
        cleaned_lines = [i.lstrip() for i in contents.splitlines()]
        cleaned_contents = '\n'.join(cleaned_lines)
        puppet_config.readfp(StringIO(cleaned_contents),
                             filename=puppet_conf_fn)
        for (cfg_name, cfg) in puppet_cfg['conf'].iteritems():
            # Cert configuration is a special case
            # Dump the puppet master ca certificate in the correct place
            if cfg_name == 'ca_cert':
                # Puppet ssl sub-directory isn't created yet
                # Create it with the proper permissions and ownership
                pp_ssl_dir = cloud.paths.join(False, '/var/lib/puppet/ssl')
                util.ensure_dir(pp_ssl_dir, 0771)
                util.chownbyid(pp_ssl_dir,
                               pwd.getpwnam('puppet').pw_uid, 0)
                pp_ssl_certs = cloud.paths.join(False,
                                                '/var/lib/puppet/ssl/certs/')
                util.ensure_dir(pp_ssl_certs)
                util.chownbyid(pp_ssl_certs,
                               pwd.getpwnam('puppet').pw_uid, 0)
                pp_ssl_ca_certs = cloud.paths.join(False,
                                                   ('/var/lib/puppet/'
                                                    'ssl/certs/ca.pem'))
                util.write_file(pp_ssl_ca_certs, cfg)
                util.chownbyid(pp_ssl_ca_certs,
                               pwd.getpwnam('puppet').pw_uid, 0)
            else:
                # Iterate throug the config items, we'll use ConfigParser.set
                # to overwrite or create new items as needed
                for (o, v) in cfg.iteritems():
                    if o == 'certname':
                        # Expand %f as the fqdn
                        # TODO should this use the cloud fqdn??
                        v = v.replace("%f", socket.getfqdn())
                        # Expand %i as the instance id
                        v = v.replace("%i", cloud.get_instance_id())
                        # certname needs to be downcased
                        v = v.lower()
                    puppet_config.set(cfg_name, o, v)
            # We got all our config as wanted we'll rename
            # the previous puppet.conf and create our new one
            puppet_conf_old_fn = "%s.old" % (puppet_conf_fn)
            util.rename(puppet_conf_fn, puppet_conf_old_fn)
            util.write_file(puppet_conf_fn, puppet_config.stringify())

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

    # Start puppetd
    util.subp(['service', 'puppet', 'start'], capture=False)
