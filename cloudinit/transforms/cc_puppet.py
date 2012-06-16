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

import os
import os.path
import pwd
import socket
import subprocess
import StringIO
import ConfigParser
import cloudinit.CloudConfig as cc
import cloudinit.util as util


def handle(_name, cfg, cloud, log, _args):
    # If there isn't a puppet key in the configuration don't do anything
    if 'puppet' not in cfg:
        return
    puppet_cfg = cfg['puppet']
    # Start by installing the puppet package ...
    cc.install_packages(("puppet",))

    # ... and then update the puppet configuration
    if 'conf' in puppet_cfg:
        # Add all sections from the conf object to puppet.conf
        puppet_conf_fh = open('/etc/puppet/puppet.conf', 'r')
        # Create object for reading puppet.conf values
        puppet_config = ConfigParser.ConfigParser()
        # Read puppet.conf values from original file in order to be able to
        # mix the rest up
        puppet_config.readfp(StringIO.StringIO(''.join(i.lstrip() for i in
                                               puppet_conf_fh.readlines())))
        # Close original file, no longer needed
        puppet_conf_fh.close()
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
                util.restorecon_if_possible('/var/lib/puppet', recursive=True)
            else:
                #puppet_conf_fh.write("\n[%s]\n" % (cfg_name))
                # If puppet.conf already has this section we don't want to
                # write it again
                if puppet_config.has_section(cfg_name) == False:
                    puppet_config.add_section(cfg_name)
                # Iterate throug the config items, we'll use ConfigParser.set
                # to overwrite or create new items as needed
                for o, v in cfg.iteritems():
                    if o == 'certname':
                        # Expand %f as the fqdn
                        v = v.replace("%f", socket.getfqdn())
                        # Expand %i as the instance id
                        v = v.replace("%i",
                              cloud.datasource.get_instance_id())
                        # certname needs to be downcase
                        v = v.lower()
                    puppet_config.set(cfg_name, o, v)
                    #puppet_conf_fh.write("%s=%s\n" % (o, v))
            # We got all our config as wanted we'll rename
            # the previous puppet.conf and create our new one
            os.rename('/etc/puppet/puppet.conf', '/etc/puppet/puppet.conf.old')
            with open('/etc/puppet/puppet.conf', 'wb') as configfile:
                puppet_config.write(configfile)
            util.restorecon_if_possible('/etc/puppet/puppet.conf')
    # Set puppet to automatically start
    if os.path.exists('/etc/default/puppet'):
        subprocess.check_call(['sed', '-i',
                               '-e', 's/^START=.*/START=yes/',
                               '/etc/default/puppet'])
    elif os.path.exists('/bin/systemctl'):
        subprocess.check_call(['/bin/systemctl', 'enable', 'puppet.service'])
    elif os.path.exists('/sbin/chkconfig'):
        subprocess.check_call(['/sbin/chkconfig', 'puppet', 'on'])
    else:
        log.warn("Do not know how to enable puppet service on this system")
    # Start puppetd
    subprocess.check_call(['service', 'puppet', 'start'])
