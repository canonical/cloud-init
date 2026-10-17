# Copyright (C) 2012 Canonical Ltd.
# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import fnmatch
import logging
import os

from cloudinit import lifecycle, sources, subp, util
from cloudinit.event import EventScope, EventType
from cloudinit.net import eni
from cloudinit.sources.DataSourceIBMCloud import get_ibm_platform
from cloudinit.sources.helpers import openstack

LOG = logging.getLogger(__name__)

# Various defaults/constants...
DEFAULT_IID = "iid-dsconfigdrive"
DEFAULT_METADATA = {
    "instance-id": DEFAULT_IID,
}
FS_TYPES = ("vfat", "iso9660")
LABEL_TYPES = ("config-2", "CONFIG-2")
POSSIBLE_MOUNTS = ("sr", "cd")
OPTICAL_DEVICES = tuple(
    ("/dev/%s%s" % (z, i) for z in POSSIBLE_MOUNTS for i in range(2))
)


class DataSourceConfigDrive(openstack.SourceMixin, sources.DataSource):

    dsname = "ConfigDrive"

    supported_update_events = {
        EventScope.NETWORK: {
            EventType.BOOT_NEW_INSTANCE,
            EventType.BOOT,
            EventType.BOOT_LEGACY,
            EventType.HOTPLUG,
        }
    }

    def __init__(self, sys_cfg, distro, paths):
        super(DataSourceConfigDrive, self).__init__(sys_cfg, distro, paths)
        self.source = None
        self.seed_dir = os.path.join(paths.seed_dir, "config_drive")
        self.version = None
        self.ec2_metadata = None
        self._network_config = None
        self.network_json = sources.UNSET
        self.network_eni = None
        self.known_macs = None
        self.files = {}

    def __str__(self):
        root = sources.DataSource.__str__(self)
        mstr = "%s [%s,ver=%s]" % (root, self.dsmode, self.version)
        mstr += "[source=%s]" % (self.source)
        return mstr

    def _get_data(self):
        found = None
        md = {}
        results = {}
        for sdir in (self.seed_dir, "/config-drive"):
            if not os.path.isdir(sdir):
                continue
            try:
                results = read_config_drive(sdir)
                found = sdir
                break
            except openstack.NonReadable:
                util.logexc(LOG, "Failed reading config drive from %s", sdir)

        if not found:
            dslist = self.sys_cfg.get("datasource_list")
            for dev in find_candidate_devs(dslist=dslist):
                mtype = None
                if util.is_BSD():
                    if dev.startswith("/dev/cd"):
                        mtype = "cd9660"
                try:
                    results = util.mount_cb(
                        dev, read_config_drive, mtype=mtype
                    )
                    found = dev
                except openstack.NonReadable:
                    pass
                except util.MountFailedError:
                    pass
                except openstack.BrokenMetadata:
                    util.logexc(LOG, "Broken config drive: %s", dev)
                if found:
                    break
        if not found:
            return False

        md = results.get("metadata", {})
        md = util.mergemanydict([md, DEFAULT_METADATA])

        self.dsmode = self._determine_dsmode(
            [
                results.get("dsmode"),
                self.ds_cfg.get("dsmode"),
                sources.DSMODE_PASS if results["version"] == 1 else None,
            ]
        )

        if self.dsmode == sources.DSMODE_DISABLED:
            return False

        prev_iid = get_previous_iid(self.paths)
        cur_iid = md["instance-id"]
        if prev_iid != cur_iid:
            # better would be to handle this centrally, allowing
            # the datasource to do something on new instance id
            # note, networking is only rendered here if dsmode is DSMODE_PASS
            # which means "DISABLED, but render files and networking"
            files_policy = extract_files_policy(self.ds_cfg)
            on_first_boot(
                results,
                distro=self.distro,
                network=self.dsmode == sources.DSMODE_PASS,
                files_policy=files_policy,
            )

        # This is legacy and sneaky.  If dsmode is 'pass' then do not claim
        # the datasource was used, even though we did run on_first_boot above.
        if self.dsmode == sources.DSMODE_PASS:
            LOG.debug(
                "%s: not claiming datasource, dsmode=%s", self, self.dsmode
            )
            return False

        self.source = found
        self.metadata = md
        self.ec2_metadata = results.get("ec2-metadata")
        self.userdata_raw = results.get("userdata")
        self.version = results["version"]
        self.files.update(results.get("files", {}))

        vd = results.get("vendordata")
        try:
            self.vendordata_raw = sources.convert_vendordata(vd)
        except ValueError as e:
            LOG.warning("Invalid content in vendor-data: %s", e)
            self.vendordata_raw = None

        vd2 = results.get("vendordata2")
        try:
            self.vendordata2_raw = sources.convert_vendordata(vd2)
        except ValueError as e:
            LOG.warning("Invalid content in vendor-data2: %s", e)
            self.vendordata2_raw = None

        # network_config is an /etc/network/interfaces formatted file and is
        # obsolete compared to networkdata (from network_data.json) but both
        # might be present.
        self.network_eni = results.get("network_config")
        self.network_json = results.get("networkdata")
        return True

    def check_instance_id(self, sys_cfg):
        # quickly (local check only) if self.instance_id is still valid
        return sources.instance_id_matches_system_uuid(self.get_instance_id())

    @property
    def network_config(self):
        if self._network_config is None:
            if self.network_json not in (None, sources.UNSET):
                LOG.debug("network config provided via network_json")
                self._network_config = openstack.convert_net_json(
                    self.network_json, known_macs=self.known_macs
                )
            elif self.network_eni is not None:
                self._network_config = eni.convert_eni_data(self.network_eni)
                LOG.debug("network config provided via converted eni data")
                lifecycle.deprecate(
                    deprecated="Eni network configuration in ConfigDrive",
                    deprecated_version="24.3",
                    extra_message=(
                        "You can use openstack's network "
                        "configuration format instead"
                    ),
                )
            else:
                LOG.debug("no network configuration available")
        return self._network_config

    @property
    def platform(self):
        return "openstack"

    def _get_subplatform(self):
        """Return the subplatform metadata source details."""
        if self.source.startswith("/dev"):
            subplatform_type = "config-disk"
        else:
            subplatform_type = "seed-dir"
        return "%s (%s)" % (subplatform_type, self.source)


