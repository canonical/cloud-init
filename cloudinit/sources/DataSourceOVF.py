# Copyright (C) 2011 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Hafliger <juerg.haefliger@hp.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

from xml.dom import minidom

import base64
import os
import re
import time

from cloudinit import log as logging
from cloudinit import sources
from cloudinit import util

from cloudinit.sources.helpers.vmware.imc.config \
    import Config
from cloudinit.sources.helpers.vmware.imc.config_file \
    import ConfigFile
from cloudinit.sources.helpers.vmware.imc.config_nic \
    import NicConfigurator
from cloudinit.sources.helpers.vmware.imc.guestcust_error \
    import GuestCustErrorEnum
from cloudinit.sources.helpers.vmware.imc.guestcust_event \
    import GuestCustEventEnum
from cloudinit.sources.helpers.vmware.imc.guestcust_state \
    import GuestCustStateEnum
from cloudinit.sources.helpers.vmware.imc.guestcust_util import (
    enable_nics,
    get_nics_to_enable,
    set_customization_status
)

LOG = logging.getLogger(__name__)


class DataSourceOVF(sources.DataSource):
    def __init__(self, sys_cfg, distro, paths):
        sources.DataSource.__init__(self, sys_cfg, distro, paths)
        self.seed = None
        self.seed_dir = os.path.join(paths.seed_dir, 'ovf')
        self.environment = None
        self.cfg = {}
        self.supported_seed_starts = ("/", "file://")

    def __str__(self):
        root = sources.DataSource.__str__(self)
        return "%s [seed=%s]" % (root, self.seed)

    def get_data(self):
        found = []
        md = {}
        ud = ""
        vmwarePlatformFound = False
        vmwareImcConfigFilePath = ''

        defaults = {
            "instance-id": "iid-dsovf",
        }

        (seedfile, contents) = get_ovf_env(self.paths.seed_dir)

        system_type = util.read_dmi_data("system-product-name")
        if system_type is None:
            LOG.debug("No system-product-name found")

        if seedfile:
            # Found a seed dir
            seed = os.path.join(self.paths.seed_dir, seedfile)
            (md, ud, cfg) = read_ovf_environment(contents)
            self.environment = contents
            found.append(seed)
        elif system_type and 'vmware' in system_type.lower():
            LOG.debug("VMware Virtualization Platform found")
            if not util.get_cfg_option_bool(
                    self.sys_cfg, "disable_vmware_customization", True):
                deployPkgPluginPath = search_file("/usr/lib/vmware-tools",
                                                  "libdeployPkgPlugin.so")
                if not deployPkgPluginPath:
                    deployPkgPluginPath = search_file("/usr/lib/open-vm-tools",
                                                      "libdeployPkgPlugin.so")
                if deployPkgPluginPath:
                    # When the VM is powered on, the "VMware Tools" daemon
                    # copies the customization specification file to
                    # /var/run/vmware-imc directory. cloud-init code needs
                    # to search for the file in that directory.
                    vmwareImcConfigFilePath = util.log_time(
                        logfunc=LOG.debug,
                        msg="waiting for configuration file",
                        func=wait_for_imc_cfg_file,
                        args=("/var/run/vmware-imc", "cust.cfg"))

                if vmwareImcConfigFilePath:
                    LOG.debug("Found VMware DeployPkg Config File at %s" %
                              vmwareImcConfigFilePath)
                else:
                    LOG.debug("Did not find VMware DeployPkg Config File Path")
            else:
                LOG.debug("Customization for VMware platform is disabled.")

        if vmwareImcConfigFilePath:
            nics = ""
            try:
                cf = ConfigFile(vmwareImcConfigFilePath)
                conf = Config(cf)
                (md, ud, cfg) = read_vmware_imc(conf)
                dirpath = os.path.dirname(vmwareImcConfigFilePath)
                nics = get_nics_to_enable(dirpath)
            except Exception as e:
                LOG.debug("Error parsing the customization Config File")
                LOG.exception(e)
                set_customization_status(
                    GuestCustStateEnum.GUESTCUST_STATE_RUNNING,
                    GuestCustEventEnum.GUESTCUST_EVENT_CUSTOMIZE_FAILED)
                enable_nics(nics)
                return False
            finally:
                util.del_dir(os.path.dirname(vmwareImcConfigFilePath))

            try:
                LOG.debug("Applying the Network customization")
                nicConfigurator = NicConfigurator(conf.nics)
                nicConfigurator.configure()
            except Exception as e:
                LOG.debug("Error applying the Network Configuration")
                LOG.exception(e)
                set_customization_status(
                    GuestCustStateEnum.GUESTCUST_STATE_RUNNING,
                    GuestCustEventEnum.GUESTCUST_EVENT_NETWORK_SETUP_FAILED)
                enable_nics(nics)
                return False

            vmwarePlatformFound = True
            set_customization_status(
                GuestCustStateEnum.GUESTCUST_STATE_DONE,
                GuestCustErrorEnum.GUESTCUST_ERROR_SUCCESS)
            enable_nics(nics)
        else:
            np = {'iso': transport_iso9660,
                  'vmware-guestd': transport_vmware_guestd, }
            name = None
            for (name, transfunc) in np.items():
                (contents, _dev, _fname) = transfunc()
                if contents:
                    break
            if contents:
                (md, ud, cfg) = read_ovf_environment(contents)
                self.environment = contents
                found.append(name)

        # There was no OVF transports found
        if len(found) == 0 and not vmwarePlatformFound:
            return False

        if 'seedfrom' in md and md['seedfrom']:
            seedfrom = md['seedfrom']
            seedfound = False
            for proto in self.supported_seed_starts:
                if seedfrom.startswith(proto):
                    seedfound = proto
                    break
            if not seedfound:
                LOG.debug("Seed from %s not supported by %s",
                          seedfrom, self)
                return False

            (md_seed, ud) = util.read_seeded(seedfrom, timeout=None)
            LOG.debug("Using seeded cache data from %s", seedfrom)

            md = util.mergemanydict([md, md_seed])
            found.append(seedfrom)

        # Now that we have exhausted any other places merge in the defaults
        md = util.mergemanydict([md, defaults])

        self.seed = ",".join(found)
        self.metadata = md
        self.userdata_raw = ud
        self.cfg = cfg
        return True

    def get_public_ssh_keys(self):
        if 'public-keys' not in self.metadata:
            return []
        pks = self.metadata['public-keys']
        if isinstance(pks, (list)):
            return pks
        else:
            return [pks]

    # The data sources' config_obj is a cloud-config formatted
    # object that came to it from ways other than cloud-config
    # because cloud-config content would be handled elsewhere
    def get_config_obj(self):
        return self.cfg


