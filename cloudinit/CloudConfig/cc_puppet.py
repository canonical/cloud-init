# vi: ts=4 expandtab
#
#    Copyright (C) 2009-2010 Canonical Ltd.
#
#    Author: Scott Moser <scott.moser@canonical.com>
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

def handle(name,cfg,cloud,log,args):
    # If there isn't a puppet key in the configuration don't do anything
    if not cfg.has_key('puppet'): return
    puppet_cfg = cfg['puppet']
    # Start by installing the puppet package ...
    e=os.environ.copy()
    e['DEBIAN_FRONTEND']='noninteractive'
    # Make sure that the apt database is updated since it's not run by
    # default
    # Note: we should have a helper to check if apt-get update 
    # has already been run on this instance to speed the boot time.
    subprocess.check_call(['apt-get', 'update'], env=e)
    subprocess.check_call(['apt-get', 'install', '--assume-yes',
                           'puppet'], env=e)
    # ... and then update the puppet configuration
    if puppet_cfg.has_key('conf'):
        # Add all sections from the conf object to puppet.conf
        puppet_conf_fh = open('/etc/puppet/puppet.conf', 'a')
        for cfg_name, cfg in puppet_cfg['conf'].iteritems():
            # ca_cert configuration is a special case
            # Dump the puppetmaster ca certificate in the correct place
            if cfg_name == 'ca_cert':
                # Puppet ssl sub-directory isn't created yet
                # Create it with the proper permissions and ownership
                os.makedirs('/var/lib/puppet/ssl')
                os.chmod('/var/lib/puppet/ssl', 0771)
                os.chown('/var/lib/puppet/ssl',
                         pwd.getpwnam('puppet').pw_uid, 0)
                os.makedirs('/var/lib/puppet/ssl/certs/')
                os.chown('/var/lib/puppet/ssl/certs/',
                         pwd.getpwnam('puppet').pw_uid, 0)
                ca_fh = open('/var/lib/puppet/ssl/certs/ca.pem', 'w')
                ca_fh.write(cfg)
                ca_fh.close()
                os.chown('/var/lib/puppet/ssl/certs/ca.pem',
                         pwd.getpwnam('puppet').pw_uid, 0)
            else:
                puppet_conf_fh.write("\n[%s]\n" % (cfg_name))
                for o, v in cfg.iteritems():
                    if o == 'certname':
                        # Expand %f as the fqdn
                        v = v.replace("%f", socket.getfqdn())
                        # Expand %i as the instance id
                        v = v.replace("%i",
                              cloud.datasource.get_instance_id())
                        # certname needs to be downcase
                        v = v.lower()
                    puppet_conf_fh.write("%s=\"%s\"\n" % (o, v))
        puppet_conf_fh.close()
    # Set puppet default file to automatically start
    subprocess.check_call(['sed', '-i',
                           '-e', 's/^START=.*/START=yes/',
                           '/etc/default/puppet'])
    # Start puppetd
    subprocess.check_call(['service', 'puppet', 'start'])

