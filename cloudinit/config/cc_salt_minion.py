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
specified with ``public_key`` and ``private_key`` respectively. Optionally if
you have a custom package name, service name or config directory you can
specify them with ``pkg_name``, ``service_name`` and ``config_dir``.

**Internal name:** ``cc_salt_minion``

**Module frequency:** per instance

**Supported distros:** all

**Config keys**::

    salt_minion:
        pkg_name: 'salt-minion'
        service_name: 'salt-minion'
        config_dir: '/etc/salt'
        conf:
            master: salt.example.com
        grains:
            role:
                - web
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

# Note: see https://docs.saltstack.com/en/latest/topics/installation/
# Note: see https://docs.saltstack.com/en/latest/ref/configuration/


class SaltConstants(object):
    """
    defines default distribution specific salt variables
    """
    def __init__(self, cfg):

        # constants tailored for FreeBSD
        if util.is_FreeBSD():
            self.pkg_name = 'py27-salt'
            self.srv_name = 'salt_minion'
            self.conf_dir = '/usr/local/etc/salt'
        # constants for any other OS
        else:
            self.pkg_name = 'salt-minion'
            self.srv_name = 'salt-minion'
            self.conf_dir = '/etc/salt'

        # if there are constants given in cloud config use those
        self.pkg_name = util.get_cfg_option_str(cfg, 'pkg_name',
                                                self.pkg_name)
        self.conf_dir = util.get_cfg_option_str(cfg, 'config_dir',
                                                self.conf_dir)
        self.srv_name = util.get_cfg_option_str(cfg, 'service_name',
                                                self.srv_name)


def handle(name, cfg, cloud, log, _args):
    # If there isn't a salt key in the configuration don't do anything
    if 'salt_minion' not in cfg:
        log.debug(("Skipping module named %s,"
                   " no 'salt_minion' key in configuration"), name)
        return

    s_cfg = cfg['salt_minion']
    const = SaltConstants(cfg=s_cfg)

    # Start by installing the salt package ...
    cloud.distro.install_packages(const.pkg_name)

    # Ensure we can configure files at the right dir
    util.ensure_dir(const.conf_dir)

    # ... and then update the salt configuration
    if 'conf' in s_cfg:
        # Add all sections from the conf object to minion config file
        minion_config = os.path.join(const.conf_dir, 'minion')
        minion_data = util.yaml_dumps(s_cfg.get('conf'))
        util.write_file(minion_config, minion_data)

    if 'grains' in s_cfg:
        # add grains to /etc/salt/grains
        grains_config = os.path.join(const.conf_dir, 'grains')
        grains_data = util.yaml_dumps(s_cfg.get('grains'))
        util.write_file(grains_config, grains_data)

    # ... copy the key pair if specified
    if 'public_key' in s_cfg and 'private_key' in s_cfg:
        pki_dir_default = os.path.join(const.conf_dir, "pki/minion")
        if not os.path.isdir(pki_dir_default):
            pki_dir_default = os.path.join(const.conf_dir, "pki")

        pki_dir = s_cfg.get('pki_dir', pki_dir_default)
        with util.umask(0o77):
            util.ensure_dir(pki_dir)
            pub_name = os.path.join(pki_dir, 'minion.pub')
            pem_name = os.path.join(pki_dir, 'minion.pem')
            util.write_file(pub_name, s_cfg['public_key'])
            util.write_file(pem_name, s_cfg['private_key'])

    # we need to have the salt minion service enabled in rc in order to be
    # able to start the service. this does only apply on FreeBSD servers.
    if cloud.distro.osfamily == 'freebsd':
        cloud.distro.updatercconf('salt_minion_enable', 'YES')

    # restart salt-minion. 'service' will start even if not started. if it
    # was started, it needs to be restarted for config change.
    util.subp(['service', const.srv_name, 'restart'], capture=False)

# vi: ts=4 expandtab
