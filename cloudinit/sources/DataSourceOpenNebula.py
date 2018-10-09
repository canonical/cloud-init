# Copyright (C) 2012 Canonical Ltd.
# Copyright (C) 2012 Yahoo! Inc.
# Copyright (C) 2012-2013 CERIT Scientific Cloud
# Copyright (C) 2012-2013 OpenNebula.org
# Copyright (C) 2014 Consejo Superior de Investigaciones Cientificas
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
# Author: Vlastimil Holer <xholer@mail.muni.cz>
# Author: Javier Fontan <jfontan@opennebula.org>
# Author: Enol Fernandez <enolfc@ifca.unican.es>
#
# This file is part of cloud-init. See LICENSE file for license information.

import collections
import os
import pwd
import re
import string

from cloudinit import log as logging
from cloudinit import net
from cloudinit import sources
from cloudinit import util


LOG = logging.getLogger(__name__)

DEFAULT_IID = "iid-dsopennebula"
DEFAULT_PARSEUSER = 'nobody'
CONTEXT_DISK_FILES = ["context.sh"]


class DataSourceOpenNebula(sources.DataSource):

    dsname = "OpenNebula"

    def __init__(self, sys_cfg, distro, paths):
        sources.DataSource.__init__(self, sys_cfg, distro, paths)
        self.seed = None
        self.seed_dir = os.path.join(paths.seed_dir, 'opennebula')

    def __str__(self):
        root = sources.DataSource.__str__(self)
        return "%s [seed=%s][dsmode=%s]" % (root, self.seed, self.dsmode)

    def _get_data(self):
        defaults = {"instance-id": DEFAULT_IID}
        results = None
        seed = None

        # decide parseuser for context.sh shell reader
        parseuser = DEFAULT_PARSEUSER
        if 'parseuser' in self.ds_cfg:
            parseuser = self.ds_cfg.get('parseuser')

        candidates = [self.seed_dir]
        candidates.extend(find_candidate_devs())
        for cdev in candidates:
            try:
                if os.path.isdir(self.seed_dir):
                    results = read_context_disk_dir(cdev, asuser=parseuser)
                elif cdev.startswith("/dev"):
                    results = util.mount_cb(cdev, read_context_disk_dir,
                                            data=parseuser)
            except NonContextDiskDir:
                continue
            except BrokenContextDiskDir as exc:
                raise exc
            except util.MountFailedError:
                LOG.warning("%s was not mountable", cdev)

            if results:
                seed = cdev
                LOG.debug("found datasource in %s", cdev)
                break

        if not seed:
            return False

        # merge fetched metadata with datasource defaults
        md = results['metadata']
        md = util.mergemanydict([md, defaults])

        # check for valid user specified dsmode
        self.dsmode = self._determine_dsmode(
            [results.get('DSMODE'), self.ds_cfg.get('dsmode')])

        if self.dsmode == sources.DSMODE_DISABLED:
            return False

        self.seed = seed
        self.network = results.get('network-interfaces')
        self.metadata = md
        self.userdata_raw = results.get('userdata')
        return True

    def _get_subplatform(self):
        """Return the subplatform metadata source details."""
        if self.seed_dir in self.seed:
            subplatform_type = 'seed-dir'
        else:
            subplatform_type = 'config-disk'
        return '%s (%s)' % (subplatform_type, self.seed)

    @property
    def network_config(self):
        if self.network is not None:
            return self.network
        else:
            return None

    def get_hostname(self, fqdn=False, resolve_ip=False, metadata_only=False):
        if resolve_ip is None:
            if self.dsmode == sources.DSMODE_NETWORK:
                resolve_ip = True
            else:
                resolve_ip = False
        return sources.DataSource.get_hostname(self, fqdn, resolve_ip)


class NonContextDiskDir(Exception):
    pass


class BrokenContextDiskDir(Exception):
    pass


