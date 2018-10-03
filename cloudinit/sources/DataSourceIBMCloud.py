# This file is part of cloud-init. See LICENSE file for license information.
"""Datasource for IBMCloud.

IBMCloud is also know as SoftLayer or BlueMix.
IBMCloud hypervisor is xen (2018-03-10).

There are 2 different api exposed launch methods.
 * template: This is the legacy method of launching instances.
   When booting from an image template, the system boots first into
   a "provisioning" mode.  There, host <-> guest mechanisms are utilized
   to execute code in the guest and configure it.  The configuration
   includes configuring the system network and possibly installing
   packages and other software stack.

   After the provisioning is finished, the system reboots.

 * os_code: Essentially "launch by OS Code" (Operating System Code).
   This is a more modern approach.  There is no specific "provisioning" boot.
   Instead, cloud-init does all the customization.  With or without
   user-data provided, an OpenStack ConfigDrive like disk is attached.

   Only disks with label 'config-2' and UUID '9796-932E' are considered.
   This is to avoid this datasource claiming ConfigDrive.  This does
   mean that 1 in 8^16 (~4 billion) Xen ConfigDrive systems will be
   incorrectly identified as IBMCloud.

The combination of these 2 launch methods and with or without user-data
creates 6 boot scenarios.
 A. os_code with user-data
 B. os_code without user-data
    Cloud-init is fully operational in this mode.

    There is a block device attached with label 'config-2'.
    As it differs from OpenStack's config-2, we have to differentiate.
    We do so by requiring the UUID on the filesystem to be "9796-932E".

    This disk will have the following files. Specifically note, there
    is no versioned path to the meta-data, only 'latest':
      openstack/latest/meta_data.json
      openstack/latest/network_data.json
      openstack/latest/user_data [optional]
      openstack/latest/vendor_data.json

    vendor_data.json as of 2018-04 looks like this:
      {"cloud-init":"#!/bin/bash\necho 'root:$6$<snip>' | chpasswd -e"}

    The only difference between A and B in this mode is the presence
    of user_data on the config disk.

 C. template, provisioning boot with user-data
 D. template, provisioning boot without user-data.
    With ds-identify cloud-init is fully disabled in this mode.
    Without ds-identify, cloud-init None datasource will be used.

    This is currently identified by the presence of
    /root/provisioningConfiguration.cfg . That file is placed into the
    system before it is booted.

    The difference between C and D is the presence of the METADATA disk
    as described in E below.  There is no METADATA disk attached unless
    user-data is provided.

 E. template, post-provisioning boot with user-data.
    Cloud-init is fully operational in this mode.

    This is identified by a block device with filesystem label "METADATA".
    The looks similar to a version-1 OpenStack config drive.  It will
    have the following files:

       openstack/latest/user_data
       openstack/latest/meta_data.json
       openstack/content/interfaces
       meta.js

    meta.js contains something similar to user_data.  cloud-init ignores it.
    cloud-init ignores the 'interfaces' style file here.
    In this mode, cloud-init has networking code disabled.  It relies
    on the provisioning boot to have configured networking.

 F. template, post-provisioning boot without user-data.
    With ds-identify, cloud-init will be fully disabled.
    Without ds-identify, cloud-init None datasource will be used.

    There is no information available to identify this scenario.

    The user will be able to ssh in as as root with their public keys that
    have been installed into /root/ssh/.authorized_keys
    during the provisioning stage.

TODO:
 * is uuid (/sys/hypervisor/uuid) stable for life of an instance?
   it seems it is not the same as data's uuid in the os_code case
   but is in the template case.
"""
import base64
import json
import os

from cloudinit import log as logging
from cloudinit import sources
from cloudinit.sources.helpers import openstack
from cloudinit import util

LOG = logging.getLogger(__name__)

IBM_CONFIG_UUID = "9796-932E"


class Platforms(object):
    TEMPLATE_LIVE_METADATA = "Template/Live/Metadata"
    TEMPLATE_LIVE_NODATA = "UNABLE TO BE IDENTIFIED."
    TEMPLATE_PROVISIONING_METADATA = "Template/Provisioning/Metadata"
    TEMPLATE_PROVISIONING_NODATA = "Template/Provisioning/No-Metadata"
    OS_CODE = "OS-Code/Live"


