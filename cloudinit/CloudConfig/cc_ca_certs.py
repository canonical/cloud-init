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
import pwd
import socket
from subprocess import check_call
import json
import StringIO
import ConfigParser
import cloudinit.CloudConfig as cc
import cloudinit.util as util

CERT_FILENAME = "/usr/share/ca-certificates/cloud-init-provided.crt"

def write_file(filename, contents, owner, group, mode):
    """
    Write a file to disk with specified owner, group, and mode. If the file
    exists already it will be overwritten.

    @param filename: Full path to the new file.
    @param contents: The contents of the newly created file.
    @param owner: The username who should own the file.
    @param group: The group for the new file.
    @param mode: The octal mode (as string) for the new file.
    """
    raise NotImplementedError()

def update_ca_certs():
    """
    Updates the CA certificate cache on the current machine.
    """
    check_call(["dpkg-reconfigure", "ca-certificates"])
    check_call(["update-ca-certificates"])

def handle(name, cfg, cloud, log, args):
    """
    Call to handle ca-cert sections in cloud-config file.

    @param name: The module name "ca-cert" from cloud.cfg
    @param cfg: A nested dict containing the entire cloud config contents.
    @param cloud: The L{CloudInit} object in use
    @param log: Pre-initialized Python logger object to use for logging
    @param args: Any module arguments from cloud.cfg
    """
    # If there isn't a ca-certs section in the configuration don't do anything
    if not cfg.has_key('ca-certs'):
        return
    ca_cert_cfg = cfg['ca-certs']

    # set the validation key based on the presence of either 'validation_key'
    # or 'validation_cert'. In the case where both exist, 'validation_key'
    # takes precedence
    if ca_cert_cfg.has_key('trusted'):
        trusted_certs = util.get_cfg_option_list_or_str(ca_cert_cfg, 'trusted')
        if trusted_certs:
            cert_file_contents = "\n".join(trusted_certs)
            write_file(CERT_FILENAME, cert_file_contents, "root", "root", "644")

    update_ca_certs()
