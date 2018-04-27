# Copyright (C) 2017 Canonical Ltd.
#
# Author: Chad Smith <chad.smith@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import configobj
import logging
import os
import re
import signal

from cloudinit.net import (
    EphemeralIPv4Network, find_fallback_nic, get_devicelist)
from cloudinit.net.network_state import mask_and_ipv4_to_bcast_addr as bcip
from cloudinit import temp_utils
from cloudinit import util
from six import StringIO

LOG = logging.getLogger(__name__)

NETWORKD_LEASES_DIR = '/run/systemd/netif/leases'


class InvalidDHCPLeaseFileError(Exception):
    """Raised when parsing an empty or invalid dhcp.leases file.

    Current uses are DataSourceAzure and DataSourceEc2 during ephemeral
    boot to scrape metadata.
    """
    pass


class NoDHCPLeaseError(Exception):
    """Raised when unable to get a DHCP lease."""
    pass


class EphemeralDHCPv4(object):
    def __init__(self, iface=None):
        self.iface = iface
        self._ephipv4 = None

    def __enter__(self):
        try:
            leases = maybe_perform_dhcp_discovery(self.iface)
        except InvalidDHCPLeaseFileError:
            raise NoDHCPLeaseError()
        if not leases:
            raise NoDHCPLeaseError()
        lease = leases[-1]
        LOG.debug("Received dhcp lease on %s for %s/%s",
                  lease['interface'], lease['fixed-address'],
                  lease['subnet-mask'])
        nmap = {'interface': 'interface', 'ip': 'fixed-address',
                'prefix_or_mask': 'subnet-mask',
                'broadcast': 'broadcast-address',
                'router': 'routers'}
        kwargs = dict([(k, lease.get(v)) for k, v in nmap.items()])
        if not kwargs['broadcast']:
            kwargs['broadcast'] = bcip(kwargs['prefix_or_mask'], kwargs['ip'])
        ephipv4 = EphemeralIPv4Network(**kwargs)
        ephipv4.__enter__()
        self._ephipv4 = ephipv4
        return lease

    def __exit__(self, excp_type, excp_value, excp_traceback):
        if not self._ephipv4:
            return
        self._ephipv4.__exit__(excp_type, excp_value, excp_traceback)


def maybe_perform_dhcp_discovery(nic=None):
    """Perform dhcp discovery if nic valid and dhclient command exists.

    If the nic is invalid or undiscoverable or dhclient command is not found,
    skip dhcp_discovery and return an empty dict.

    @param nic: Name of the network interface we want to run dhclient on.
    @return: A list of dicts representing dhcp options for each lease obtained
        from the dhclient discovery if run, otherwise an empty list is
        returned.
    """
    if nic is None:
        nic = find_fallback_nic()
        if nic is None:
            LOG.debug('Skip dhcp_discovery: Unable to find fallback nic.')
            return []
    elif nic not in get_devicelist():
        LOG.debug(
            'Skip dhcp_discovery: nic %s not found in get_devicelist.', nic)
        return []
    dhclient_path = util.which('dhclient')
    if not dhclient_path:
        LOG.debug('Skip dhclient configuration: No dhclient command found.')
        return []
    with temp_utils.tempdir(prefix='cloud-init-dhcp-', needs_exe=True) as tdir:
        # Use /var/tmp because /run/cloud-init/tmp is mounted noexec
        return dhcp_discovery(dhclient_path, nic, tdir)


def parse_dhcp_lease_file(lease_file):
    """Parse the given dhcp lease file for the most recent lease.

    Return a list of dicts of dhcp options. Each dict contains key value pairs
    a specific lease in order from oldest to newest.

    @raises: InvalidDHCPLeaseFileError on empty of unparseable leasefile
        content.
    """
    lease_regex = re.compile(r"lease {(?P<lease>[^}]*)}\n")
    dhcp_leases = []
    lease_content = util.load_file(lease_file)
    if len(lease_content) == 0:
        raise InvalidDHCPLeaseFileError(
            'Cannot parse empty dhcp lease file {0}'.format(lease_file))
    for lease in lease_regex.findall(lease_content):
        lease_options = []
        for line in lease.split(';'):
            # Strip newlines, double-quotes and option prefix
            line = line.strip().replace('"', '').replace('option ', '')
            if not line:
                continue
            lease_options.append(line.split(' ', 1))
        dhcp_leases.append(dict(lease_options))
    if not dhcp_leases:
        raise InvalidDHCPLeaseFileError(
            'Cannot parse dhcp lease file {0}. No leases found'.format(
                lease_file))
    return dhcp_leases


