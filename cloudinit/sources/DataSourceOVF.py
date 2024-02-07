# Copyright (C) 2011 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Hafliger <juerg.haefliger@hp.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Cloud-Init DataSource for OVF

This module provides a cloud-init datasource for OVF data.
"""

import base64
import logging
import os
import re
from xml.dom import minidom

from cloudinit import safeyaml, sources, subp, util

LOG = logging.getLogger(__name__)


class DataSourceOVF(sources.DataSource):
    dsname = "OVF"

    def __init__(self, sys_cfg, distro, paths):
        sources.DataSource.__init__(self, sys_cfg, distro, paths)
        self.seed = None
        self.seed_dir = os.path.join(paths.seed_dir, "ovf")
        self.environment = None
        self.cfg = {}
        self.supported_seed_starts = ("/", "file://")
        self._network_config = None

    def __str__(self):
        root = sources.DataSource.__str__(self)
        return "%s [seed=%s]" % (root, self.seed)

    def _get_data(self):
        found = []
        md = {}
        ud = ""
        vd = ""

        defaults = {
            "instance-id": "iid-dsovf",
        }

        (seedfile, contents) = get_ovf_env(self.paths.seed_dir)

        if seedfile:
            # Found a seed dir
            seed = os.path.join(self.paths.seed_dir, seedfile)
            (md, ud, cfg) = read_ovf_environment(contents)
            self.environment = contents
            found.append(seed)
        else:
            np = [
                ("com.vmware.guestInfo", transport_vmware_guestinfo),
                ("iso", transport_iso9660),
            ]
            name = None
            for name, transfunc in np:
                contents = transfunc()
                if contents:
                    break
            if contents:
                (md, ud, cfg) = read_ovf_environment(contents, True)
                self.environment = contents
                if "network-config" in md and md["network-config"]:
                    self._network_config = md["network-config"]
                found.append(name)

        # There was no OVF transports found
        if len(found) == 0:
            return False

        if "seedfrom" in md and md["seedfrom"]:
            seedfrom = md["seedfrom"]
            seedfound = False
            for proto in self.supported_seed_starts:
                if seedfrom.startswith(proto):
                    seedfound = proto
                    break
            if not seedfound:
                LOG.debug("Seed from %s not supported by %s", seedfrom, self)
                return False

            (md_seed, ud, vd) = util.read_seeded(seedfrom, timeout=None)
            LOG.debug("Using seeded cache data from %s", seedfrom)

            md = util.mergemanydict([md, md_seed])
            found.append(seedfrom)

        # Now that we have exhausted any other places merge in the defaults
        md = util.mergemanydict([md, defaults])

        self.seed = ",".join(found)
        self.metadata = md
        self.userdata_raw = ud
        self.vendordata_raw = vd
        self.cfg = cfg
        return True

    def _get_subplatform(self):
        return "ovf (%s)" % self.seed

    def get_public_ssh_keys(self):
        if "public-keys" not in self.metadata:
            return []
        pks = self.metadata["public-keys"]
        if isinstance(pks, (list)):
            return pks
        else:
            return [pks]

    # The data sources' config_obj is a cloud-config formatted
    # object that came to it from ways other than cloud-config
    # because cloud-config content would be handled elsewhere
    def get_config_obj(self):
        return self.cfg

    @property
    def network_config(self):
        return self._network_config


class DataSourceOVFNet(DataSourceOVF):
    def __init__(self, sys_cfg, distro, paths):
        DataSourceOVF.__init__(self, sys_cfg, distro, paths)
        self.seed_dir = os.path.join(paths.seed_dir, "ovf-net")
        self.supported_seed_starts = ("http://", "https://")


# This will return a dict with some content
#  meta-data, user-data, some config
def read_ovf_environment(contents, read_network=False):
    props = get_properties(contents)
    md = {}
    cfg = {}
    ud = None
    cfg_props = ["password"]
    md_props = ["seedfrom", "local-hostname", "public-keys", "instance-id"]
    network_props = ["network-config"]
    for prop, val in props.items():
        if prop == "hostname":
            prop = "local-hostname"
        if prop in md_props:
            md[prop] = val
        elif prop in cfg_props:
            cfg[prop] = val
        elif prop in network_props and read_network:
            try:
                network_config = base64.b64decode(val.encode())
                md[prop] = safeload_yaml_or_dict(network_config).get("network")
            except Exception:
                LOG.debug("Ignore network-config in wrong format")
        elif prop == "user-data":
            try:
                ud = base64.b64decode(val.encode())
            except Exception:
                ud = val.encode()
    return (md, ud, cfg)


# Returns tuple of filename (in 'dirname', and the contents of the file)
# on "not found", returns 'None' for filename and False for contents
def get_ovf_env(dirname):
    env_names = ("ovf-env.xml", "ovf_env.xml", "OVF_ENV.XML", "OVF-ENV.XML")
    for fname in env_names:
        full_fn = os.path.join(dirname, fname)
        if os.path.isfile(full_fn):
            try:
                contents = util.load_text_file(full_fn)
                return (fname, contents)
            except Exception:
                util.logexc(LOG, "Failed loading ovf file %s", full_fn)
    return (None, False)


def maybe_cdrom_device(devname):
    """Test if devname matches known list of devices which may contain iso9660
       filesystems.

    Be helpful in accepting either knames (with no leading /dev/) or full path
    names, but do not allow paths outside of /dev/, like /dev/foo/bar/xxx.
    """
    if not devname:
        return False
    elif not isinstance(devname, str):
        raise ValueError("Unexpected input for devname: %s" % devname)

    # resolve '..' and multi '/' elements
    devname = os.path.normpath(devname)

    # drop leading '/dev/'
    if devname.startswith("/dev/"):
        # partition returns tuple (before, partition, after)
        devname = devname.partition("/dev/")[-1]

    # ignore leading slash (/sr0), else fail on / in name (foo/bar/xvdc)
    if devname.startswith("/"):
        devname = devname.split("/")[-1]
    elif devname.count("/") > 0:
        return False

    # if empty string
    if not devname:
        return False

    # default_regex matches values in /lib/udev/rules.d/60-cdrom_id.rules
    # KERNEL!="sr[0-9]*|hd[a-z]|xvd*", GOTO="cdrom_end"
    default_regex = r"^(sr[0-9]+|hd[a-z]|xvd.*)"
    devname_regex = os.environ.get("CLOUD_INIT_CDROM_DEV_REGEX", default_regex)
    cdmatch = re.compile(devname_regex)

    return cdmatch.match(devname) is not None


# Transport functions are called with no arguments and return
# either None (indicating not present) or string content of an ovf-env.xml
def transport_iso9660(require_iso=True):
    # Go through mounts to see if it was already mounted
    mounts = util.mounts()
    for dev, info in mounts.items():
        fstype = info["fstype"]
        if fstype != "iso9660" and require_iso:
            continue
        if not maybe_cdrom_device(dev):
            continue
        mp = info["mountpoint"]
        (_fname, contents) = get_ovf_env(mp)
        if contents is not False:
            return contents

    if require_iso:
        mtype = "iso9660"
    else:
        mtype = None

    # generate a list of devices with mtype filesystem, filter by regex
    devs = [
        dev
        for dev in util.find_devs_with("TYPE=%s" % mtype if mtype else None)
        if maybe_cdrom_device(dev)
    ]
    for dev in devs:
        try:
            (_fname, contents) = util.mount_cb(dev, get_ovf_env, mtype=mtype)
        except util.MountFailedError:
            LOG.debug("%s not mountable as iso9660", dev)
            continue

        if contents is not False:
            return contents

    return None


def exec_vmware_rpctool(rpctool, arg):
    cmd = [rpctool, arg]
    (stdout, stderr) = subp.subp(cmd)
    return (cmd, stdout, stderr)


def exec_vmtoolsd(rpctool, arg):
    cmd = [rpctool, "--cmd", arg]
    (stdout, stderr) = subp.subp(cmd)
    return (cmd, stdout, stderr)


def transport_vmware_guestinfo():
    rpctool, rpctool_fn = None, None
    vmtoolsd = subp.which("vmtoolsd")
    vmware_rpctool = subp.which("vmware-rpctool")

    # Default to using vmware-rpctool if it is available.
    if vmware_rpctool:
        rpctool, rpctool_fn = vmware_rpctool, exec_vmware_rpctool
        LOG.debug("discovered vmware-rpctool: %s", vmware_rpctool)

    if vmtoolsd:
        # Default to using vmtoolsd if it is available and vmware-rpctool is
        # not.
        if not vmware_rpctool:
            rpctool, rpctool_fn = vmtoolsd, exec_vmtoolsd
        LOG.debug("discovered vmtoolsd: %s", vmtoolsd)

    # If neither vmware-rpctool nor vmtoolsd are available, then nothing can
    # be done.
    if not rpctool:
        LOG.debug("no rpctool discovered")
        return None

    def query_guestinfo(rpctool, rpctool_fn):
        LOG.info("query guestinfo.ovfEnv with %s", rpctool)
        try:
            cmd, stdout, _ = rpctool_fn(rpctool, "info-get guestinfo.ovfEnv")
            if stdout:
                return stdout
            LOG.debug("cmd %s exited 0 with empty stdout", cmd)
            return None
        except subp.ProcessExecutionError as error:
            if error.exit_code != 1:
                LOG.warning("%s exited with code %d", rpctool, error.exit_code)
            raise error

    try:
        # The first attempt to query guestinfo could occur via either
        # vmware-rpctool *or* vmtoolsd.
        return query_guestinfo(rpctool, rpctool_fn)
    except subp.ProcessExecutionError as error:
        # The second attempt to query guestinfo can only occur with
        # vmtoolsd.

        # If the first attempt at getting the data was with vmtoolsd, then
        # no second attempt is made.
        if vmtoolsd and rpctool == vmtoolsd:
            # The fallback failed, log the error.
            util.logexc(
                LOG, "vmtoolsd failed to get guestinfo.ovfEnv: %s", error
            )
            return None

        if not vmtoolsd:
            LOG.info("vmtoolsd fallback option not present")
            return None

        try:
            LOG.info("fallback to vmtoolsd")
            return query_guestinfo(vmtoolsd, exec_vmtoolsd)
        except subp.ProcessExecutionError as error:
            # The fallback failed, log the error.
            util.logexc(
                LOG, "vmtoolsd failed to get guestinfo.ovfEnv: %s", error
            )

    return None


def find_child(node, filter_func):
    ret = []
    if not node.hasChildNodes():
        return ret
    for child in node.childNodes:
        if filter_func(child):
            ret.append(child)
    return ret


def get_properties(contents):
    dom = minidom.parseString(contents)
    if dom.documentElement.localName != "Environment":
        raise XmlError("No Environment Node")

    if not dom.documentElement.hasChildNodes():
        raise XmlError("No Child Nodes")

    envNsURI = "http://schemas.dmtf.org/ovf/environment/1"

    # could also check here that elem.namespaceURI ==
    #   "http://schemas.dmtf.org/ovf/environment/1"
    propSections = find_child(
        dom.documentElement, lambda n: n.localName == "PropertySection"
    )

    if len(propSections) == 0:
        raise XmlError("No 'PropertySection's")

    props = {}
    propElems = find_child(
        propSections[0], (lambda n: n.localName == "Property")
    )

    for elem in propElems:
        key = elem.attributes.getNamedItemNS(envNsURI, "key").value
        val = elem.attributes.getNamedItemNS(envNsURI, "value").value
        props[key] = val

    return props


class XmlError(Exception):
    pass


# Used to match classes to dependencies
datasources = (
    (DataSourceOVF, (sources.DEP_FILESYSTEM,)),
    (DataSourceOVFNet, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
)


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)


def safeload_yaml_or_dict(data):
    """
    The meta data could be JSON or YAML. Since YAML is a strict superset of
    JSON, we will unmarshal the data as YAML. If data is None then a new
    dictionary is returned.
    """
    if not data:
        return {}
    return safeyaml.load(data)
