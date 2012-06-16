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

from StringIO import StringIO

from cloudinit import cfg as config
from cloudinit import util

pubcert_file = "/etc/mcollective/ssl/server-public.pem"
pricert_file = "/etc/mcollective/ssl/server-private.pem"


def handle(name, cfg, cloud, log, _args):

    # If there isn't a mcollective key in the configuration don't do anything
    if 'mcollective' not in cfg:
        log.debug(("Skipping transform named %s, "
                   "no 'mcollective' key in configuration"), name)
        return

    mcollective_cfg = cfg['mcollective']

    # Start by installing the mcollective package ...
    cloud.distro.install_packages(("mcollective",))

    # ... and then update the mcollective configuration
    if 'conf' in mcollective_cfg:
        # Create object for reading server.cfg values
        mcollective_config = config.DefaultingConfigParser()
        # Read server.cfg values from original file in order to be able to mix
        # the rest up
        old_contents = util.load_file('/etc/mcollective/server.cfg')
        # It doesn't contain any sections so just add one temporarily
        # Use a hash id based off the contents,
        # just incase of conflicts... (try to not have any...)
        # This is so that an error won't occur when reading (and no 
        # sections exist in the file)
        section_tpl = "[nullsection_%s]"
        attempts = 0
        section_head = section_tpl % (attempts)
        while old_contents.find(section_head) != -1:
            attempts += 1
            section_head = section_tpl % (attempts)
        sectioned_contents = "%s\n%s" % (section_head, old_contents)
        mcollective_config.readfp(StringIO(sectioned_contents),
                                  filename='/etc/mcollective/server.cfg')
        for (cfg_name, cfg) in mcollective_cfg['conf'].iteritems():
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
                for (o, v) in cfg.iteritems():
                    mcollective_config.set(cfg_name, o, v)
        # We got all our config as wanted we'll rename
        # the previous server.cfg and create our new one
        util.rename('/etc/mcollective/server.cfg',
                    '/etc/mcollective/server.cfg.old')
        # Now we got the whole file, write to disk except the section 
        # we added so that config parser won't error out when trying to read.
        # Note below, that we've just used ConfigParser because it generally
        # works.  Below, we remove the initial 'nullsection' header.
        contents = mcollective_config.stringify()
        contents = contents.replace("%s\n" % (section_head), "")
        util.write_file('/etc/mcollective/server.cfg', contents, mode=0644)

    # Start mcollective
    util.subp(['service', 'mcollective', 'start'], capture=False)
