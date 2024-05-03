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
import functools
import logging
import os
import pwd
import re
import shlex
import textwrap

from cloudinit import atomic_helper, net, sources, subp, util

LOG = logging.getLogger(__name__)

DEFAULT_IID = "iid-dsopennebula"
DEFAULT_PARSEUSER = "nobody"
CONTEXT_DISK_FILES = ["context.sh"]
EXCLUDED_VARS = (
    "EPOCHREALTIME",
    "EPOCHSECONDS",
    "RANDOM",
    "LINENO",
    "SECONDS",
    "_",
    "SRANDOM",
    "__v",
)


class DataSourceOpenNebula(sources.DataSource):

    dsname = "OpenNebula"

    def __init__(self, sys_cfg, distro, paths):
        sources.DataSource.__init__(self, sys_cfg, distro, paths)
        self.seed = None
        self.seed_dir = os.path.join(paths.seed_dir, "opennebula")
        self.network = None

    def __str__(self):
        root = sources.DataSource.__str__(self)
        return "%s [seed=%s][dsmode=%s]" % (root, self.seed, self.dsmode)

    def _get_data(self):
        defaults = {"instance-id": DEFAULT_IID}
        results = None
        seed = None

        # decide parseuser for context.sh shell reader
        parseuser = DEFAULT_PARSEUSER
        if "parseuser" in self.ds_cfg:
            parseuser = self.ds_cfg.get("parseuser")

        candidates = [self.seed_dir]
        candidates.extend(find_candidate_devs())
        for cdev in candidates:
            try:
                if os.path.isdir(self.seed_dir):
                    results = read_context_disk_dir(
                        cdev, self.distro, asuser=parseuser
                    )
                elif cdev.startswith("/dev"):
                    # util.mount_cb only handles passing a single argument
                    # through to the wrapped function, so we have to partially
                    # apply the function to pass in `distro`.  See LP: #1884979
                    partially_applied_func = functools.partial(
                        read_context_disk_dir,
                        asuser=parseuser,
                        distro=self.distro,
                    )
                    results = util.mount_cb(cdev, partially_applied_func)
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
        md = results["metadata"]
        md = util.mergemanydict([md, defaults])

        # check for valid user specified dsmode
        self.dsmode = self._determine_dsmode(
            [results.get("DSMODE"), self.ds_cfg.get("dsmode")]
        )

        if self.dsmode == sources.DSMODE_DISABLED:
            return False

        self.seed = seed
        self.network = results.get("network-interfaces")
        self.metadata = md
        self.userdata_raw = results.get("userdata")
        return True

    def _get_subplatform(self):
        """Return the subplatform metadata source details."""
        if self.seed_dir in self.seed:
            subplatform_type = "seed-dir"
        else:
            subplatform_type = "config-disk"
        return "%s (%s)" % (subplatform_type, self.seed)

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


