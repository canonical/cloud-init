# Copyright (C) 2009-2011 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Marc Cluet <marc.cluet@canonical.com>
# Based on code by Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""
Mcollective
-----------
**Summary:** install, configure and start mcollective

This module installs, configures and starts mcollective. If the ``mcollective``
key is present in config, then mcollective will be installed and started.

Configuration for ``mcollective`` can be specified in the ``conf`` key under
``mcollective``. Each config value consists of a key value pair and will be
written to ``/etc/mcollective/server.cfg``. The ``public-cert`` and
``private-cert`` keys, if present in conf may be used to specify the public and
private certificates for mcollective. Their values will be written to
``/etc/mcollective/ssl/server-public.pem`` and
``/etc/mcollective/ssl/server-private.pem``.

.. note::
    The ec2 metadata service is readable by non-root users.
    If security is a concern, use include-once and ssl urls.

**Internal name:** ``cc_mcollective``

**Module frequency:** per instance

**Supported distros:** all

**Config keys**::

    mcollective:
        conf:
            <key>: <value>
            public-cert: |
                -------BEGIN CERTIFICATE--------
                <cert data>
                -------END CERTIFICATE--------
            private-cert: |
                -------BEGIN CERTIFICATE--------
                <cert data>
                -------END CERTIFICATE--------
"""

import errno

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
    # Read server.cfg (if it exists) values from the
    # original file in order to be able to mix the rest up.
    try:
        old_contents = util.load_file(server_cfg, quiet=False, decode=False)
        mcollective_config = ConfigObj(BytesIO(old_contents))
    except IOError as e:
        if e.errno != errno.ENOENT:
            raise
        else:
            LOG.debug("Did not find file %s (starting with an empty"
                      " config)", server_cfg)
            mcollective_config = ConfigObj()
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

    try:
        # We got all our config as wanted we'll copy
        # the previous server.cfg and overwrite the old with our new one
        util.copy(server_cfg, "%s.old" % (server_cfg))
    except IOError as e:
        if e.errno == errno.ENOENT:
            # Doesn't exist to copy...
            pass
        else:
            raise

    # Now we got the whole (new) file, write to disk...
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

# vi: ts=4 expandtab
