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
import time
from io import StringIO

from cloudinit.net import (
    EphemeralIPv4Network, find_fallback_nic, get_devicelist,
    has_url_connectivity)
from cloudinit.net.network_state import mask_and_ipv4_to_bcast_addr as bcip
from cloudinit import temp_utils
from cloudinit import subp
from cloudinit import util

LOG = logging.getLogger(__name__)

NETWORKD_LEASES_DIR = '/run/systemd/netif/leases'


class InvalidDHCPLeaseFileError(Exception):
    """Raised when parsing an empty or invalid dhcp.leases file.

    Current uses are DataSourceAzure and DataSourceEc2 during ephemeral
    boot to scrape metadata.
    """


class NoDHCPLeaseError(Exception):
    """Raised when unable to get a DHCP lease."""


class EphemeralDHCPv4(object):
    def __init__(self, iface=None, connectivity_url=None, dhcp_log_func=None):
        self.iface = iface
        self._ephipv4 = None
        self.lease = None
        self.dhcp_log_func = dhcp_log_func
        self.connectivity_url = connectivity_url

    def __enter__(self):
        """Setup sandboxed dhcp context, unless connectivity_url can already be
        reached."""
        if self.connectivity_url:
            if has_url_connectivity(self.connectivity_url):
                LOG.debug(
                    'Skip ephemeral DHCP setup, instance has connectivity'
                    ' to %s', self.connectivity_url)
                return
        return self.obtain_lease()

    def __exit__(self, excp_type, excp_value, excp_traceback):
        """Teardown sandboxed dhcp context."""
        self.clean_network()

    def clean_network(self):
        """Exit _ephipv4 context to teardown of ip configuration performed."""
        if self.lease:
            self.lease = None
        if not self._ephipv4:
            return
        self._ephipv4.__exit__(None, None, None)

    def obtain_lease(self):
        """Perform dhcp discovery in a sandboxed environment if possible.

        @return: A dict representing dhcp options on the most recent lease
            obtained from the dhclient discovery if run, otherwise an error
            is raised.

        @raises: NoDHCPLeaseError if no leases could be obtained.
        """
        if self.lease:
            return self.lease
        try:
            leases = maybe_perform_dhcp_discovery(
                self.iface, self.dhcp_log_func)
        except InvalidDHCPLeaseFileError as e:
            raise NoDHCPLeaseError() from e
        if not leases:
            raise NoDHCPLeaseError()
        self.lease = leases[-1]
        LOG.debug("Received dhcp lease on %s for %s/%s",
                  self.lease['interface'], self.lease['fixed-address'],
                  self.lease['subnet-mask'])
        nmap = {'interface': 'interface', 'ip': 'fixed-address',
                'prefix_or_mask': 'subnet-mask',
                'broadcast': 'broadcast-address',
                'static_routes': [
                    'rfc3442-classless-static-routes',
                    'classless-static-routes'
                ],
                'router': 'routers'}
        kwargs = self.extract_dhcp_options_mapping(nmap)
        if not kwargs['broadcast']:
            kwargs['broadcast'] = bcip(kwargs['prefix_or_mask'], kwargs['ip'])
        if kwargs['static_routes']:
            kwargs['static_routes'] = (
                parse_static_routes(kwargs['static_routes']))
        if self.connectivity_url:
            kwargs['connectivity_url'] = self.connectivity_url
        ephipv4 = EphemeralIPv4Network(**kwargs)
        ephipv4.__enter__()
        self._ephipv4 = ephipv4
        return self.lease

    def extract_dhcp_options_mapping(self, nmap):
        result = {}
        for internal_reference, lease_option_names in nmap.items():
            if isinstance(lease_option_names, list):
                self.get_first_option_value(
                    internal_reference,
                    lease_option_names,
                    result
                )
            else:
                result[internal_reference] = self.lease.get(lease_option_names)
        return result

    def get_first_option_value(self, internal_mapping,
                               lease_option_names, result):
        for different_names in lease_option_names:
            if not result.get(internal_mapping):
                result[internal_mapping] = self.lease.get(different_names)


