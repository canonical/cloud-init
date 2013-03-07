# vi: ts=4 expandtab
#
#    Author: Mike Milner <mike.milner@canonical.com>
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

from cloudinit import util

CA_CERT_PATH = "/usr/share/ca-certificates/"
CA_CERT_FILENAME = "cloud-init-ca-certs.crt"
CA_CERT_CONFIG = "/etc/ca-certificates.conf"
CA_CERT_SYSTEM_PATH = "/etc/ssl/certs/"
CA_CERT_FULL_PATH = os.path.join(CA_CERT_PATH, CA_CERT_FILENAME)

distros = ['ubuntu', 'debian']


def update_ca_certs():
    """
    Updates the CA certificate cache on the current machine.
    """
    util.subp(["update-ca-certificates"], capture=False)


def add_ca_certs(certs):
    """
    Adds certificates to the system. To actually apply the new certificates
    you must also call L{update_ca_certs}.

    @param certs: A list of certificate strings.
    """
    if certs:
        # First ensure they are strings...
        cert_file_contents = "\n".join([str(c) for c in certs])
        util.write_file(CA_CERT_FULL_PATH, cert_file_contents, mode=0644)

        # Append cert filename to CA_CERT_CONFIG file.
        # We have to strip the content because blank lines in the file
        # causes subsequent entries to be ignored. (LP: #1077020)
        orig = util.load_file(CA_CERT_CONFIG)
        cur_cont = '\n'.join([l for l in orig.splitlines()
                              if l != CA_CERT_FILENAME])
        out = "%s\n%s\n" % (cur_cont.rstrip(), CA_CERT_FILENAME)
        util.write_file(CA_CERT_CONFIG, out, omode="wb")


def remove_default_ca_certs():
    """
    Removes all default trusted CA certificates from the system. To actually
    apply the change you must also call L{update_ca_certs}.
    """
    util.delete_dir_contents(CA_CERT_PATH)
    util.delete_dir_contents(CA_CERT_SYSTEM_PATH)
    util.write_file(CA_CERT_CONFIG, "", mode=0644)
    debconf_sel = "ca-certificates ca-certificates/trust_new_crts select no"
    util.subp(('debconf-set-selections', '-'), debconf_sel)


def handle(name, cfg, _cloud, log, _args):
    """
    Call to handle ca-cert sections in cloud-config file.

    @param name: The module name "ca-cert" from cloud.cfg
    @param cfg: A nested dict containing the entire cloud config contents.
    @param cloud: The L{CloudInit} object in use.
    @param log: Pre-initialized Python logger object to use for logging.
    @param args: Any module arguments from cloud.cfg
    """
    # If there isn't a ca-certs section in the configuration don't do anything
    if "ca-certs" not in cfg:
        log.debug(("Skipping module named %s,"
                   " no 'ca-certs' key in configuration"), name)
        return

    ca_cert_cfg = cfg['ca-certs']

    # If there is a remove-defaults option set to true, remove the system
    # default trusted CA certs first.
    if ca_cert_cfg.get("remove-defaults", False):
        log.debug("Removing default certificates")
        remove_default_ca_certs()

    # If we are given any new trusted CA certs to add, add them.
    if "trusted" in ca_cert_cfg:
        trusted_certs = util.get_cfg_option_list(ca_cert_cfg, "trusted")
        if trusted_certs:
            log.debug("Adding %d certificates" % len(trusted_certs))
            add_ca_certs(trusted_certs)

    # Update the system with the new cert configuration.
    log.debug("Updating certificates")
    update_ca_certs()