class OpenNebulaNetwork(object):
    def __init__(self, context, system_nics_by_mac=None):
        self.context = context
        if system_nics_by_mac is None:
            system_nics_by_mac = get_physical_nics_by_mac()
        self.ifaces = collections.OrderedDict(
            [k for k in sorted(system_nics_by_mac.items(),
                               key=lambda k: net.natural_sort_key(k[1]))])

        # OpenNebula 4.14+ provide macaddr for ETHX in variable ETH_MAC.
        # context_devname provides {mac.lower():ETHX, mac2.lower():ETHX}
        self.context_devname = {}
        for k, v in context.items():
            m = re.match(r'^(.+)_MAC$', k)
            if m:
                self.context_devname[v.lower()] = m.group(1)

    def mac2ip(self, mac):
        return '.'.join([str(int(c, 16)) for c in mac.split(':')[2:]])

    def mac2network(self, mac):
        return self.mac2ip(mac).rpartition(".")[0] + ".0"

    def get_nameservers(self, dev):
        nameservers = {}
        dns = self.get_field(dev, "dns", "").split()
        dns.extend(self.context.get('DNS', "").split())
        if dns:
            nameservers['addresses'] = dns
        search_domain = self.get_field(dev, "search_domain", "").split()
        if search_domain:
            nameservers['search'] = search_domain
        return nameservers

    def get_mtu(self, dev):
        return self.get_field(dev, "mtu")

    def get_ip(self, dev, mac):
        return self.get_field(dev, "ip", self.mac2ip(mac))

    def get_ip6(self, dev):
        addresses6 = []
        ip6 = self.get_field(dev, "ip6")
        if ip6:
            addresses6.append(ip6)
        ip6_ula = self.get_field(dev, "ip6_ula")
        if ip6_ula:
            addresses6.append(ip6_ula)
        return addresses6

    def get_ip6_prefix(self, dev):
        return self.get_field(dev, "ip6_prefix_length", "64")

    def get_gateway(self, dev):
        return self.get_field(dev, "gateway")

    def get_gateway6(self, dev):
        return self.get_field(dev, "gateway6")

    def get_mask(self, dev):
        return self.get_field(dev, "mask", "255.255.255.0")

    def get_network(self, dev, mac):
        return self.get_field(dev, "network", self.mac2network(mac))

    def get_field(self, dev, name, default=None):
        """return the field name in context for device dev.

        context stores <dev>_<NAME> (example: eth0_DOMAIN).
        an empty string for value will return default."""
        val = self.context.get('_'.join((dev, name,)).upper())
        # allow empty string to return the default.
        return default if val in (None, "") else val

    def gen_conf(self):
        netconf = {}
        netconf['version'] = 2
        netconf['ethernets'] = {}

        ethernets = {}
        for mac, dev in self.ifaces.items():
            mac = mac.lower()

            # c_dev stores name in context 'ETHX' for this device.
            # dev stores the current system name.
            c_dev = self.context_devname.get(mac, dev)

            devconf = {}

            # Set MAC address
            devconf['match'] = {'macaddress': mac}

            # Set IPv4 address
            devconf['addresses'] = []
            mask = self.get_mask(c_dev)
            prefix = str(net.mask_to_net_prefix(mask))
            devconf['addresses'].append(
                self.get_ip(c_dev, mac) + '/' + prefix)

            # Set IPv6 Global and ULA address
            addresses6 = self.get_ip6(c_dev)
            if addresses6:
                prefix6 = self.get_ip6_prefix(c_dev)
                devconf['addresses'].extend(
                    [i + '/' + prefix6 for i in addresses6])

            # Set IPv4 default gateway
            gateway = self.get_gateway(c_dev)
            if gateway:
                devconf['gateway4'] = gateway

            # Set IPv6 default gateway
            gateway6 = self.get_gateway6(c_dev)
            if gateway6:
                devconf['gateway6'] = gateway6

            # Set DNS servers and search domains
            nameservers = self.get_nameservers(c_dev)
            if nameservers:
                devconf['nameservers'] = nameservers

            # Set MTU size
            mtu = self.get_mtu(c_dev)
            if mtu:
                devconf['mtu'] = mtu

            ethernets[dev] = devconf

        netconf['ethernets'] = ethernets
        return(netconf)


def find_candidate_devs():
    """
    Return a list of devices that may contain the context disk.
    """
    combined = []
    for f in ('LABEL=CONTEXT', 'LABEL=CDROM', 'TYPE=iso9660'):
        devs = util.find_devs_with(f)
        devs.sort()
        for d in devs:
            if d not in combined:
                combined.append(d)

    return combined


def switch_user_cmd(user):
    return ['sudo', '-u', user]


