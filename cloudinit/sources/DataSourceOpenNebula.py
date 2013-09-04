# vi: ts=4 expandtab
#
#    Copyright (C) 2012 Canonical Ltd.
#    Copyright (C) 2012 Yahoo! Inc.
#    Copyright (C) 2012-2013 CERIT Scientific Cloud
#    Copyright (C) 2012 OpenNebula.org
#
#    Author: Scott Moser <scott.moser@canonical.com>
#    Author: Joshua Harlow <harlowja@yahoo-inc.com>
#    Author: Vlastimil Holer <xholer@mail.muni.cz>
#    Author: Javier Fontan <jfontan@opennebula.org>
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
import re

from cloudinit import log as logging
from cloudinit import sources
from cloudinit import util

LOG = logging.getLogger(__name__)

DEFAULT_IID = "iid-dsopennebula"
DEFAULT_MODE = 'net'
CONTEXT_DISK_FILES = ["context.sh"]
VALID_DSMODES = ("local", "net", "disabled")


class DataSourceOpenNebula(sources.DataSource):
    def __init__(self, sys_cfg, distro, paths):
        sources.DataSource.__init__(self, sys_cfg, distro, paths)
        self.dsmode = 'local'
        self.seed = None
        self.seed_dir = os.path.join(paths.seed_dir, 'opennebula')

    def __str__(self):
        return "%s [seed=%s][dsmode=%s]" % \
            (util.obj_name(self), self.seed, self.dsmode)

    def get_data(self):
        defaults = {
            "instance-id": DEFAULT_IID,
            "dsmode": self.dsmode}

        found = None
        md = {}
        results = {}

        if os.path.isdir(self.seed_dir):
            try:
                results = read_context_disk_dir(self.seed_dir)
                found = self.seed_dir
            except NonContextDiskDir:
                util.logexc(LOG, "Failed reading context disk from %s",
                            self.seed_dir)

        # find candidate devices, try to mount them and
        # read context script if present
        if not found:
            for dev in find_candidate_devs():
                try:
                    results = util.mount_cb(dev, read_context_disk_dir)
                    found = dev
                    break
                except (NonContextDiskDir, util.MountFailedError):
                    pass

        if not found:
            return False

        md = results['metadata']
        md = util.mergedict(md, defaults)

        # check for valid user specified dsmode
        user_dsmode = results.get('dsmode', None)
        if user_dsmode not in VALID_DSMODES + (None,):
            LOG.warn("user specified invalid mode: %s", user_dsmode)
            user_dsmode = None

        # decide dsmode
        if user_dsmode:
            dsmode = user_dsmode
        elif self.ds_cfg.get('dsmode'):
            dsmode = self.ds_cfg.get('dsmode')
        else:
            dsmode = DEFAULT_MODE

        if dsmode == "disabled":
            # most likely user specified
            return False

        # apply static network configuration only in 'local' dsmode
        if ('network-interfaces' in results and self.dsmode == "local"):
            LOG.debug("Updating network interfaces from %s", self)
            self.distro.apply_network(results['network-interfaces'])

        if dsmode != self.dsmode:
            LOG.debug("%s: not claiming datasource, dsmode=%s", self, dsmode)
            return False

        self.seed = found
        self.metadata = md
        self.userdata_raw = results.get('userdata')

        return True

    def get_hostname(self, fqdn=False, resolve_ip=None):
        if resolve_ip is None:
            if self.dsmode == 'net':
                resolve_ip = True
            else:
                resolve_ip = False
        return sources.DataSource.get_hostname(self, fqdn, resolve_ip)


class DataSourceOpenNebulaNet(DataSourceOpenNebula):
    def __init__(self, sys_cfg, distro, paths):
        DataSourceOpenNebula.__init__(self, sys_cfg, distro, paths)
        self.dsmode = 'net'


class NonContextDiskDir(Exception):
    pass


