# vi: ts=4 expandtab
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

"""
**Summary:** helper to setup https://fedorahosted.org/spacewalk/

**Description:** This module will enable for configuring the needed
actions to setup spacewalk on redhat based systems.

It can be configured with the following option structure::

    spacewalk:
       server: spacewalk api server (required)
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