def read_config_drive(source_dir):
    reader = openstack.ConfigDriveReader(source_dir)
    finders = [
        (reader.read_v2, [], {}),
        (reader.read_v1, [], {}),
    ]
    excps = []
    for functor, args, kwargs in finders:
        try:
            return functor(*args, **kwargs)
        except openstack.NonReadable as e:
            excps.append(e)
    raise excps[-1]


def get_previous_iid(paths):
    # interestingly, for this purpose the "previous" instance-id is the current
    # instance-id.  cloud-init hasn't moved them over yet as this datasource
    # hasn't declared itself found.
    fname = os.path.join(paths.get_cpath("data"), "instance-id")
    try:
        return util.load_text_file(fname).rstrip("\n")
    except IOError:
        return None


def extract_files_policy(cfg):
    """Extract and normalize injected files policy from datasource
    configuration.

    Supports nested configuration:
      datasource:
        ConfigDrive:
          files:
            enabled: bool (default True)
            allowlist: list of glob patterns (default None -> all allowed)
            denylist: list of glob patterns (default [])
            overwrite: bool (default True)
            mode: int or octal str (default 0o660)

    As well as aliases and flat options:
      files: false / true
      files: { whitelist: [...], blacklist: [...] }
      files_allowlist: [...]
      files_denylist: [...]
      files_overwrite: bool
    """
    default_policy = {
        "enabled": True,
        "allowlist": None,
        "denylist": [],
        "overwrite": True,
        "mode": 0o660,
    }

    if cfg is None:
        return default_policy

    if isinstance(cfg, bool):
        default_policy["enabled"] = cfg
        return default_policy

    if not isinstance(cfg, dict):
        if util.is_false(cfg):
            default_policy["enabled"] = False
        return default_policy

    policy = dict(default_policy)

    files_cfg = cfg.get("files")
    if files_cfg is None and any(
        k in cfg
        for k in (
            "enabled",
            "allowlist",
            "whitelist",
            "denylist",
            "blacklist",
            "overwrite",
            "mode",
        )
    ):
        files_cfg = cfg

    if isinstance(files_cfg, bool):
        policy["enabled"] = files_cfg
    elif isinstance(files_cfg, dict):
        if "enabled" in files_cfg:
            policy["enabled"] = util.is_true(files_cfg.get("enabled"))

        # Allowlist / Whitelist
        allow = files_cfg.get("allowlist")
        if allow is None:
            allow = files_cfg.get("whitelist")
        if allow is not None:
            if isinstance(allow, str):
                policy["allowlist"] = [allow]
            else:
                policy["allowlist"] = list(allow)

        # Denylist / Blacklist
        deny = files_cfg.get("denylist")
        if deny is None:
            deny = files_cfg.get("blacklist", [])
        if isinstance(deny, str):
            policy["denylist"] = [deny]
        elif deny:
            policy["denylist"] = list(deny)

        if "overwrite" in files_cfg:
            policy["overwrite"] = util.is_true(files_cfg.get("overwrite"))

        if "mode" in files_cfg:
            mode = files_cfg["mode"]
            if isinstance(mode, str):
                try:
                    policy["mode"] = int(mode, 8)
                except ValueError:
                    policy["mode"] = int(mode)
            else:
                policy["mode"] = int(mode)
    elif files_cfg is not None and util.is_false(files_cfg):
        policy["enabled"] = False

    # Check fallback flat keys under cfg
    if policy["allowlist"] is None:
        flat_allow = cfg.get("files_allowlist", cfg.get("files_whitelist"))
        if flat_allow is not None:
            if isinstance(flat_allow, str):
                policy["allowlist"] = [flat_allow]
            else:
                policy["allowlist"] = list(flat_allow)

    if not policy["denylist"]:
        flat_deny = cfg.get("files_denylist", cfg.get("files_blacklist", []))
        if isinstance(flat_deny, str):
            policy["denylist"] = [flat_deny]
        elif flat_deny:
            policy["denylist"] = list(flat_deny)

    if "files_overwrite" in cfg:
        policy["overwrite"] = util.is_true(cfg.get("files_overwrite"))

    return policy