def parse_shell_config(content, keylist=None, bash=None, asuser=None,
                       switch_user_cb=None):

    if isinstance(bash, str):
        bash = [bash]
    elif bash is None:
        bash = ['bash', '-e']

    if switch_user_cb is None:
        switch_user_cb = switch_user_cmd

    # allvars expands to all existing variables by using '${!x*}' notation
    # where x is lower or upper case letters or '_'
    allvars = ["${!%s*}" % x for x in string.ascii_letters + "_"]

    keylist_in = keylist
    if keylist is None:
        keylist = allvars
        keylist_in = []

    setup = '\n'.join(('__v="";', '',))

    def varprinter(vlist):
        # output '\0'.join(['_start_', key=value NULL for vars in vlist]
        return '\n'.join((
            'printf "%s\\0" _start_',
            'for __v in %s; do' % ' '.join(vlist),
            '   printf "%s=%s\\0" "$__v" "${!__v}";',
            'done',
            ''
        ))

    # the rendered 'bcmd' is bash syntax that does
    # setup: declare variables we use (so they show up in 'all')
    # varprinter(allvars): print all variables known at beginning
    # content: execute the provided content
    # varprinter(keylist): print all variables known after content
    #
    # output is then a null terminated array of:
    #   literal '_start_'
    #   key=value (for each preset variable)
    #   literal '_start_'
    #   key=value (for each post set variable)
    bcmd = ('unset IFS\n' +
            setup +
            varprinter(allvars) +
            '{\n%s\n\n:\n} > /dev/null\n' % content +
            'unset IFS\n' +
            varprinter(keylist) + "\n")

    cmd = []
    if asuser is not None:
        cmd = switch_user_cb(asuser)

    cmd.extend(bash)

    (output, _error) = util.subp(cmd, data=bcmd)

    # exclude vars in bash that change on their own or that we used
    excluded = ("RANDOM", "LINENO", "SECONDS", "_", "__v")
    preset = {}
    ret = {}
    target = None
    output = output[0:-1]  # remove trailing null

    # go through output.  First _start_ is for 'preset', second for 'target'.
    # Add to ret only things were changed and not in excluded.
    for line in output.split("\x00"):
        try:
            (key, val) = line.split("=", 1)
            if target is preset:
                preset[key] = val
            elif (key not in excluded and
                  (key in keylist_in or preset.get(key) != val)):
                ret[key] = val
        except ValueError:
            if line != "_start_":
                raise
            if target is None:
                target = preset
            elif target is preset:
                target = ret

    return ret


def read_context_disk_dir(source_dir, asuser=None):
    """
    read_context_disk_dir(source_dir):
    read source_dir and return a tuple with metadata dict and user-data
    string populated.  If not a valid dir, raise a NonContextDiskDir
    """
    found = {}
    for af in CONTEXT_DISK_FILES:
        fn = os.path.join(source_dir, af)
        if os.path.isfile(fn):
            found[af] = fn

    if not found:
        raise NonContextDiskDir("%s: %s" % (source_dir, "no files found"))

    context = {}
    results = {'userdata': None, 'metadata': {}}

    if "context.sh" in found:
        if asuser is not None:
            try:
                pwd.getpwnam(asuser)
            except KeyError:
                raise BrokenContextDiskDir(
                    "configured user '{user}' does not exist".format(
                        user=asuser))
        try:
            path = os.path.join(source_dir, 'context.sh')
            content = util.load_file(path)
            context = parse_shell_config(content, asuser=asuser)
        except util.ProcessExecutionError as e:
            raise BrokenContextDiskDir("Error processing context.sh: %s" % (e))
        except IOError as e:
            raise NonContextDiskDir("Error reading context.sh: %s" % (e))
    else:
        raise NonContextDiskDir("Missing context.sh")

    if not context:
        return results

    results['metadata'] = context

    # process single or multiple SSH keys
    ssh_key_var = None
    if "SSH_KEY" in context:
        ssh_key_var = "SSH_KEY"
    elif "SSH_PUBLIC_KEY" in context:
        ssh_key_var = "SSH_PUBLIC_KEY"

    if ssh_key_var:
        lines = context.get(ssh_key_var).splitlines()
        results['metadata']['public-keys'] = [l for l in lines
                                              if len(l) and not
                                              l.startswith("#")]

    # custom hostname -- try hostname or leave cloud-init
    # itself create hostname from IP address later
    for k in ('HOSTNAME', 'PUBLIC_IP', 'IP_PUBLIC', 'ETH0_IP'):
        if k in context:
            results['metadata']['local-hostname'] = context[k]
            break

    # raw user data
    if "USER_DATA" in context:
        results['userdata'] = context["USER_DATA"]
    elif "USERDATA" in context:
        results['userdata'] = context["USERDATA"]

    # b64decode user data if necessary (default)
    if 'userdata' in results:
        encoding = context.get('USERDATA_ENCODING',
                               context.get('USER_DATA_ENCODING'))
        if encoding == "base64":
            try:
                results['userdata'] = util.b64d(results['userdata'])
            except TypeError:
                LOG.warning("Failed base64 decoding of userdata")

    # generate Network Configuration v2
    # only if there are any required context variables
    # http://docs.opennebula.org/5.4/operation/references/template.html#context-section
    ipaddr_keys = [k for k in context if re.match(r'^ETH\d+_IP.*$', k)]
    if ipaddr_keys:
        onet = OpenNebulaNetwork(context)
        results['network-interfaces'] = onet.gen_conf()

    return results


def get_physical_nics_by_mac():
    devs = net.get_interfaces_by_mac()
    return dict([(m, n) for m, n in devs.items() if net.is_physical(n)])


# Legacy: Must be present in case we load an old pkl object
DataSourceOpenNebulaNet = DataSourceOpenNebula

# Used to match classes to dependencies
datasources = [
    (DataSourceOpenNebula, (sources.DEP_FILESYSTEM, )),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)

# vi: ts=4 expandtab
