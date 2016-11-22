# This file is part of cloud-init. See LICENSE file for license information.

"""
Spacewalk
---------
**Summary:** install and configure spacewalk

This module installs spacewalk and applies basic configuration. If the
``spacewalk`` config key is present spacewalk will be installed. The server to
connect to after installation must be provided in the ``server`` in spacewalk
configuration. A proxy to connect through and a activation key may optionally
be specified.

For more information about spacewalk see: https://fedorahosted.org/spacewalk/

**Internal name:** ``cc_spacewalk``

**Module frequency:** per instance

**Supported distros:** redhat, fedora

**Config keys**::

    spacewalk:
       server: <url>
       proxy: <proxy host>
       activation_key: <key>
"""

from cloudinit import util


distros = ['redhat', 'fedora']
required_packages = ['rhn-setup']
def_ca_cert_path = "/usr/share/rhn/RHN-ORG-TRUSTED-SSL-CERT"


def is_registered():
    # Check to see if already registered and don't bother; this is
    # apparently done by trying to sync and if that fails then we
    # assume we aren't registered; which is sorta ghetto...
    already_registered = False
    try:
        util.subp(['rhn-profile-sync', '--verbose'], capture=False)
        already_registered = True
    except util.ProcessExecutionError as e:
        if e.exit_code != 1:
            raise
    return already_registered


def do_register(server, profile_name,
                ca_cert_path=def_ca_cert_path,
                proxy=None, log=None,
                activation_key=None):
    if log is not None:
        log.info("Registering using `rhnreg_ks` profile '%s'"
                 " into server '%s'", profile_name, server)
    cmd = ['rhnreg_ks']
    cmd.extend(['--serverUrl', 'https://%s/XMLRPC' % server])
    cmd.extend(['--profilename', str(profile_name)])
    if proxy:
        cmd.extend(["--proxy", str(proxy)])
    if ca_cert_path:
        cmd.extend(['--sslCACert', str(ca_cert_path)])
    if activation_key:
        cmd.extend(['--activationkey', str(activation_key)])
    util.subp(cmd, capture=False)


def handle(name, cfg, cloud, log, _args):
    if 'spacewalk' not in cfg:
        log.debug(("Skipping module named %s,"
                   " no 'spacewalk' key in configuration"), name)
        return
    cfg = cfg['spacewalk']
    spacewalk_server = cfg.get('server')
    if spacewalk_server:
        # Need to have this installed before further things will work.
        cloud.distro.install_packages(required_packages)
        if not is_registered():
            do_register(spacewalk_server,
                        cloud.datasource.get_hostname(fqdn=True),
                        proxy=cfg.get("proxy"), log=log,
                        activation_key=cfg.get('activation_key'))
    else:
        log.debug("Skipping module named %s, 'spacewalk/server' key"
                  " was not found in configuration", name)

# vi: ts=4 expandtab
