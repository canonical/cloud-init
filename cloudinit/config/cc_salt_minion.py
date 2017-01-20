# Author: Jeff Bauer <jbauer@rubic.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""
Salt Minion
-----------
**Summary:** set up and run salt minion

This module installs, configures and starts salt minion. If the ``salt_minion``
key is present in the config parts, then salt minion will be installed and
started. Configuration for salt minion can be specified in the ``conf`` key
under ``salt_minion``. Any conf values present there will be assigned in
``/etc/salt/minion``. The public and private keys to use for salt minion can be
specified with ``public_key`` and ``private_key`` respectively.

**Internal name:** ``cc_salt_minion``

**Module frequency:** per instance

**Supported distros:** all

**Config keys**::

    salt_minion:
        conf:
            master: salt.example.com
        public_key: |
            ------BEGIN PUBLIC KEY-------
            <key data>
            ------END PUBLIC KEY-------
        private_key: |
            ------BEGIN PRIVATE KEY------
            <key data>
            ------END PRIVATE KEY-------
"""

import os

from cloudinit import util

# Note: see http://saltstack.org/topics/installation/


def handle(name, cfg, cloud, log, _args):
    # If there isn't a salt key in the configuration don't do anything
    if 'salt_minion' not in cfg:
        log.debug(("Skipping module named %s,"
                   " no 'salt_minion' key in configuration"), name)
        return

    salt_cfg = cfg['salt_minion']

    # Start by installing the salt package ...
    cloud.distro.install_packages(('salt-minion',))

    # Ensure we can configure files at the right dir
    config_dir = salt_cfg.get("config_dir", '/etc/salt')
    util.ensure_dir(config_dir)

    # ... and then update the salt configuration
    if 'conf' in salt_cfg:
        # Add all sections from the conf object to /etc/salt/minion
        minion_config = os.path.join(config_dir, 'minion')
        minion_data = util.yaml_dumps(salt_cfg.get('conf'))
        util.write_file(minion_config, minion_data)

    # ... copy the key pair if specified
    if 'public_key' in salt_cfg and 'private_key' in salt_cfg:
        if os.path.isdir("/etc/salt/pki/minion"):
            pki_dir_default = "/etc/salt/pki/minion"
        else:
            pki_dir_default = "/etc/salt/pki"

        pki_dir = salt_cfg.get('pki_dir', pki_dir_default)
        with util.umask(0o77):
            util.ensure_dir(pki_dir)
            pub_name = os.path.join(pki_dir, 'minion.pub')
            pem_name = os.path.join(pki_dir, 'minion.pem')
            util.write_file(pub_name, salt_cfg['public_key'])
            util.write_file(pem_name, salt_cfg['private_key'])

    # restart salt-minion.  'service' will start even if not started.  if it
    # was started, it needs to be restarted for config change.
    util.subp(['service', 'salt-minion', 'restart'], capture=False)

# vi: ts=4 expandtab
