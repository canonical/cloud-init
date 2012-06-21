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

from cloudinit import helpers
from cloudinit import util

PUBCERT_FILE = "/etc/mcollective/ssl/server-public.pem"
PRICERT_FILE = "/etc/mcollective/ssl/server-private.pem"


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
        mcollective_config = helpers.DefaultingConfigParser()
        # Read server.cfg values from original file in order to be able to mix
        # the rest up
        server_cfg_fn = cloud.paths.join(True, '/etc/mcollective/server.cfg')
        old_contents = util.load_file(server_cfg_fn)
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
                                  filename=server_cfg_fn)
        for (cfg_name, cfg) in mcollective_cfg['conf'].iteritems():
            if cfg_name == 'public-cert':
                pubcert_fn = cloud.paths.join(True, PUBCERT_FILE)
                util.write_file(pubcert_fn, cfg, mode=0644)
                mcollective_config.set(cfg_name,
                    'plugin.ssl_server_public', pubcert_fn)
                mcollective_config.set(cfg_name, 'securityprovider', 'ssl')
            elif cfg_name == 'private-cert':
                pricert_fn = cloud.paths.join(True, PRICERT_FILE)
                util.write_file(pricert_fn, cfg, mode=0600)
                mcollective_config.set(cfg_name,
                    'plugin.ssl_server_private', pricert_fn)
                mcollective_config.set(cfg_name, 'securityprovider', 'ssl')
            else:
                # Iterate throug the config items, we'll use ConfigParser.set
                # to overwrite or create new items as needed
                for (o, v) in cfg.iteritems():
                    mcollective_config.set(cfg_name, o, v)
        # We got all our config as wanted we'll rename
        # the previous server.cfg and create our new one
        old_fn = cloud.paths.join(False, '/etc/mcollective/server.cfg.old')
        util.rename(server_cfg_fn, old_fn)
        # Now we got the whole file, write to disk except the section
        # we added so that config parser won't error out when trying to read.
        # Note below, that we've just used ConfigParser because it generally
        # works.  Below, we remove the initial 'nullsection' header.
        contents = mcollective_config.stringify()
        contents = contents.replace("%s\n" % (section_head), "")
        server_cfg_rw = cloud.paths.join(False, '/etc/mcollective/server.cfg')
        util.write_file(server_cfg_rw, contents, mode=0644)

    # Start mcollective
    util.subp(['service', 'mcollective', 'start'], capture=False)