def maybe_perform_dhcp_discovery(nic=None, dhcp_log_func=None):
    """Perform dhcp discovery if nic valid and dhclient command exists.

    If the nic is invalid or undiscoverable or dhclient command is not found,
    skip dhcp_discovery and return an empty dict.

    @param nic: Name of the network interface we want to run dhclient on.
    @param dhcp_log_func: A callable accepting the dhclient output and error
        streams.
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
    dhclient_path = subp.which('dhclient')
    if not dhclient_path:
        LOG.debug('Skip dhclient configuration: No dhclient command found.')
        return []
    with temp_utils.tempdir(rmtree_ignore_errors=True,
                            prefix='cloud-init-dhcp-',
                            needs_exe=True) as tdir:
        # Use /var/tmp because /run/cloud-init/tmp is mounted noexec
        return dhcp_discovery(dhclient_path, nic, tdir, dhcp_log_func)


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


def dhcp_discovery(dhclient_cmd_path, interface, cleandir, dhcp_log_func=None):
    """Run dhclient on the interface without scripts or filesystem artifacts.

    @param dhclient_cmd_path: Full path to the dhclient used.
    @param interface: Name of the network inteface on which to dhclient.
    @param cleandir: The directory from which to run dhclient as well as store
        dhcp leases.
    @param dhcp_log_func: A callable accepting the dhclient output and error
        streams.

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

    # In some cases files in /var/tmp may not be executable, launching dhclient
    # from there will certainly raise 'Permission denied' error. Try launching
    # the original dhclient instead.
    if not os.access(sandbox_dhclient_cmd, os.X_OK):
        sandbox_dhclient_cmd = dhclient_cmd_path

    # ISC dhclient needs the interface up to send initial discovery packets.
    # Generally dhclient relies on dhclient-script PREINIT action to bring the
    # link up before attempting discovery. Since we are using -sf /bin/true,
    # we need to do that "link up" ourselves first.
    subp.subp(['ip', 'link', 'set', 'dev', interface, 'up'], capture=True)
    cmd = [sandbox_dhclient_cmd, '-1', '-v', '-lf', lease_file,
           '-pf', pid_file, interface, '-sf', '/bin/true']
    out, err = subp.subp(cmd, capture=True)

    # Wait for pid file and lease file to appear, and for the process
    # named by the pid file to daemonize (have pid 1 as its parent). If we
    # try to read the lease file before daemonization happens, we might try
    # to read it before the dhclient has actually written it. We also have
    # to wait until the dhclient has become a daemon so we can be sure to
    # kill the correct process, thus freeing cleandir to be deleted back
    # up the callstack.
    missing = util.wait_for_files(
        [pid_file, lease_file], maxwait=5, naplen=0.01)
    if missing:
        LOG.warning("dhclient did not produce expected files: %s",
                    ', '.join(os.path.basename(f) for f in missing))
        return []

    ppid = 'unknown'
    daemonized = False
    for _ in range(0, 1000):
        pid_content = util.load_file(pid_file).strip()
        try:
            pid = int(pid_content)
        except ValueError:
            pass
        else:
            ppid = util.get_proc_ppid(pid)
            if ppid == 1:
                LOG.debug('killing dhclient with pid=%s', pid)
                os.kill(pid, signal.SIGKILL)
                daemonized = True
                break
        time.sleep(0.01)

    if not daemonized:
        LOG.error(
            'dhclient(pid=%s, parentpid=%s) failed to daemonize after %s '
            'seconds', pid_content, ppid, 0.01 * 1000
        )
    if dhcp_log_func is not None:
        dhcp_log_func(out, err)
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