class OpenNebulaNetwork:
    def __init__(self, context, distro, system_nics_by_mac=None):
        self.context = context
        if system_nics_by_mac is None:
            system_nics_by_mac = get_physical_nics_by_mac(distro)
        self.ifaces = collections.OrderedDict(
            [
                k
                for k in sorted(
                    system_nics_by_mac.items(),
                    key=lambda k: net.natural_sort_key(k[1]),
                )
            ]
        )

        # OpenNebula 4.14+ provide macaddr for ETHX in variable ETH_MAC.
        # context_devname provides {mac.lower():ETHX, mac2.lower():ETHX}
        self.context_devname = {}
        for k, v in context.items():
            m = re.match(r"^(.+)_MAC$", k)
            if m:
                self.context_devname[v.lower()] = m.group(1)

    def mac2ip(self, mac):
        return ".".join([str(int(c, 16)) for c in mac.split(":")[2:]])

    def get_nameservers(self, dev):
        nameservers = {}
        dns = self.get_field(dev, "dns", "").split()
        dns.extend(self.context.get("DNS", "").split())
        if dns:
            nameservers["addresses"] = dns
        search_domain = self.get_field(dev, "search_domain", "").split()
        if search_domain:
            nameservers["search"] = search_domain
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
        # OpenNebula 6.1.80 introduced new context parameter ETHx_IP6_GATEWAY
        # to replace old ETHx_GATEWAY6. Old ETHx_GATEWAY6 will be removed in
        # OpenNebula 6.4.0 (https://github.com/OpenNebula/one/issues/5536).
        return self.get_field(
            dev, "ip6_gateway", self.get_field(dev, "gateway6")
        )

    def get_mask(self, dev):
        return self.get_field(dev, "mask", "255.255.255.0")

    def get_field(self, dev, name, default=None):
        """return the field name in context for device dev.

        context stores <dev>_<NAME> (example: eth0_DOMAIN).
        an empty string for value will return default."""
        val = self.context.get(
            "_".join(
                (
                    dev,
                    name,
                )
            ).upper()
        )
        # allow empty string to return the default.
        return default if val in (None, "") else val

    def gen_conf(self):
        netconf = {}
        netconf["version"] = 2
        netconf["ethernets"] = {}

        ethernets = {}
        for mac, dev in self.ifaces.items():
            mac = mac.lower()

            # c_dev stores name in context 'ETHX' for this device.
            # dev stores the current system name.
            c_dev = self.context_devname.get(mac, dev)

            devconf = {}

            # Set MAC address
            devconf["match"] = {"macaddress": mac}

            # Set IPv4 address
            devconf["addresses"] = []
            mask = self.get_mask(c_dev)
            prefix = str(net.ipv4_mask_to_net_prefix(mask))
            devconf["addresses"].append(self.get_ip(c_dev, mac) + "/" + prefix)

            # Set IPv6 Global and ULA address
            addresses6 = self.get_ip6(c_dev)
            if addresses6:
                prefix6 = self.get_ip6_prefix(c_dev)
                devconf["addresses"].extend(
                    [i + "/" + prefix6 for i in addresses6]
                )

            # Set IPv4 default gateway
            gateway = self.get_gateway(c_dev)
            if gateway:
                devconf["gateway4"] = gateway

            # Set IPv6 default gateway
            gateway6 = self.get_gateway6(c_dev)
            if gateway6:
                devconf["gateway6"] = gateway6

            # Set DNS servers and search domains
            nameservers = self.get_nameservers(c_dev)
            if nameservers:
                devconf["nameservers"] = nameservers

            # Set MTU size
            mtu = self.get_mtu(c_dev)
            if mtu:
                devconf["mtu"] = mtu

            ethernets[dev] = devconf

        netconf["ethernets"] = ethernets
        return netconf


def find_candidate_devs():
    """
    Return a list of devices that may contain the context disk.
    """
    combined = []
    for f in ("LABEL=CONTEXT", "LABEL=CDROM", "TYPE=iso9660"):
        devs = util.find_devs_with(f)
        devs.sort()
        for d in devs:
            if d not in combined:
                combined.append(d)

    return combined


def switch_user_cmd(user):
    return ["sudo", "-u", user]


def varprinter():
    """print the shell environment variables within delimiters to be parsed"""
    return textwrap.dedent(
        """
        printf "%s\\0" _start_
        [ $0 != 'sh' ] && set -o posix
        set
        [ $0 != 'sh' ] && set +o posix
        printf "%s\\0" _start_
        """
    )