class DataSourceOVFNet(DataSourceOVF):
    def __init__(self, sys_cfg, distro, paths):
        DataSourceOVF.__init__(self, sys_cfg, distro, paths)
        self.seed_dir = os.path.join(paths.seed_dir, 'ovf-net')
        self.supported_seed_starts = ("http://", "https://", "ftp://")


def wait_for_imc_cfg_file(dirpath, filename, maxwait=180, naplen=5):
    waited = 0

    while waited < maxwait:
        fileFullPath = search_file(dirpath, filename)
        if fileFullPath:
            return fileFullPath
        time.sleep(naplen)
        waited += naplen
    return None


# This will return a dict with some content
#  meta-data, user-data, some config
def read_vmware_imc(config):
    md = {}
    cfg = {}
    ud = None
    if config.host_name:
        if config.domain_name:
            md['local-hostname'] = config.host_name + "." + config.domain_name
        else:
            md['local-hostname'] = config.host_name

    if config.timezone:
        cfg['timezone'] = config.timezone

    return (md, ud, cfg)


# This will return a dict with some content
#  meta-data, user-data, some config
def read_ovf_environment(contents):
    props = get_properties(contents)
    md = {}
    cfg = {}
    ud = None
    cfg_props = ['password']
    md_props = ['seedfrom', 'local-hostname', 'public-keys', 'instance-id']
    for (prop, val) in props.items():
        if prop == 'hostname':
            prop = "local-hostname"
        if prop in md_props:
            md[prop] = val
        elif prop in cfg_props:
            cfg[prop] = val
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
                contents = util.load_file(full_fn)
                return (fname, contents)
            except Exception:
                util.logexc(LOG, "Failed loading ovf file %s", full_fn)
    return (None, False)


