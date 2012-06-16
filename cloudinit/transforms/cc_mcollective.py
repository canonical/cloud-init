# vi: ts=4 expandtab
#
#    Copyright (C) 2009-2011 Canonical Ltd.
#    Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
#    Author: Marc Cluet <marc.cluet@canonical.com>
#    Based on code by Scott Moser <scott.moser@canonical.com>
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
import subprocess
import StringIO
import ConfigParser
import cloudinit.CloudConfig as cc
import cloudinit.util as util

pubcert_file = "/etc/mcollective/ssl/server-public.pem"
pricert_file = "/etc/mcollective/ssl/server-private.pem"


# Our fake header section
class FakeSecHead(object):
    def __init__(self, fp):
        self.fp = fp
        self.sechead = '[nullsection]\n'

    def readline(self):
        if self.sechead:
            try:
                return self.sechead
            finally:
                self.sechead = None
        else:
            return self.fp.readline()


def handle(_name, cfg, _cloud, _log, _args):
    # If there isn't a mcollective key in the configuration don't do anything
    if 'mcollective' not in cfg:
        return
    mcollective_cfg = cfg['mcollective']
    # Start by installing the mcollective package ...
    cc.install_packages(("mcollective",))

    # ... and then update the mcollective configuration
    if 'conf' in mcollective_cfg:
        # Create object for reading server.cfg values
        mcollective_config = ConfigParser.ConfigParser()
        # Read server.cfg values from original file in order to be able to mix
        # the rest up
        mcollective_config.readfp(FakeSecHead(open('/etc/mcollective/'
                                                   'server.cfg')))
        for cfg_name, cfg in mcollective_cfg['conf'].iteritems():
            if cfg_name == 'public-cert':
                util.write_file(pubcert_file, cfg, mode=0644)
                mcollective_config.set(cfg_name,
                    'plugin.ssl_server_public', pubcert_file)
                mcollective_config.set(cfg_name, 'securityprovider', 'ssl')
            elif cfg_name == 'private-cert':
                util.write_file(pricert_file, cfg, mode=0600)
                mcollective_config.set(cfg_name,
                    'plugin.ssl_server_private', pricert_file)
                mcollective_config.set(cfg_name, 'securityprovider', 'ssl')
            else:
                # Iterate throug the config items, we'll use ConfigParser.set
                # to overwrite or create new items as needed
                for o, v in cfg.iteritems():
                    mcollective_config.set(cfg_name, o, v)
        # We got all our config as wanted we'll rename
        # the previous server.cfg and create our new one
        os.rename('/etc/mcollective/server.cfg',
                  '/etc/mcollective/server.cfg.old')
        outputfile = StringIO.StringIO()
        mcollective_config.write(outputfile)
        # Now we got the whole file, write to disk except first line
        # Note below, that we've just used ConfigParser because it generally
        # works.  Below, we remove the initial 'nullsection' header
        # and then change 'key = value' to 'key: value'.  The global
        # search and replace of '=' with ':' could be problematic though.
        # this most likely needs fixing.
        util.write_file('/etc/mcollective/server.cfg',
            outputfile.getvalue().replace('[nullsection]\n', '').replace(' =',
                                                                         ':'),
            mode=0644)

    # Start mcollective
    subprocess.check_call(['service', 'mcollective', 'start'])
