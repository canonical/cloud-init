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

import six
from six import BytesIO

# Used since this can maintain comments
# and doesn't need a top level section
from configobj import ConfigObj

from cloudinit import log as logging
from cloudinit import util

PUBCERT_FILE = "/etc/mcollective/ssl/server-public.pem"
PRICERT_FILE = "/etc/mcollective/ssl/server-private.pem"
SERVER_CFG = '/etc/mcollective/server.cfg'

LOG = logging.getLogger(__name__)


def configure(config, server_cfg=SERVER_CFG,
              pubcert_file=PUBCERT_FILE, pricert_file=PRICERT_FILE):
    # Read server.cfg values from the
    # original file in order to be able to mix the rest up
    try:
        mcollective_config = ConfigObj(server_cfg, file_error=True)
        existed = True
    except IOError:
        LOG.debug("Did not find file %s", server_cfg)
        mcollective_config = ConfigObj()
        existed = False

    for (cfg_name, cfg) in config.items():
        if cfg_name == 'public-cert':
            util.write_file(pubcert_file, cfg, mode=0o644)
            mcollective_config[
                'plugin.ssl_server_public'] = pubcert_file
            mcollective_config['securityprovider'] = 'ssl'
        elif cfg_name == 'private-cert':
            util.write_file(pricert_file, cfg, mode=0o600)
            mcollective_config[
                'plugin.ssl_server_private'] = pricert_file
            mcollective_config['securityprovider'] = 'ssl'
        else:
            if isinstance(cfg, six.string_types):
                # Just set it in the 'main' section
                mcollective_config[cfg_name] = cfg
            elif isinstance(cfg, (dict)):
                # Iterate through the config items, create a section if
                # it is needed and then add/or create items as needed
                if cfg_name not in mcollective_config.sections:
                    mcollective_config[cfg_name] = {}
                for (o, v) in cfg.items():
                    mcollective_config[cfg_name][o] = v
            else:
                # Otherwise just try to convert it to a string
                mcollective_config[cfg_name] = str(cfg)

    if existed:
        # We got all our config as wanted we'll rename
        # the previous server.cfg and create our new one
        util.rename(server_cfg, "%s.old" % (server_cfg))

    # Now we got the whole file, write to disk...
    contents = BytesIO()
    mcollective_config.write(contents)
    util.write_file(server_cfg, contents.getvalue(), mode=0o644)


def handle(name, cfg, cloud, log, _args):

    # If there isn't a mcollective key in the configuration don't do anything
    if 'mcollective' not in cfg:
        log.debug(("Skipping module named %s, "
                   "no 'mcollective' key in configuration"), name)
        return

    mcollective_cfg = cfg['mcollective']

    # Start by installing the mcollective package ...
    cloud.distro.install_packages(("mcollective",))

    # ... and then update the mcollective configuration
    if 'conf' in mcollective_cfg:
        configure(config=mcollective_cfg['conf'])

    # restart mcollective to handle updated config
    util.subp(['service', 'mcollective', 'restart'], capture=False)