PROVISIONING = (
    Platforms.TEMPLATE_PROVISIONING_METADATA,
    Platforms.TEMPLATE_PROVISIONING_NODATA)


class DataSourceIBMCloud(sources.DataSource):

    dsname = 'IBMCloud'
    system_uuid = None

    def __init__(self, sys_cfg, distro, paths):
        super(DataSourceIBMCloud, self).__init__(sys_cfg, distro, paths)
        self.source = None
        self._network_config = None
        self.network_json = None
        self.platform = None

    def __str__(self):
        root = super(DataSourceIBMCloud, self).__str__()
        mstr = "%s [%s %s]" % (root, self.platform, self.source)
        return mstr

    def _get_data(self):
        results = read_md()
        if results is None:
            return False

        self.source = results['source']
        self.platform = results['platform']
        self.metadata = results['metadata']
        self.userdata_raw = results.get('userdata')
        self.network_json = results.get('networkdata')
        vd = results.get('vendordata')
        self.vendordata_pure = vd
        self.system_uuid = results['system-uuid']
        try:
            self.vendordata_raw = sources.convert_vendordata(vd)
        except ValueError as e:
            LOG.warning("Invalid content in vendor-data: %s", e)
            self.vendordata_raw = None

        return True

    def check_instance_id(self, sys_cfg):
        """quickly (local check only) if self.instance_id is still valid

        in Template mode, the system uuid (/sys/hypervisor/uuid) is the
        same as found in the METADATA disk.  But that is not true in OS_CODE
        mode.  So we read the system_uuid and keep that for later compare."""
        if self.system_uuid is None:
            return False
        return self.system_uuid == _read_system_uuid()

    @property
    def network_config(self):
        if self.platform != Platforms.OS_CODE:
            # If deployed from template, an agent in the provisioning
            # environment handles networking configuration. Not cloud-init.
            return {'config': 'disabled', 'version': 1}
        if self._network_config is None:
            if self.network_json is not None:
                LOG.debug("network config provided via network_json")
                self._network_config = openstack.convert_net_json(
                    self.network_json, known_macs=None)
            else:
                LOG.debug("no network configuration available.")
        return self._network_config


def _read_system_uuid():
    uuid_path = "/sys/hypervisor/uuid"
    if not os.path.isfile(uuid_path):
        return None
    return util.load_file(uuid_path).strip().lower()


def _is_xen():
    return os.path.exists("/proc/xen")


def _is_ibm_provisioning(
        prov_cfg="/root/provisioningConfiguration.cfg",
        inst_log="/root/swinstall.log",
        boot_ref="/proc/1/environ"):
    """Return boolean indicating if this boot is ibm provisioning boot."""
    if os.path.exists(prov_cfg):
        msg = "config '%s' exists." % prov_cfg
        result = True
        if os.path.exists(inst_log):
            if os.path.exists(boot_ref):
                result = (os.stat(inst_log).st_mtime >
                          os.stat(boot_ref).st_mtime)
                msg += (" log '%s' from %s boot." %
                        (inst_log, "current" if result else "previous"))
            else:
                msg += (" log '%s' existed, but no reference file '%s'." %
                        (inst_log, boot_ref))
                result = False
        else:
            msg += " log '%s' did not exist." % inst_log
    else:
        result, msg = (False, "config '%s' did not exist." % prov_cfg)
    LOG.debug("ibm_provisioning=%s: %s", result, msg)
    return result


def get_ibm_platform():
    """Return a tuple (Platform, path)

    If this is Not IBM cloud, then the return value is (None, None).
    An instance in provisioning mode is considered running on IBM cloud."""
    label_mdata = "METADATA"
    label_cfg2 = "CONFIG-2"
    not_found = (None, None)

    if not _is_xen():
        return not_found

    # fslabels contains only the first entry with a given label.
    fslabels = {}
    try:
        devs = util.blkid()
    except util.ProcessExecutionError as e:
        LOG.warning("Failed to run blkid: %s", e)
        return (None, None)

    for dev in sorted(devs.keys()):
        data = devs[dev]
        label = data.get("LABEL", "").upper()
        uuid = data.get("UUID", "").upper()
        if label not in (label_mdata, label_cfg2):
            continue
        if label in fslabels:
            LOG.warning("Duplicate fslabel '%s'. existing=%s current=%s",
                        label, fslabels[label], data)
            continue
        if label == label_cfg2 and uuid != IBM_CONFIG_UUID:
            LOG.debug("Skipping %s with LABEL=%s due to uuid != %s: %s",
                      dev, label, uuid, data)
            continue
        fslabels[label] = data

    metadata_path = fslabels.get(label_mdata, {}).get('DEVNAME')
    cfg2_path = fslabels.get(label_cfg2, {}).get('DEVNAME')

    if cfg2_path:
        return (Platforms.OS_CODE, cfg2_path)
    elif metadata_path:
        if _is_ibm_provisioning():
            return (Platforms.TEMPLATE_PROVISIONING_METADATA, metadata_path)
        else:
            return (Platforms.TEMPLATE_LIVE_METADATA, metadata_path)
    elif _is_ibm_provisioning():
        return (Platforms.TEMPLATE_PROVISIONING_NODATA, None)
    return not_found