def dhcp_discovery(dhclient_cmd_path, interface, cleandir):
    """Run dhclient on the interface without scripts or filesystem artifacts.

    @param dhclient_cmd_path: Full path to the dhclient used.
    @param interface: Name of the network inteface on which to dhclient.
    @param cleandir: The directory from which to run dhclient as well as store
        dhcp leases.

    @return: A list of dicts of representing the dhcp leases parsed from the
        dhcp.leases file or empty list.
    """
    LOG.debug('Performing a dhcp discovery on %s', interface)

    # XXX We copy dhclient out of /sbin/dhclient to avoid dealing with strict
    # app armor profiles which disallow running dhclient -sf <our-script-file>.
    # We want to avoid running /sbin/dhclient-script because of side-effects in
    # /etc/resolv.conf any any other vendor specific scripts in
    # /etc/dhcp/dhclient*hooks.d.
    sandbox_dhclient_cmd = os.path.join(cleandir, 'dhclient')
    util.copy(dhclient_cmd_path, sandbox_dhclient_cmd)
    pid_file = os.path.join(cleandir, 'dhclient.pid')
    lease_file = os.path.join(cleandir, 'dhcp.leases')

    # ISC dhclient needs the interface up to send initial discovery packets.
    # Generally dhclient relies on dhclient-script PREINIT action to bring the
    # link up before attempting discovery. Since we are using -sf /bin/true,
    # we need to do that "link up" ourselves first.
    util.subp(['ip', 'link', 'set', 'dev', interface, 'up'], capture=True)
    cmd = [sandbox_dhclient_cmd, '-1', '-v', '-lf', lease_file,
           '-pf', pid_file, interface, '-sf', '/bin/true']
    util.subp(cmd, capture=True)

    # dhclient doesn't write a pid file until after it forks when it gets a
    # proper lease response. Since cleandir is a temp directory that gets
    # removed, we need to wait for that pidfile creation before the
    # cleandir is removed, otherwise we get FileNotFound errors.
    missing = util.wait_for_files(
        [pid_file, lease_file], maxwait=5, naplen=0.01)
    if missing:
        LOG.warning("dhclient did not produce expected files: %s",
                    ', '.join(os.path.basename(f) for f in missing))
        return []
    pid_content = util.load_file(pid_file).strip()
    try:
        pid = int(pid_content)
    except ValueError:
        LOG.debug(
            "pid file contains non-integer content '%s'", pid_content)
    else:
        os.kill(pid, signal.SIGKILL)
    return parse_dhcp_lease_file(lease_file)


def networkd_parse_lease(content):
    """Parse a systemd lease file content as in /run/systemd/netif/leases/

    Parse this (almost) ini style file even though it says:
      # This is private data. Do not parse.

    Simply return a dictionary of key/values."""

    return dict(configobj.ConfigObj(StringIO(content), list_values=False))


def networkd_load_leases(leases_d=None):
    """Return a dictionary of dictionaries representing each lease
    found in lease_d.i

    The top level key will be the filename, which is typically the ifindex."""

    if leases_d is None:
        leases_d = NETWORKD_LEASES_DIR

    ret = {}
    if not os.path.isdir(leases_d):
        return ret
    for lfile in os.listdir(leases_d):
        ret[lfile] = networkd_parse_lease(
            util.load_file(os.path.join(leases_d, lfile)))
    return ret


def networkd_get_option_from_leases(keyname, leases_d=None):
    if leases_d is None:
        leases_d = NETWORKD_LEASES_DIR
    leases = networkd_load_leases(leases_d=leases_d)
    for _ifindex, data in sorted(leases.items()):
        if data.get(keyname):
            return data[keyname]
    return None

# vi: ts=4 expandtab