# Transport functions take no input and return
# a 3 tuple of content, path, filename
def transport_iso9660(require_iso=True):

    # default_regex matches values in
    # /lib/udev/rules.d/60-cdrom_id.rules
    # KERNEL!="sr[0-9]*|hd[a-z]|xvd*", GOTO="cdrom_end"
    envname = "CLOUD_INIT_CDROM_DEV_REGEX"
    default_regex = "^(sr[0-9]+|hd[a-z]|xvd.*)"

    devname_regex = os.environ.get(envname, default_regex)
    cdmatch = re.compile(devname_regex)

    # Go through mounts to see if it was already mounted
    mounts = util.mounts()
    for (dev, info) in mounts.items():
        fstype = info['fstype']
        if fstype != "iso9660" and require_iso:
            continue
        if cdmatch.match(dev[5:]) is None:  # take off '/dev/'
            continue
        mp = info['mountpoint']
        (fname, contents) = get_ovf_env(mp)
        if contents is not False:
            return (contents, dev, fname)

    if require_iso:
        mtype = "iso9660"
    else:
        mtype = None

    devs = os.listdir("/dev/")
    devs.sort()
    for dev in devs:
        fullp = os.path.join("/dev/", dev)

        if (fullp in mounts or
                not cdmatch.match(dev) or os.path.isdir(fullp)):
            continue

        try:
            # See if we can read anything at all...??
            util.peek_file(fullp, 512)
        except IOError:
            continue

        try:
            (fname, contents) = util.mount_cb(fullp, get_ovf_env, mtype=mtype)
        except util.MountFailedError:
            LOG.debug("%s not mountable as iso9660" % fullp)
            continue

        if contents is not False:
            return (contents, fullp, fname)

    return (False, None, None)


def transport_vmware_guestd():
    # http://blogs.vmware.com/vapp/2009/07/ \
    #    selfconfiguration-and-the-ovf-environment.html
    # try:
    #     cmd = ['vmware-guestd', '--cmd', 'info-get guestinfo.ovfEnv']
    #     (out, err) = subp(cmd)
    #     return(out, 'guestinfo.ovfEnv', 'vmware-guestd')
    # except:
    #     # would need to error check here and see why this failed
    #     # to know if log/error should be raised
    #     return(False, None, None)
    return (False, None, None)


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
    propSections = find_child(dom.documentElement,
                              lambda n: n.localName == "PropertySection")

    if len(propSections) == 0:
        raise XmlError("No 'PropertySection's")

    props = {}
    propElems = find_child(propSections[0],
                           (lambda n: n.localName == "Property"))

    for elem in propElems:
        key = elem.attributes.getNamedItemNS(envNsURI, "key").value
        val = elem.attributes.getNamedItemNS(envNsURI, "value").value
        props[key] = val

    return props


def search_file(dirpath, filename):
    if not dirpath or not filename:
        return None

    for root, dirs, files in os.walk(dirpath):
        if filename in files:
            return os.path.join(root, filename)

    return None


class XmlError(Exception):
    pass


# Used to match classes to dependencies
datasources = (
    (DataSourceOVF, (sources.DEP_FILESYSTEM, )),
    (DataSourceOVFNet, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
)


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)

# vi: ts=4 expandtab