def parse_static_routes(rfc3442):
    """ parse rfc3442 format and return a list containing tuple of strings.

    The tuple is composed of the network_address (including net length) and
    gateway for a parsed static route.  It can parse two formats of rfc3442,
    one from dhcpcd and one from dhclient (isc).

    @param rfc3442: string in rfc3442 format (isc or dhcpd)
    @returns: list of tuple(str, str) for all valid parsed routes until the
              first parsing error.

    E.g.
    sr=parse_static_routes("32,169,254,169,254,130,56,248,255,0,130,56,240,1")
    sr=[
        ("169.254.169.254/32", "130.56.248.255"), ("0.0.0.0/0", "130.56.240.1")
    ]

    sr2 = parse_static_routes("24.191.168.128 192.168.128.1,0 192.168.128.1")
    sr2 = [
        ("191.168.128.0/24", "192.168.128.1"), ("0.0.0.0/0", "192.168.128.1")
    ]

    Python version of isc-dhclient's hooks:
       /etc/dhcp/dhclient-exit-hooks.d/rfc3442-classless-routes
    """
    # raw strings from dhcp lease may end in semi-colon
    rfc3442 = rfc3442.rstrip(";")
    tokens = [tok for tok in re.split(r"[, .]", rfc3442) if tok]
    static_routes = []

    def _trunc_error(cidr, required, remain):
        msg = ("RFC3442 string malformed.  Current route has CIDR of %s "
               "and requires %s significant octets, but only %s remain. "
               "Verify DHCP rfc3442-classless-static-routes value: %s"
               % (cidr, required, remain, rfc3442))
        LOG.error(msg)

    current_idx = 0
    for idx, tok in enumerate(tokens):
        if idx < current_idx:
            continue
        net_length = int(tok)
        if net_length in range(25, 33):
            req_toks = 9
            if len(tokens[idx:]) < req_toks:
                _trunc_error(net_length, req_toks, len(tokens[idx:]))
                return static_routes
            net_address = ".".join(tokens[idx+1:idx+5])
            gateway = ".".join(tokens[idx+5:idx+req_toks])
            current_idx = idx + req_toks
        elif net_length in range(17, 25):
            req_toks = 8
            if len(tokens[idx:]) < req_toks:
                _trunc_error(net_length, req_toks, len(tokens[idx:]))
                return static_routes
            net_address = ".".join(tokens[idx+1:idx+4] + ["0"])
            gateway = ".".join(tokens[idx+4:idx+req_toks])
            current_idx = idx + req_toks
        elif net_length in range(9, 17):
            req_toks = 7
            if len(tokens[idx:]) < req_toks:
                _trunc_error(net_length, req_toks, len(tokens[idx:]))
                return static_routes
            net_address = ".".join(tokens[idx+1:idx+3] + ["0", "0"])
            gateway = ".".join(tokens[idx+3:idx+req_toks])
            current_idx = idx + req_toks
        elif net_length in range(1, 9):
            req_toks = 6
            if len(tokens[idx:]) < req_toks:
                _trunc_error(net_length, req_toks, len(tokens[idx:]))
                return static_routes
            net_address = ".".join(tokens[idx+1:idx+2] + ["0", "0", "0"])
            gateway = ".".join(tokens[idx+2:idx+req_toks])
            current_idx = idx + req_toks
        elif net_length == 0:
            req_toks = 5
            if len(tokens[idx:]) < req_toks:
                _trunc_error(net_length, req_toks, len(tokens[idx:]))
                return static_routes
            net_address = "0.0.0.0"
            gateway = ".".join(tokens[idx+1:idx+req_toks])
            current_idx = idx + req_toks
        else:
            LOG.error('Parsed invalid net length "%s".  Verify DHCP '
                      'rfc3442-classless-static-routes value.', net_length)
            return static_routes

        static_routes.append(("%s/%s" % (net_address, net_length), gateway))

    return static_routes

# vi: ts=4 expandtab