def _matches_pattern(path, pattern):
    """Check if path matches a glob pattern case-sensitively."""
    if fnmatch.fnmatchcase(path, pattern):
        return True
    return fnmatch.fnmatchcase(path.lstrip(os.sep), pattern.lstrip(os.sep))


def _is_file_allowed(filename, policy):
    """Determine whether filename is permitted by the files policy."""
    for pattern in policy.get("denylist", []):
        if _matches_pattern(filename, pattern):
            LOG.info(
                "Skipping injected file %s: matches denylist (%s)",
                filename,
                pattern,
            )
            return False

    allowlist = policy.get("allowlist")
    if allowlist is not None:
        matched = False
        for pattern in allowlist:
            if _matches_pattern(filename, pattern):
                matched = True
                break
        if not matched:
            LOG.info(
                "Skipping injected file %s: does not match allowlist",
                filename,
            )
            return False

    return True


def on_first_boot(
    data, distro=None, network=True, files_policy=None, files_cfg=None
):
    """Performs any first-boot actions using data read from a config-drive."""
    if not isinstance(data, dict):
        raise TypeError(
            "Config-drive data expected to be a dict; not %s" % (type(data))
        )
    if files_policy is None and files_cfg is not None:
        files_policy = files_cfg
    if network:
        net_conf = data.get("network_config", "")
        if net_conf and distro:
            LOG.warning("Updating network interfaces from config drive")
            distro.apply_network_config(eni.convert_eni_data(net_conf))
    write_injected_files(data.get("files"), policy=files_policy)


def write_injected_files(files, policy=None, files_cfg=None):
    if not files:
        return

    if policy is None and files_cfg is not None:
        policy = files_cfg

    if not isinstance(policy, dict) or "enabled" not in policy:
        policy = extract_files_policy(policy)

    if not policy.get("enabled", True):
        LOG.debug(
            "Skipping %d injected files; file injection is disabled",
            len(files),
        )
        return

    LOG.debug("Writing %s injected files", len(files))
    for filename, content in files.items():
        if not filename.startswith(os.sep):
            filename = os.sep + filename
        filename = os.path.normpath(filename)

        if not _is_file_allowed(filename, policy):
            continue

        if not policy.get("overwrite", True) and os.path.lexists(filename):
            LOG.info(
                "Skipping injected file %s: file exists and overwrite is "
                "disabled",
                filename,
            )
            continue

        mode = policy.get("mode", 0o660)
        try:
            util.write_file(filename, content, mode=mode)
        except IOError:
            util.logexc(LOG, "Failed writing file: %s", filename)


def find_candidate_devs(probe_optical=True, dslist=None):
    """Return a list of devices that may contain the config drive.

    The returned list is sorted by search order where the first item has
    should be searched first (highest priority)

    config drive v1:
       Per documentation, this is "associated as the last available disk on the
       instance", and should be VFAT.
       Currently, we do not restrict search list to "last available disk"

    config drive v2:
       Disk should be:
        * either vfat or iso9660 formatted
        * labeled with 'config-2' or 'CONFIG-2'
    """
    if dslist is None:
        dslist = []

    # query optical drive to get it in blkid cache for 2.6 kernels
    if probe_optical:
        for device in OPTICAL_DEVICES:
            try:
                util.find_devs_with(path=device)
            except subp.ProcessExecutionError:
                pass

    by_fstype = []
    for fs_type in FS_TYPES:
        by_fstype.extend(util.find_devs_with("TYPE=%s" % (fs_type)))

    by_label = []
    for label in LABEL_TYPES:
        by_label.extend(util.find_devs_with("LABEL=%s" % (label)))

    # give preference to "last available disk" (vdb over vda)
    # note, this is not a perfect rendition of that.
    by_fstype.sort(reverse=True)
    by_label.sort(reverse=True)

    # combine list of items by putting by-label items first
    # followed by fstype items, but with dupes removed
    candidates = by_label + [d for d in by_fstype if d not in by_label]

    # We are looking for a block device or partition with necessary label or
    # an unpartitioned block device (ex sda, not sda1)
    devices = [
        d for d in candidates if d in by_label or not util.is_partition(d)
    ]

    LOG.debug("devices=%s dslist=%s", devices, dslist)
    if devices and "IBMCloud" in dslist:
        # IBMCloud uses config-2 label, but limited to a single UUID.
        ibm_platform, ibm_path = get_ibm_platform()
        if ibm_path in devices:
            devices.remove(ibm_path)
            LOG.debug(
                "IBMCloud device '%s' (%s) removed from candidate list",
                ibm_path,
                ibm_platform,
            )

    return devices


# Legacy: Must be present in case we load an old pkl object
DataSourceConfigDriveNet = DataSourceConfigDrive

# Used to match classes to dependencies
datasources = [
    (DataSourceConfigDrive, (sources.DEP_FILESYSTEM,)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
