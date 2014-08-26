# vi: ts=4 expandtab
#
#    Copyright (C) 2012 Canonical Ltd.
#    Copyright (C) 2012 Yahoo! Inc.
#    Copyright (C) 2012-2013 CERIT Scientific Cloud
#    Copyright (C) 2012-2013 OpenNebula.org
#    Copyright (C) 2014 Consejo Superior de Investigaciones Cientificas
#
#    Author: Scott Moser <scott.moser@canonical.com>
#    Author: Joshua Harlow <harlowja@yahoo-inc.com>
#    Author: Vlastimil Holer <xholer@mail.muni.cz>
#    Author: Javier Fontan <jfontan@opennebula.org>
#    Author: Enol Fernandez <enolfc@ifca.unican.es>
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

import base64
import os
import pwd
import re
import string

from cloudinit import log as logging
from cloudinit import sources
from cloudinit import util

LOG = logging.getLogger(__name__)

DEFAULT_IID = "iid-dsopennebula"
DEFAULT_MODE = 'net'
DEFAULT_PARSEUSER = 'nobody'
CONTEXT_DISK_FILES = ["context.sh"]
VALID_DSMODES = ("local", "net", "disabled")


class DataSourceOpenNebula(sources.DataSource):
    def __init__(self, sys_cfg, distro, paths):
        sources.DataSource.__init__(self, sys_cfg, distro, paths)
        self.dsmode = 'local'
        self.seed = None
        self.seed_dir = os.path.join(paths.seed_dir, 'opennebula')

    def __str__(self):
        root = sources.DataSource.__str__(self)
        return "%s [seed=%s][dsmode=%s]" % (root, self.seed, self.dsmode)

    def get_data(self):
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
                LOG.warn("%s was not mountable" % cdev)

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
        user_dsmode = results['metadata'].get('DSMODE', None)
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

        self.seed = seed
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


class BrokenContextDiskDir(Exception):
    pass


class OpenNebulaNetwork(object):
    REG_DEV_MAC = re.compile(
                    r'^\d+: (eth\d+):.*?link\/ether (..:..:..:..:..:..) ?',
                    re.MULTILINE | re.DOTALL)

    def __init__(self, ip, context):
        self.ip = ip
        self.context = context
        self.ifaces = self.get_ifaces()

    def get_ifaces(self):
        return self.REG_DEV_MAC.findall(self.ip)

    def mac2ip(self, mac):
        components = mac.split(':')[2:]
        return [str(int(c, 16)) for c in components]

    def get_ip(self, dev, components):
        var_name = dev.upper() + '_IP'
        if var_name in self.context:
            return self.context[var_name]
        else:
            return '.'.join(components)

    def get_mask(self, dev):
        var_name = dev.upper() + '_MASK'
        if var_name in self.context:
            return self.context[var_name]
        else:
            return '255.255.255.0'

    def get_network(self, dev, components):
        var_name = dev.upper() + '_NETWORK'
        if var_name in self.context:
            return self.context[var_name]
        else:
            return '.'.join(components[:-1]) + '.0'

    def get_gateway(self, dev):
        var_name = dev.upper() + '_GATEWAY'
        if var_name in self.context:
            return self.context[var_name]
        else:
            return None

    def get_dns(self, dev):
        var_name = dev.upper() + '_DNS'
        if var_name in self.context:
            return self.context[var_name]
        else:
            return None

    def get_domain(self, dev):
        var_name = dev.upper() + '_DOMAIN'
        if var_name in self.context:
            return self.context[var_name]
        else:
            return None

    def gen_conf(self):
        global_dns = []
        if 'DNS' in self.context:
            global_dns.append(self.context['DNS'])

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
    allvars = ["${!%s*}" % x for x in string.letters + "_"]

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
    # Add to target only things were changed and not in volitile
    for line in output.split("\x00"):
        try:
            (key, val) = line.split("=", 1)
            if target is preset:
                target[key] = val
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
            except KeyError as e:
                raise BrokenContextDiskDir("configured user '%s' "
                                           "does not exist", asuser)
        try:
            with open(os.path.join(source_dir, 'context.sh'), 'r') as f:
                content = f.read().strip()

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
            if len(l) and not l.startswith("#")]

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
                results['userdata'] = base64.b64decode(results['userdata'])
            except TypeError:
                LOG.warn("Failed base64 decoding of userdata")

    # generate static /etc/network/interfaces
    # only if there are any required context variables
    # http://opennebula.org/documentation:rel3.8:cong#network_configuration
    for k in context.keys():
        if re.match(r'^ETH\d+_IP$', k):
            (out, _) = util.subp(['/sbin/ip', 'link'])
            net = OpenNebulaNetwork(out, context)
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