class OpenNebulaNetwork(object):
    REG_DEV_MAC = re.compile(
                    r'^\d+: (eth\d+):.*?link\/ether (..:..:..:..:..:..) ?',
                    re.MULTILINE | re.DOTALL)

    def __init__(self, ip, context_sh):
        self.ip = ip
        self.context_sh = context_sh
        self.ifaces = self.get_ifaces()

    def get_ifaces(self):
        return self.REG_DEV_MAC.findall(self.ip)

    def mac2ip(self, mac):
        components = mac.split(':')[2:]
        return [str(int(c, 16)) for c in components]

    def get_ip(self, dev, components):
        var_name = dev + '_ip'
        if var_name in self.context_sh:
            return self.context_sh[var_name]
        else:
            return '.'.join(components)

    def get_mask(self, dev):
        var_name = dev + '_mask'
        if var_name in self.context_sh:
            return self.context_sh[var_name]
        else:
            return '255.255.255.0'

    def get_network(self, dev, components):
        var_name = dev + '_network'
        if var_name in self.context_sh:
            return self.context_sh[var_name]
        else:
            return '.'.join(components[:-1]) + '.0'

    def get_gateway(self, dev):
        var_name = dev + '_gateway'
        if var_name in self.context_sh:
            return self.context_sh[var_name]
        else:
            return None

    def get_dns(self, dev):
        var_name = dev + '_dns'
        if var_name in self.context_sh:
            return self.context_sh[var_name]
        else:
            return None

    def get_domain(self, dev):
        var_name = dev + '_domain'
        if var_name in self.context_sh:
            return self.context_sh[var_name]
        else:
            return None

    def gen_conf(self):
        global_dns = []
        if 'dns' in self.context_sh:
            global_dns.append(self.context_sh['dns'])

        conf = []
        conf.append('auto lo')
        conf.append('iface lo inet loopback')
        conf.append('')

        for i in self.ifaces:
            dev = i[0]
            mac = i[1]
            ip_components = self.mac2ip(mac)

            conf.append('auto ' + dev)
            conf.append('iface ' + dev + ' inet static')
            conf.append('  address ' + self.get_ip(dev, ip_components))
            conf.append('  network ' + self.get_network(dev, ip_components))
            conf.append('  netmask ' + self.get_mask(dev))

            gateway = self.get_gateway(dev)
            if gateway:
                conf.append('  gateway ' + gateway)

            domain = self.get_domain(dev)
            if domain:
                conf.append('  dns-search ' + domain)

            # add global DNS servers to all interfaces
            dns = self.get_dns(dev)
            if global_dns or dns:
                all_dns = global_dns
                if dns:
                    all_dns.append(dns)
                conf.append('  dns-nameservers ' + ' '.join(all_dns))

            conf.append('')

        return "\n".join(conf)


def find_candidate_devs():
    """
    Return a list of devices that may contain the context disk.
    """
    by_fstype = util.find_devs_with("TYPE=iso9660")
    by_fstype.sort()

    by_label = util.find_devs_with("LABEL=CDROM")
    by_label.sort()

    # combine list of items by putting by-label items first
    # followed by fstype items, but with dupes removed
    combined = (by_label + [d for d in by_fstype if d not in by_label])

    return combined


def read_context_disk_dir(source_dir):
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

    if len(found) == 0:
        raise NonContextDiskDir("%s: %s" % (source_dir, "no files found"))

    results = {'userdata': None, 'metadata': {}}
    context_sh = {}

    if "context.sh" in found:
        try:
            f = open('%s/context.sh' % (source_dir), 'r')
            text = f.read()
            f.close()

            # lame matching:
            # 1. group = key
            # 2. group = single quoted value, respect '\''
            # 3. group = old double quoted value, but doesn't end with \"
            context_reg = re.compile(
                r"^([\w_]+)=(?:'((?:[^']|'\\'')*?)'|\"(.*?[^\\])\")$",
                re.MULTILINE | re.DOTALL)

            variables = context_reg.findall(text)
            if not variables:
                raise NonContextDiskDir("No variables in context")

            for k, v1, v2 in variables:
                k = k.lower()
                if v1:
                    # take single quoted variable 'xyz'
                    # (ON>=4) and unquote '\'' -> '
                    context_sh[k] = v1.replace(r"'\''", r"'")
                elif v2:
                    # take double quoted variable "xyz"
                    # (old ON<4) and unquote \" -> "
                    context_sh[k] = v2.replace(r'\"', r'"')

        except (IOError, NonContextDiskDir) as e:
            raise NonContextDiskDir("Error reading context.sh: %s" % (e))

        results['metadata'] = context_sh
    else:
        raise NonContextDiskDir("Missing context.sh")

    # process single or multiple SSH keys
    ssh_key_var = None

    if "ssh_key" in context_sh:
        ssh_key_var = "ssh_key"
    elif "ssh_public_key" in context_sh:
        ssh_key_var = "ssh_public_key"

    if ssh_key_var:
        lines = context_sh.get(ssh_key_var).splitlines()
        results['metadata']['public-keys'] = [l for l in lines
            if len(l) and not l.startswith("#")]

    # custom hostname -- try hostname or leave cloud-init
    # itself create hostname from IP address later
    for k in ('hostname', 'public_ip', 'ip_public', 'eth0_ip'):
        if k in context_sh:
            results['metadata']['local-hostname'] = context_sh[k]
            break

    # raw user data
    if "user_data" in context_sh:
        results['userdata'] = context_sh["user_data"]
    elif "userdata" in context_sh:
        results['userdata'] = context_sh["userdata"]

    # generate static /etc/network/interfaces
    # only if there are any required context variables
    # http://opennebula.org/documentation:rel3.8:cong#network_configuration
    for k in context_sh.keys():
        if re.match(r'^eth\d+_ip$', k):
            (out, _) = util.subp(['/sbin/ip', 'link'])
            net = OpenNebulaNetwork(out, context_sh)
            results['network-interfaces'] = net.gen_conf()
            break

    return results


# Used to match classes to dependencies
datasources = [
    (DataSourceOpenNebula, (sources.DEP_FILESYSTEM, )),
    (DataSourceOpenNebulaNet, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
