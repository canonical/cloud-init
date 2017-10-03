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
from cloudinit.sources.helpers.vmware.imc.config_passwd \
    import PasswordConfigurator
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
        self.vmware_customization_supported = True
        self._network_config = None
        self._vmware_nics_to_enable = None
        self._vmware_cust_conf = None
        self._vmware_cust_found = False

    def __str__(self):
        root = sources.DataSource.__str__(self)
        return "%s [seed=%s]" % (root, self.seed)

    def get_data(self):
        found = []
        md = {}
        ud = ""
        vmwareImcConfigFilePath = None
        nicspath = None

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
            if not self.vmware_customization_supported:
                LOG.debug("Skipping the check for "
                          "VMware Customization support")
            elif not util.get_cfg_option_bool(
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
                    max_wait = get_max_wait_from_cfg(self.ds_cfg)
                    vmwareImcConfigFilePath = util.log_time(
                        logfunc=LOG.debug,
                        msg="waiting for configuration file",
                        func=wait_for_imc_cfg_file,
                        args=("cust.cfg", max_wait))

                if vmwareImcConfigFilePath:
                    LOG.debug("Found VMware Customization Config File at %s",
                              vmwareImcConfigFilePath)
                    nicspath = wait_for_imc_cfg_file(
                        filename="nics.txt", maxwait=10, naplen=5)
                else:
                    LOG.debug("Did not find VMware Customization Config File")
            else:
                LOG.debug("Customization for VMware platform is disabled.")

        if vmwareImcConfigFilePath:
            self._vmware_nics_to_enable = ""
            try:
                cf = ConfigFile(vmwareImcConfigFilePath)
                self._vmware_cust_conf = Config(cf)
                (md, ud, cfg) = read_vmware_imc(self._vmware_cust_conf)
                self._vmware_nics_to_enable = get_nics_to_enable(nicspath)
                markerid = self._vmware_cust_conf.marker_id
                markerexists = check_marker_exists(markerid)
            except Exception as e:
                LOG.debug("Error parsing the customization Config File")
                LOG.exception(e)
                set_customization_status(
                    GuestCustStateEnum.GUESTCUST_STATE_RUNNING,
                    GuestCustEventEnum.GUESTCUST_EVENT_CUSTOMIZE_FAILED)
                raise e
            finally:
                util.del_dir(os.path.dirname(vmwareImcConfigFilePath))
            try:
                LOG.debug("Preparing the Network configuration")
                self._network_config = get_network_config_from_conf(
                    self._vmware_cust_conf,
                    True,
                    True,
                    self.distro.osfamily)
            except Exception as e:
                LOG.exception(e)
                set_customization_status(
                    GuestCustStateEnum.GUESTCUST_STATE_RUNNING,
                    GuestCustEventEnum.GUESTCUST_EVENT_NETWORK_SETUP_FAILED)
                raise e

            if markerid and not markerexists:
                LOG.debug("Applying password customization")
                pwdConfigurator = PasswordConfigurator()
                adminpwd = self._vmware_cust_conf.admin_password
                try:
                    resetpwd = self._vmware_cust_conf.reset_password
                    if adminpwd or resetpwd:
                        pwdConfigurator.configure(adminpwd, resetpwd,
                                                  self.distro)
                    else:
                        LOG.debug("Changing password is not needed")
                except Exception as e:
                    LOG.debug("Error applying Password Configuration: %s", e)
                    set_customization_status(
                        GuestCustStateEnum.GUESTCUST_STATE_RUNNING,
                        GuestCustEventEnum.GUESTCUST_EVENT_CUSTOMIZE_FAILED)
                    return False
            if markerid:
                LOG.debug("Handle marker creation")
                try:
                    setup_marker_files(markerid)
                except Exception as e:
                    LOG.debug("Error creating marker files: %s", e)
                    set_customization_status(
                        GuestCustStateEnum.GUESTCUST_STATE_RUNNING,
                        GuestCustEventEnum.GUESTCUST_EVENT_CUSTOMIZE_FAILED)
                    return False

            self._vmware_cust_found = True
            found.append('vmware-tools')

            # TODO: Need to set the status to DONE only when the
            # customization is done successfully.
            enable_nics(self._vmware_nics_to_enable)
            set_customization_status(
                GuestCustStateEnum.GUESTCUST_STATE_DONE,
                GuestCustErrorEnum.GUESTCUST_ERROR_SUCCESS)

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
        if len(found) == 0:
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

    @property
    def network_config(self):
        return self._network_config


class DataSourceOVFNet(DataSourceOVF):
    def __init__(self, sys_cfg, distro, paths):
        DataSourceOVF.__init__(self, sys_cfg, distro, paths)
        self.seed_dir = os.path.join(paths.seed_dir, 'ovf-net')
        self.supported_seed_starts = ("http://", "https://", "ftp://")
        self.vmware_customization_supported = False


def get_max_wait_from_cfg(cfg):
    default_max_wait = 90
    max_wait_cfg_option = 'vmware_cust_file_max_wait'
    max_wait = default_max_wait

    if not cfg:
        return max_wait

    try:
        max_wait = int(cfg.get(max_wait_cfg_option, default_max_wait))
    except ValueError:
        LOG.warning("Failed to get '%s', using %s",
                    max_wait_cfg_option, default_max_wait)

    if max_wait <= 0:
        LOG.warning("Invalid value '%s' for '%s', using '%s' instead",
                    max_wait, max_wait_cfg_option, default_max_wait)
        max_wait = default_max_wait

    return max_wait


def wait_for_imc_cfg_file(filename, maxwait=180, naplen=5,
                          dirpath="/var/run/vmware-imc"):
    waited = 0

    while waited < maxwait:
        fileFullPath = os.path.join(dirpath, filename)
        if os.path.isfile(fileFullPath):
            return fileFullPath
        LOG.debug("Waiting for VMware Customization Config File")
        time.sleep(naplen)
        waited += naplen
    return None


def get_network_config_from_conf(config, use_system_devices=True,
                                 configure=False, osfamily=None):
    nicConfigurator = NicConfigurator(config.nics, use_system_devices)
    nics_cfg_list = nicConfigurator.generate(configure, osfamily)

    return get_network_config(nics_cfg_list,
                              config.name_servers,
                              config.dns_suffixes)


def get_network_config(nics=None, nameservers=None, search=None):
    config_list = nics

    if nameservers or search:
        config_list.append({'type': 'nameserver', 'address': nameservers,
                            'search': search})

    return {'version': 1, 'config': config_list}


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

    # Generate a unique instance-id so that re-customization will
    # happen in cloud-init
    md['instance-id'] = "iid-vmware-" + util.rand_str(strlen=8)
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


def maybe_cdrom_device(devname):
    """Test if devname matches known list of devices which may contain iso9660
       filesystems.

    Be helpful in accepting either knames (with no leading /dev/) or full path
    names, but do not allow paths outside of /dev/, like /dev/foo/bar/xxx.
    """
    if not devname:
        return False
    elif not isinstance(devname, util.string_types):
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


# Transport functions take no input and return
# a 3 tuple of content, path, filename
def transport_iso9660(require_iso=True):

    # Go through mounts to see if it was already mounted
    mounts = util.mounts()
    for (dev, info) in mounts.items():
        fstype = info['fstype']
        if fstype != "iso9660" and require_iso:
            continue
        if not maybe_cdrom_device(dev):
            continue
        mp = info['mountpoint']
        (fname, contents) = get_ovf_env(mp)
        if contents is not False:
            return (contents, dev, fname)

    if require_iso:
        mtype = "iso9660"
    else:
        mtype = None

    # generate a list of devices with mtype filesystem, filter by regex
    devs = [dev for dev in
            util.find_devs_with("TYPE=%s" % mtype if mtype else None)
            if maybe_cdrom_device(dev)]
    for dev in devs:
        try:
            (fname, contents) = util.mount_cb(dev, get_ovf_env, mtype=mtype)
        except util.MountFailedError:
            LOG.debug("%s not mountable as iso9660", dev)
            continue

        if contents is not False:
            return (contents, dev, fname)

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


# To check if marker file exists
def check_marker_exists(markerid):
    """
    Check the existence of a marker file.
    Presence of marker file determines whether a certain code path is to be
    executed. It is needed for partial guest customization in VMware.
    """
    if not markerid:
        return False
    markerfile = "/.markerfile-" + markerid
    if os.path.exists(markerfile):
        return True
    return False


# Create a marker file
def setup_marker_files(markerid):
    """
    Create a new marker file.
    Marker files are unique to a full customization workflow in VMware
    environment.
    """
    if not markerid:
        return
    markerfile = "/.markerfile-" + markerid
    util.del_file("/.markerfile-*.txt")
    open(markerfile, 'w').close()

# vi: ts=4 expandtab