def read_md():
    """Read data from IBM Cloud.

    @return: None if not running on IBM Cloud.
             dictionary with guaranteed fields: metadata, version
             and optional fields: userdata, vendordata, networkdata.
             Also includes the system uuid from /sys/hypervisor/uuid."""
    platform, path = get_ibm_platform()
    if platform is None:
        LOG.debug("This is not an IBMCloud platform.")
        return None
    elif platform in PROVISIONING:
        LOG.debug("Cloud-init is disabled during provisioning: %s.",
                  platform)
        return None

    ret = {'platform': platform, 'source': path,
           'system-uuid': _read_system_uuid()}

    try:
        if os.path.isdir(path):
            results = metadata_from_dir(path)
        else:
            results = util.mount_cb(path, metadata_from_dir)
    except sources.BrokenMetadata as e:
        raise RuntimeError(
            "Failed reading IBM config disk (platform=%s path=%s): %s" %
            (platform, path, e))

    ret.update(results)
    return ret


def metadata_from_dir(source_dir):
    """Walk source_dir extracting standardized metadata.

    Certain metadata keys are renamed to present a standardized set of metadata
    keys.

    This function has a lot in common with ConfigDriveReader.read_v2 but
    there are a number of inconsistencies, such key renames and as only
    presenting a 'latest' version which make it an unlikely candidate to share
    code.

    @return: Dict containing translated metadata, userdata, vendordata,
        networkdata as present.
    """

    def opath(fname):
        return os.path.join("openstack", "latest", fname)

    def load_json_bytes(blob):
        return json.loads(blob.decode('utf-8'))

    files = [
        # tuples of (results_name, path, translator)
        ('metadata_raw', opath('meta_data.json'), load_json_bytes),
        ('userdata', opath('user_data'), None),
        ('vendordata', opath('vendor_data.json'), load_json_bytes),
        ('networkdata', opath('network_data.json'), load_json_bytes),
    ]

    results = {}
    for (name, path, transl) in files:
        fpath = os.path.join(source_dir, path)
        raw = None
        try:
            raw = util.load_file(fpath, decode=False)
        except IOError as e:
            LOG.debug("Failed reading path '%s': %s", fpath, e)

        if raw is None or transl is None:
            data = raw
        else:
            try:
                data = transl(raw)
            except Exception as e:
                raise sources.BrokenMetadata(
                    "Failed decoding %s: %s" % (path, e))

        results[name] = data

    if results.get('metadata_raw') is None:
        raise sources.BrokenMetadata(
            "%s missing required file 'meta_data.json'" % source_dir)

    results['metadata'] = {}

    md_raw = results['metadata_raw']
    md = results['metadata']
    if 'random_seed' in md_raw:
        try:
            md['random_seed'] = base64.b64decode(md_raw['random_seed'])
        except (ValueError, TypeError) as e:
            raise sources.BrokenMetadata(
                "Badly formatted metadata random_seed entry: %s" % e)

    renames = (
        ('public_keys', 'public-keys'), ('hostname', 'local-hostname'),
        ('uuid', 'instance-id'))
    for mdname, newname in renames:
        if mdname in md_raw:
            md[newname] = md_raw[mdname]

    return results


# Used to match classes to dependencies
datasources = [
    (DataSourceIBMCloud, (sources.DEP_FILESYSTEM,)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Query IBM Cloud Metadata')
    args = parser.parse_args()
    data = read_md()
    print(util.json_dumps(data))

# vi: ts=4 expandtab