def parse_shell_config(content, asuser=None):
    """run content and return environment variables which changed

    WARNING: the special variable _start_ is used to delimit content

    a context.sh that defines this variable might break in unexpected
    ways

    compatible with posix shells such as dash and ash and any shell
    which supports `set -o posix`
    """
    if b"_start_\x00" in content.encode():
        LOG.warning(
            "User defined _start_ variable in context.sh, this may break"
            "cloud-init in unexpected ways."
        )

    # the rendered 'bcmd' does:
    #
    # setup: declare variables we use (so they show up in 'all')
    # varprinter(allvars): print all variables known at beginning
    # content: execute the provided content
    # varprinter(keylist): print all variables known after content
    #
    # output is then a newline terminated array of:
    #   [0] unwanted content before first _start_
    #   [1] key=value (for each preset variable)
    #   [2] unwanted content between second and third _start_
    #   [3] key=value (for each post set variable)
    bcmd = (
        varprinter()
        + "{\n%s\n\n:\n} > /dev/null\n" % content
        + varprinter()
        + "\n"
    )

    cmd = []
    if asuser is not None:
        cmd = switch_user_cmd(asuser)
    cmd.extend(["sh", "-e"])

    output = subp.subp(cmd, data=bcmd).stdout

    # exclude vars that change on their own or that we used
    ret = {}

    # Add to ret only things were changed and not in excluded.
    # skip all content before initial _start_\x00 pair
    sections = output.split("_start_\x00")[1:]

    # store env variables prior to content run
    # skip all content before second _start\x00 pair
    # store env variables prior to content run
    before, after = sections[0], sections[2]

    pre_env = dict(
        variable.split("=", maxsplit=1) for variable in shlex.split(before)
    )
    post_env = dict(
        variable.split("=", maxsplit=1) for variable in shlex.split(after)
    )
    for key in set(pre_env.keys()).union(set(post_env.keys())):
        if key in EXCLUDED_VARS:
            continue
        value = post_env.get(key)
        if value is not None and value != pre_env.get(key):
            ret[key] = value

    return ret


def read_context_disk_dir(source_dir, distro, asuser=None):
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
    results = {"userdata": None, "metadata": {}}

    if "context.sh" in found:
        if asuser is not None:
            try:
                pwd.getpwnam(asuser)
            except KeyError as e:
                raise BrokenContextDiskDir(
                    "configured user '{user}' does not exist".format(
                        user=asuser
                    )
                ) from e
        try:
            path = os.path.join(source_dir, "context.sh")
            content = util.load_text_file(path)
            context = parse_shell_config(content, asuser=asuser)
        except subp.ProcessExecutionError as e:
            raise BrokenContextDiskDir(
                "Error processing context.sh: %s" % (e)
            ) from e
        except IOError as e:
            raise NonContextDiskDir(
                "Error reading context.sh: %s" % (e)
            ) from e
    else:
        raise NonContextDiskDir("Missing context.sh")

    if not context:
        return results

    results["metadata"] = context

    # process single or multiple SSH keys
    ssh_key_var = None
    if "SSH_KEY" in context:
        ssh_key_var = "SSH_KEY"
    elif "SSH_PUBLIC_KEY" in context:
        ssh_key_var = "SSH_PUBLIC_KEY"

    if ssh_key_var:
        lines = context.get(ssh_key_var).splitlines()
        results["metadata"]["public-keys"] = [
            line for line in lines if len(line) and not line.startswith("#")
        ]

    # custom hostname -- try hostname or leave cloud-init
    # itself create hostname from IP address later
    for k in ("SET_HOSTNAME", "HOSTNAME", "PUBLIC_IP", "IP_PUBLIC", "ETH0_IP"):
        if k in context:
            results["metadata"]["local-hostname"] = context[k]
            break

    # raw user data
    if "USER_DATA" in context:
        results["userdata"] = context["USER_DATA"]
    elif "USERDATA" in context:
        results["userdata"] = context["USERDATA"]

    # b64decode user data if necessary (default)
    if "userdata" in results:
        encoding = context.get(
            "USERDATA_ENCODING", context.get("USER_DATA_ENCODING")
        )
        if encoding == "base64":
            try:
                results["userdata"] = atomic_helper.b64d(results["userdata"])
            except TypeError:
                LOG.warning("Failed base64 decoding of userdata")

    # generate Network Configuration v2
    # only if there are any required context variables
    # http://docs.opennebula.org/5.4/operation/references/template.html#context-section
    ipaddr_keys = [k for k in context if re.match(r"^ETH\d+_IP.*$", k)]
    if ipaddr_keys:
        onet = OpenNebulaNetwork(context, distro)
        results["network-interfaces"] = onet.gen_conf()

    return results


def get_physical_nics_by_mac(distro):
    devs = net.get_interfaces_by_mac()
    return dict(
        [(m, n) for m, n in devs.items() if distro.networking.is_physical(n)]
    )


# Legacy: Must be present in case we load an old pkl object
DataSourceOpenNebulaNet = DataSourceOpenNebula

# Used to match classes to dependencies
datasources = [
    (DataSourceOpenNebula, (sources.DEP_FILESYSTEM,)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
