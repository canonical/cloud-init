# Copyright (C) 2012 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import abc
import copy
import json
import logging
import os
import pickle
import re
from collections import namedtuple
from enum import Enum, unique
from typing import Any, Dict, List, Optional, Tuple, Union

from cloudinit import atomic_helper, dmi, importer, net, type_utils
from cloudinit import user_data as ud
from cloudinit import util
from cloudinit.atomic_helper import write_json
from cloudinit.distros import Distro
from cloudinit.event import EventScope, EventType
from cloudinit.filters import launch_index
from cloudinit.helpers import Paths
from cloudinit.persistence import CloudInitPickleMixin
from cloudinit.reporting import events

DSMODE_DISABLED = "disabled"
DSMODE_LOCAL = "local"
DSMODE_NETWORK = "net"
DSMODE_PASS = "pass"

VALID_DSMODES = [DSMODE_DISABLED, DSMODE_LOCAL, DSMODE_NETWORK]

DEP_FILESYSTEM = "FILESYSTEM"
DEP_NETWORK = "NETWORK"
DS_PREFIX = "DataSource"

EXPERIMENTAL_TEXT = (
    "EXPERIMENTAL: The structure and format of content scoped under the 'ds'"
    " key may change in subsequent releases of cloud-init."
)


REDACT_SENSITIVE_VALUE = "redacted for non-root user"

# Key which can be provide a cloud's official product name to cloud-init
METADATA_CLOUD_NAME_KEY = "cloud-name"

UNSET = "_unset"
METADATA_UNKNOWN = "unknown"

LOG = logging.getLogger(__name__)

# CLOUD_ID_REGION_PREFIX_MAP format is:
#  <region-match-prefix>: (<new-cloud-id>: <test_allowed_cloud_callable>)
CLOUD_ID_REGION_PREFIX_MAP = {
    "cn-": ("aws-china", lambda c: c == "aws"),  # only change aws regions
    "us-gov-": ("aws-gov", lambda c: c == "aws"),  # only change aws regions
    "china": ("azure-china", lambda c: c == "azure"),  # only change azure
}


@unique
class NetworkConfigSource(Enum):
    """
    Represents the canonical list of network config sources that cloud-init
    knows about.
    """

    CMD_LINE = "cmdline"
    DS = "ds"
    SYSTEM_CFG = "system_cfg"
    FALLBACK = "fallback"
    INITRAMFS = "initramfs"

    def __str__(self) -> str:
        return self.value


class NicOrder(Enum):
    """Represents ways to sort NICs"""

    MAC = "mac"
    NIC_NAME = "nic_name"

    def __str__(self) -> str:
        return self.value


class DatasourceUnpickleUserDataError(Exception):
    """Raised when userdata is unable to be unpickled due to python upgrades"""


class DataSourceNotFoundException(Exception):
    pass


class InvalidMetaDataException(Exception):
    """Raised when metadata is broken, unavailable or disabled."""


def process_instance_metadata(metadata, key_path="", sensitive_keys=()):
    """Process all instance metadata cleaning it up for persisting as json.

    Strip ci-b64 prefix and catalog any 'base64_encoded_keys' as a list

    @return Dict copy of processed metadata.
    """
    md_copy = copy.deepcopy(metadata)
    base64_encoded_keys = []
    sens_keys = []
    for key, val in metadata.items():
        if key_path:
            sub_key_path = key_path + "/" + key
        else:
            sub_key_path = key
        if (
            key.lower() in sensitive_keys
            or sub_key_path.lower() in sensitive_keys
        ):
            sens_keys.append(sub_key_path)
        if isinstance(val, str) and val.startswith("ci-b64:"):
            base64_encoded_keys.append(sub_key_path)
            md_copy[key] = val.replace("ci-b64:", "")
        if isinstance(val, dict):
            return_val = process_instance_metadata(
                val, sub_key_path, sensitive_keys
            )
            base64_encoded_keys.extend(return_val.pop("base64_encoded_keys"))
            sens_keys.extend(return_val.pop("sensitive_keys"))
            md_copy[key] = return_val
    md_copy["base64_encoded_keys"] = sorted(base64_encoded_keys)
    md_copy["sensitive_keys"] = sorted(sens_keys)
    return md_copy


def redact_sensitive_keys(metadata, redact_value=REDACT_SENSITIVE_VALUE):
    """Redact any sensitive keys from to provided metadata dictionary.

    Replace any keys values listed in 'sensitive_keys' with redact_value.
    """
    # While 'sensitive_keys' should already sanitized to only include what
    # is in metadata, it is possible keys will overlap. For example, if
    # "merged_cfg" and "merged_cfg/ds/userdata" both match, it's possible that
    # "merged_cfg" will get replaced first, meaning "merged_cfg/ds/userdata"
    # no longer represents a valid key.
    # Thus, we still need to do membership checks in this function.
    if not metadata.get("sensitive_keys", []):
        return metadata
    md_copy = copy.deepcopy(metadata)
    for key_path in metadata.get("sensitive_keys"):
        path_parts = key_path.split("/")
        obj = md_copy
        for path in path_parts:
            if (
                path in obj
                and isinstance(obj[path], dict)
                and path != path_parts[-1]
            ):
                obj = obj[path]
        if path in obj:
            obj[path] = redact_value
    return md_copy


URLParams = namedtuple(
    "URLParams",
    [
        "max_wait_seconds",
        "timeout_seconds",
        "num_retries",
        "sec_between_retries",
    ],
)

DataSourceHostname = namedtuple(
    "DataSourceHostname",
    ["hostname", "is_default"],
)


class DataSource(CloudInitPickleMixin, metaclass=abc.ABCMeta):

    dsmode = DSMODE_NETWORK
    default_locale = "en_US.UTF-8"

    # Datasource name needs to be set by subclasses to determine which
    # cloud-config datasource key is loaded
    dsname = "_undef"

    # Cached cloud_name as determined by _get_cloud_name
    _cloud_name = None

    # Cached cloud platform api type: e.g. ec2, openstack, kvm, lxd, azure etc.
    _platform_type = None

    # More details about the cloud platform:
    #  - metadata (http://169.254.169.254/)
    #  - seed-dir (<dirname>)
    _subplatform = None

    _crawled_metadata: Optional[Union[Dict, str]] = None

    # The network configuration sources that should be considered for this data
    # source.  (The first source in this list that provides network
    # configuration will be used without considering any that follow.)  This
    # should always be a subset of the members of NetworkConfigSource with no
    # duplicate entries.
    network_config_sources: Tuple[NetworkConfigSource, ...] = (
        NetworkConfigSource.CMD_LINE,
        NetworkConfigSource.INITRAMFS,
        NetworkConfigSource.SYSTEM_CFG,
        NetworkConfigSource.DS,
    )

    # read_url_params
    url_max_wait = -1  # max_wait < 0 means do not wait
    url_timeout = 10  # timeout for each metadata url read attempt
    url_retries = 5  # number of times to retry url upon 404
    url_sec_between_retries = 1  # amount of seconds to wait between retries

    # The datasource defines a set of supported EventTypes during which
    # the datasource can react to changes in metadata and regenerate
    # network configuration on metadata changes. These are defined in
    # `supported_network_events`.
    # The datasource also defines a set of default EventTypes that the
    # datasource can react to. These are the event types that will be used
    # if not overridden by the user.
    #
    # A datasource requiring to write network config on each system boot
    # would either:
    #
    # 1) Overwrite the class attribute `default_update_events` like:
    #
    # >>> default_update_events = {
    # ...     EventScope.NETWORK: {
    # ...         EventType.BOOT_NEW_INSTANCE,
    # ...         EventType.BOOT,
    # ...     }
    # ... }
    #
    # 2) Or, if writing network config on every boot has to be determined at
    # runtime, then deepcopy to not overwrite the class attribute on other
    # elements of this class hierarchy, like:
    #
    # >>> self.default_update_events = copy.deepcopy(
    # ...    self.default_update_events
    # ... )
    # >>> self.default_update_events[EventScope.NETWORK].add(EventType.BOOT)

    supported_update_events = {
        EventScope.NETWORK: {
            EventType.BOOT_NEW_INSTANCE,
            EventType.BOOT,
            EventType.BOOT_LEGACY,
            EventType.HOTPLUG,
        }
    }

    # Default: generate network config on new instance id (first boot).
    default_update_events = {
        EventScope.NETWORK: {
            EventType.BOOT_NEW_INSTANCE,
        }
    }

    # N-tuple listing default values for any metadata-related class
    # attributes cached on an instance by a process_data runs. These attribute
    # values are reset via clear_cached_attrs during any update_metadata call.
    cached_attr_defaults: Tuple[Tuple[str, Any], ...] = (
        ("ec2_metadata", UNSET),
        ("network_json", UNSET),
        ("metadata", {}),
        ("userdata", None),
        ("userdata_raw", None),
        ("vendordata", None),
        ("vendordata_raw", None),
        ("vendordata2", None),
        ("vendordata2_raw", None),
    )

    _dirty_cache = False

    # N-tuple of keypaths or keynames redact from instance-data.json for
    # non-root users
    sensitive_metadata_keys: Tuple[str, ...] = (
        "combined_cloud_config",
        "merged_cfg",
        "merged_system_cfg",
        "security-credentials",
        "userdata",
        "user-data",
        "user_data",
        "vendordata",
        "vendor-data",
        # Provide ds/vendor_data to avoid redacting top-level
        #  "vendor_data": {enabled: True}
        "ds/vendor_data",
    )

    # True on datasources that may not see hotplugged devices reflected
    # in the updated metadata
    skip_hotplug_detect = False

    # Extra udev rules for cc_install_hotplug
    extra_hotplug_udev_rules: Optional[str] = None

    _ci_pkl_version = 1

    def __init__(self, sys_cfg, distro: Distro, paths: Paths, ud_proc=None):
        self.sys_cfg = sys_cfg
        self.distro = distro
        self.paths = paths
        self.userdata: Optional[Any] = None
        self.metadata: dict = {}
        self.userdata_raw: Optional[str] = None
        self.vendordata = None
        self.vendordata2 = None
        self.vendordata_raw = None
        self.vendordata2_raw = None
        self.metadata_address = None
        self.network_json = UNSET
        self.ec2_metadata = UNSET

        self.ds_cfg = util.get_cfg_by_path(
            self.sys_cfg, ("datasource", self.dsname), {}
        )
        if not self.ds_cfg:
            self.ds_cfg = {}

        if not ud_proc:
            self.ud_proc = ud.UserDataProcessor(self.paths)
        else:
            self.ud_proc = ud_proc

    def _unpickle(self, ci_pkl_version: int) -> None:
        """Perform deserialization fixes for Paths."""
        expected_attrs = {
            "_crawled_metadata": None,
            "_platform_type": None,
            "_subplatform": None,
            "ec2_metadata": UNSET,
            "extra_hotplug_udev_rules": None,
            "metadata_address": None,
            "network_json": UNSET,
            "skip_hotplug_detect": False,
            "vendordata2": None,
            "vendordata2_raw": None,
        }
        for key, value in expected_attrs.items():
            if not hasattr(self, key):
                setattr(self, key, value)

        if not hasattr(self, "check_if_fallback_is_allowed"):
            setattr(self, "check_if_fallback_is_allowed", lambda: False)
        if hasattr(self, "userdata") and self.userdata is not None:
            # If userdata stores MIME data, on < python3.6 it will be
            # missing the 'policy' attribute that exists on >=python3.6.
            # Calling str() on the userdata will attempt to access this
            # policy attribute. This will raise an exception, causing
            # the pickle load to fail, so cloud-init will discard the cache
            try:
                str(self.userdata)
            except AttributeError as e:
                LOG.debug(
                    "Unable to unpickle datasource: %s."
                    " Ignoring current cache.",
                    e,
                )
                raise DatasourceUnpickleUserDataError() from e

    def __str__(self):
        return type_utils.obj_name(self)

    def ds_detect(self) -> bool:
        """Check if running on this datasource"""
        return True

    def override_ds_detect(self) -> bool:
        """Override if either:
        - only a single datasource defined (nothing to fall back to)
        - command line argument is used (ci.ds=OpenStack)

        Note: get_cmdline() is required for the general case - when ds-identify
        does not run, _something_ needs to detect the kernel command line
        definition.
        """
        if self.dsname.lower() == parse_cmdline().lower():
            LOG.debug(
                "Machine is configured by the kernel command line to run on "
                "single datasource %s.",
                self,
            )
            return True
        elif self.sys_cfg.get("datasource_list", []) == [self.dsname]:
            LOG.debug(
                "Machine is configured to run on single datasource %s.", self
            )
            return True
        return False

    def _check_and_get_data(self):
        """Overrides runtime datasource detection"""
        if self.override_ds_detect():
            return self._get_data()
        elif self.ds_detect():
            LOG.debug(
                "Detected platform: %s. Checking for active instance data",
                self,
            )
            return self._get_data()
        else:
            LOG.debug("Datasource type %s is not detected.", self)
            return False

    def _get_standardized_metadata(self, instance_data):
        """Return a dictionary of standardized metadata keys."""
        local_hostname = self.get_hostname().hostname
        instance_id = self.get_instance_id()
        availability_zone = self.availability_zone
        # In the event of upgrade from existing cloudinit, pickled datasource
        # will not contain these new class attributes. So we need to recrawl
        # metadata to discover that content
        sysinfo = instance_data["sys_info"]
        return {
            "v1": {
                "_beta_keys": ["subplatform"],
                "availability-zone": availability_zone,
                "availability_zone": availability_zone,
                "cloud_id": canonical_cloud_id(
                    self.cloud_name, self.region, self.platform_type
                ),
                "cloud-name": self.cloud_name,
                "cloud_name": self.cloud_name,
                "distro": sysinfo["dist"][0],
                "distro_version": sysinfo["dist"][1],
                "distro_release": sysinfo["dist"][2],
                "platform": self.platform_type,
                "public_ssh_keys": self.get_public_ssh_keys(),
                "python_version": sysinfo["python"],
                "instance-id": instance_id,
                "instance_id": instance_id,
                "kernel_release": sysinfo["uname"][2],
                "local-hostname": local_hostname,
                "local_hostname": local_hostname,
                "machine": sysinfo["uname"][4],
                "region": self.region,
                "subplatform": self.subplatform,
                "system_platform": sysinfo["platform"],
                "variant": sysinfo["variant"],
            }
        }

    def clear_cached_attrs(self, attr_defaults=()):
        """Reset any cached metadata attributes to datasource defaults.

        @param attr_defaults: Optional tuple of (attr, value) pairs to
           set instead of cached_attr_defaults.
        """
        if not self._dirty_cache:
            return
        if attr_defaults:
            attr_values = attr_defaults
        else:
            attr_values = self.cached_attr_defaults

        for attribute, value in attr_values:
            if hasattr(self, attribute):
                setattr(self, attribute, value)
        if not attr_defaults:
            self._dirty_cache = False

    def get_data(self) -> bool:
        """Datasources implement _get_data to setup metadata and userdata_raw.

        Minimally, the datasource should return a boolean True on success.
        """
        self._dirty_cache = True
        return_value = self._check_and_get_data()
        # TODO: verify that datasource types are what they are expected to be
        # each datasource uses different logic to get userdata, metadata, etc
        # and then the rest of the codebase assumes the types of this data
        # it would be prudent to have a type check here that warns, when the
        # datatype is incorrect, rather than assuming types and throwing
        # exceptions later if/when they get used incorrectly.
        if not return_value:
            return return_value
        self.persist_instance_data()
        return return_value

    def persist_instance_data(self, write_cache=True):
        """Process and write INSTANCE_JSON_FILE with all instance metadata.

        Replace any hyphens with underscores in key names for use in template
        processing.

        :param write_cache: boolean set True to persist obj.pkl when
            instance_link exists.

        @return True on successful write, False otherwise.
        """
        if write_cache and os.path.lexists(self.paths.instance_link):
            pkl_store(self, self.paths.get_ipath_cur("obj_pkl"))
        if self._crawled_metadata is not None:
            # Any datasource with _crawled_metadata will best represent
            # most recent, 'raw' metadata
            crawled_metadata = copy.deepcopy(self._crawled_metadata)
            crawled_metadata.pop("user-data", None)
            crawled_metadata.pop("vendor-data", None)
            instance_data = {"ds": crawled_metadata}
        else:
            instance_data = {"ds": {"meta_data": self.metadata}}
            if self.network_json != UNSET:
                instance_data["ds"]["network_json"] = self.network_json
            if self.ec2_metadata != UNSET:
                instance_data["ds"]["ec2_metadata"] = self.ec2_metadata
        instance_data["ds"]["_doc"] = EXPERIMENTAL_TEXT
        # Add merged cloud.cfg and sys info for jinja templates and cli query
        instance_data["merged_cfg"] = copy.deepcopy(self.sys_cfg)
        instance_data["merged_cfg"][
            "_doc"
        ] = "DEPRECATED: Use merged_system_cfg. Will be dropped from 24.1"
        # Deprecate merged_cfg to a more specific key name merged_system_cfg
        instance_data["merged_system_cfg"] = copy.deepcopy(
            instance_data["merged_cfg"]
        )
        instance_data["merged_system_cfg"]["_doc"] = (
            "Merged cloud-init system config from /etc/cloud/cloud.cfg and"
            " /etc/cloud/cloud.cfg.d/"
        )
        instance_data["sys_info"] = util.system_info()
        instance_data.update(self._get_standardized_metadata(instance_data))
        try:
            # Process content base64encoding unserializable values
            content = atomic_helper.json_dumps(instance_data)
            # Strip base64: prefix and set base64_encoded_keys list.
            processed_data = process_instance_metadata(
                json.loads(content),
                sensitive_keys=self.sensitive_metadata_keys,
            )
        except TypeError as e:
            LOG.warning("Error persisting instance-data.json: %s", str(e))
            return False
        except UnicodeDecodeError as e:
            LOG.warning("Error persisting instance-data.json: %s", str(e))
            return False
        json_sensitive_file = self.paths.get_runpath("instance_data_sensitive")
        cloud_id = instance_data["v1"].get("cloud_id", "none")
        cloud_id_file = os.path.join(self.paths.run_dir, "cloud-id")
        util.write_file(f"{cloud_id_file}-{cloud_id}", f"{cloud_id}\n")
        # cloud-id not found, then no previous cloud-id file
        prev_cloud_id_file = None
        new_cloud_id_file = f"{cloud_id_file}-{cloud_id}"
        # cloud-id found, then the prev cloud-id file is source of symlink
        if os.path.exists(cloud_id_file):
            prev_cloud_id_file = os.path.realpath(cloud_id_file)

        util.sym_link(new_cloud_id_file, cloud_id_file, force=True)
        if prev_cloud_id_file and prev_cloud_id_file != new_cloud_id_file:
            util.del_file(prev_cloud_id_file)
        write_json(json_sensitive_file, processed_data, mode=0o600)
        json_file = self.paths.get_runpath("instance_data")
        # World readable
        write_json(json_file, redact_sensitive_keys(processed_data))
        return True

    def _get_data(self) -> bool:
        """Walk metadata sources, process crawled data and save attributes."""
        raise NotImplementedError(
            "Subclasses of DataSource must implement _get_data which"
            " sets self.metadata, vendordata_raw and userdata_raw."
        )

    def get_url_params(self):
        """Return the Datasource's preferred url_read parameters.

        Subclasses may override url_max_wait, url_timeout, url_retries.

        @return: A URLParams object with max_wait_seconds, timeout_seconds,
            num_retries.
        """
        max_wait = self.url_max_wait
        try:
            max_wait = int(self.ds_cfg.get("max_wait", self.url_max_wait))
        except ValueError:
            util.logexc(
                LOG,
                "Config max_wait '%s' is not an int, using default '%s'",
                self.ds_cfg.get("max_wait"),
                max_wait,
            )

        timeout = self.url_timeout
        try:
            timeout = max(0, int(self.ds_cfg.get("timeout", self.url_timeout)))
        except ValueError:
            timeout = self.url_timeout
            util.logexc(
                LOG,
                "Config timeout '%s' is not an int, using default '%s'",
                self.ds_cfg.get("timeout"),
                timeout,
            )

        retries = self.url_retries
        try:
            retries = int(self.ds_cfg.get("retries", self.url_retries))
        except Exception:
            util.logexc(
                LOG,
                "Config retries '%s' is not an int, using default '%s'",
                self.ds_cfg.get("retries"),
                retries,
            )

        sec_between_retries = self.url_sec_between_retries
        try:
            sec_between_retries = int(
                self.ds_cfg.get(
                    "sec_between_retries", self.url_sec_between_retries
                )
            )
        except Exception:
            util.logexc(
                LOG,
                "Config sec_between_retries '%s' is not an int,"
                " using default '%s'",
                self.ds_cfg.get("sec_between_retries"),
                sec_between_retries,
            )

        return URLParams(max_wait, timeout, retries, sec_between_retries)

    def get_userdata(self, apply_filter=False):
        if self.userdata is None:
            self.userdata = self.ud_proc.process(self.get_userdata_raw())
        if apply_filter:
            return self._filter_xdata(self.userdata)
        return self.userdata

    def get_vendordata(self):
        if self.vendordata is None:
            self.vendordata = self.ud_proc.process(self.get_vendordata_raw())
        return self.vendordata

    def get_vendordata2(self):
        if self.vendordata2 is None:
            self.vendordata2 = self.ud_proc.process(self.get_vendordata2_raw())
        return self.vendordata2

    @property
    def platform_type(self):
        if not self._platform_type:
            self._platform_type = self.dsname.lower()
        return self._platform_type

    @property
    def subplatform(self):
        """Return a string representing subplatform details for the datasource.

        This should be guidance for where the metadata is sourced.
        Examples of this on different clouds:
            ec2:       metadata (http://169.254.169.254)
            openstack: configdrive (/dev/path)
            openstack: metadata (http://169.254.169.254)
            nocloud:   seed-dir (/seed/dir/path)
            lxd:   nocloud (/seed/dir/path)
        """
        if not self._subplatform:
            self._subplatform = self._get_subplatform()
        return self._subplatform

    def _get_subplatform(self):
        """Subclasses should implement to return a "slug (detail)" string."""
        if self.metadata_address:
            return f"metadata ({self.metadata_address})"
        return METADATA_UNKNOWN

    @property
    def cloud_name(self):
        """Return lowercase cloud name as determined by the datasource.

        Datasource can determine or define its own cloud product name in
        metadata.
        """
        if self._cloud_name:
            return self._cloud_name
        if self.metadata and self.metadata.get(METADATA_CLOUD_NAME_KEY):
            cloud_name = self.metadata.get(METADATA_CLOUD_NAME_KEY)
            if isinstance(cloud_name, str):
                self._cloud_name = cloud_name.lower()
            else:
                self._cloud_name = self._get_cloud_name().lower()
                LOG.debug(
                    "Ignoring metadata provided key %s: non-string type %s",
                    METADATA_CLOUD_NAME_KEY,
                    type(cloud_name),
                )
        else:
            self._cloud_name = self._get_cloud_name().lower()
        return self._cloud_name

    def _get_cloud_name(self):
        """Return the datasource name as it frequently matches cloud name.

        Should be overridden in subclasses which can run on multiple
        cloud names, such as DatasourceEc2.
        """
        return self.dsname

    @property
    def launch_index(self):
        if not self.metadata:
            return None
        if "launch-index" in self.metadata:
            return self.metadata["launch-index"]
        return None

    def _filter_xdata(self, processed_ud):
        filters = [
            launch_index.Filter(util.safe_int(self.launch_index)),
        ]
        new_ud = processed_ud
        for f in filters:
            new_ud = f.apply(new_ud)
        return new_ud

    def get_userdata_raw(self):
        return self.userdata_raw

    def get_vendordata_raw(self):
        return self.vendordata_raw

    def get_vendordata2_raw(self):
        return self.vendordata2_raw

    # the data sources' config_obj is a cloud-config formatted
    # object that came to it from ways other than cloud-config
    # because cloud-config content would be handled elsewhere
    def get_config_obj(self):
        return {}

    def get_public_ssh_keys(self):
        return normalize_pubkey_data(self.metadata.get("public-keys"))

    def publish_host_keys(self, hostkeys):
        """Publish the public SSH host keys (found in /etc/ssh/*.pub).

        @param hostkeys: List of host key tuples (key_type, key_value),
            where key_type is the first field in the public key file
            (e.g. 'ssh-rsa') and key_value is the key itself
            (e.g. 'AAAAB3NzaC1y...').
        """

    def _remap_device(self, short_name):
        # LP: #611137
        # the metadata service may believe that devices are named 'sda'
        # when the kernel named them 'vda' or 'xvda'
        # we want to return the correct value for what will actually
        # exist in this instance
        mappings = {"sd": ("vd", "xvd", "vtb")}
        for (nfrom, tlist) in mappings.items():
            if not short_name.startswith(nfrom):
                continue
            for nto in tlist:
                cand = "/dev/%s%s" % (nto, short_name[len(nfrom) :])
                if os.path.exists(cand):
                    return cand
        return None

    def device_name_to_device(self, _name):
        # translate a 'name' to a device
        # the primary function at this point is on ec2
        # to consult metadata service, that has
        #  ephemeral0: sdb
        # and return 'sdb' for input 'ephemeral0'
        return None

    def get_locale(self):
        """Default locale is en_US.UTF-8, but allow distros to override"""
        locale = self.default_locale
        try:
            locale = self.distro.get_locale()
        except NotImplementedError:
            pass
        return locale

    @property
    def availability_zone(self):
        top_level_az = self.metadata.get(
            "availability-zone", self.metadata.get("availability_zone")
        )
        if top_level_az:
            return top_level_az
        return self.metadata.get("placement", {}).get("availability-zone")

    @property
    def region(self):
        return self.metadata.get("region")

    def get_instance_id(self):
        if not self.metadata or "instance-id" not in self.metadata:
            # Return a magic not really instance id string
            return "iid-datasource"
        return str(self.metadata["instance-id"])

    def get_hostname(self, fqdn=False, resolve_ip=False, metadata_only=False):
        """Get hostname or fqdn from the datasource. Look it up if desired.

        @param fqdn: Boolean, set True to return hostname with domain.
        @param resolve_ip: Boolean, set True to attempt to resolve an ipv4
            address provided in local-hostname meta-data.
        @param metadata_only: Boolean, set True to avoid looking up hostname
            if meta-data doesn't have local-hostname present.

        @return: a DataSourceHostname namedtuple
            <hostname or qualified hostname>, <is_default> (str, bool).
            is_default is a bool and
            it's true only if hostname is localhost and was
            returned by util.get_hostname() as a default.
            This is used to differentiate with a user-defined
            localhost hostname.
            Optionally return (None, False) when
            metadata_only is True and local-hostname data is not available.
        """
        defdomain = "localdomain"
        defhost = "localhost"
        domain = defdomain
        is_default = False

        if not self.metadata or not self.metadata.get("local-hostname"):
            if metadata_only:
                return DataSourceHostname(None, is_default)
            # this is somewhat questionable really.
            # the cloud datasource was asked for a hostname
            # and didn't have one. raising error might be more appropriate
            # but instead, basically look up the existing hostname
            toks = []
            hostname = util.get_hostname()
            if hostname == "localhost":
                # default hostname provided by socket.gethostname()
                is_default = True
            hosts_fqdn = util.get_fqdn_from_hosts(hostname)
            if hosts_fqdn and hosts_fqdn.find(".") > 0:
                toks = str(hosts_fqdn).split(".")
            elif hostname and hostname.find(".") > 0:
                toks = str(hostname).split(".")
            elif hostname:
                toks = [hostname, defdomain]
            else:
                toks = [defhost, defdomain]
        else:
            # if there is an ipv4 address in 'local-hostname', then
            # make up a hostname (LP: #475354) in format ip-xx.xx.xx.xx
            lhost = self.metadata["local-hostname"]
            if net.is_ipv4_address(lhost):
                toks = []
                if resolve_ip:
                    toks = util.gethostbyaddr(lhost)

                if toks:
                    toks = str(toks).split(".")
                else:
                    toks = ["ip-%s" % lhost.replace(".", "-")]
            else:
                toks = lhost.split(".")

        if len(toks) > 1:
            hostname = toks[0]
            domain = ".".join(toks[1:])
        else:
            hostname = toks[0]

        if fqdn and domain != defdomain:
            hostname = "%s.%s" % (hostname, domain)

        return DataSourceHostname(hostname, is_default)

    def get_package_mirror_info(self):
        return self.distro.get_package_mirror_info(data_source=self)

    def get_supported_events(self, source_event_types: List[EventType]):
        supported_events: Dict[EventScope, set] = {}
        for event in source_event_types:
            for (
                update_scope,
                update_events,
            ) in self.supported_update_events.items():
                if event in update_events:
                    if not supported_events.get(update_scope):
                        supported_events[update_scope] = set()
                    supported_events[update_scope].add(event)
        return supported_events

    def update_metadata_if_supported(
        self, source_event_types: List[EventType]
    ) -> bool:
        """Refresh cached metadata if the datasource supports this event.

        The datasource has a list of supported_update_events which
        trigger refreshing all cached metadata as well as refreshing the
        network configuration.

        @param source_event_types: List of EventTypes which may trigger a
            metadata update.

        @return True if the datasource did successfully update cached metadata
            due to source_event_type.
        """
        supported_events = self.get_supported_events(source_event_types)
        for scope, matched_events in supported_events.items():
            LOG.debug(
                "Update datasource metadata and %s config due to events: %s",
                scope.value,
                ", ".join([event.value for event in matched_events]),
            )
            # Each datasource has a cached config property which needs clearing
            # Once cleared that config property will be regenerated from
            # current metadata.
            self.clear_cached_attrs((("_%s_config" % scope, UNSET),))
        if supported_events:
            self.clear_cached_attrs()
            result = self.get_data()
            if result:
                return True
        LOG.debug(
            "Datasource %s not updated for events: %s",
            self,
            ", ".join([event.value for event in source_event_types]),
        )
        return False

    def check_instance_id(self, sys_cfg):
        # quickly (local check only) if self.instance_id is still
        return False

    def check_if_fallback_is_allowed(self):
        """check_if_fallback_is_allowed()
        Checks if a cached ds is allowed to be restored when no valid ds is
        found in local mode by checking instance-id and searching valid data
        through ds list.

        @return True if a ds allows fallback, False otherwise.
        """
        return False

    @staticmethod
    def _determine_dsmode(candidates, default=None, valid=None):
        # return the first candidate that is non None, warn if not valid
        if default is None:
            default = DSMODE_NETWORK

        if valid is None:
            valid = VALID_DSMODES

        for candidate in candidates:
            if candidate is None:
                continue
            if candidate in valid:
                return candidate
            else:
                LOG.warning(
                    "invalid dsmode '%s', using default=%s", candidate, default
                )
                return default

        return default

    @property
    def network_config(self):
        return None

    def setup(self, is_new_instance):
        """setup(is_new_instance)

        This is called before user-data and vendor-data have been processed.

        Unless the datasource has set mode to 'local', then networking
        per 'fallback' or per 'network_config' will have been written and
        brought up the OS at this point.
        """
        return

    def activate(self, cfg, is_new_instance):
        """activate(cfg, is_new_instance)

        This is called before the init_modules will be called but after
        the user-data and vendor-data have been fully processed.

        The cfg is fully up to date config, it contains a merged view of
           system config, datasource config, user config, vendor config.
        It should be used rather than the sys_cfg passed to __init__.

        is_new_instance is a boolean indicating if this is a new instance.
        """
        return


def normalize_pubkey_data(pubkey_data):
    keys = []

    if not pubkey_data:
        return keys

    if isinstance(pubkey_data, str):
        return pubkey_data.splitlines()

    if isinstance(pubkey_data, (list, set)):
        return list(pubkey_data)

    if isinstance(pubkey_data, (dict)):
        for (_keyname, klist) in pubkey_data.items():
            # lp:506332 uec metadata service responds with
            # data that makes boto populate a string for 'klist' rather
            # than a list.
            if isinstance(klist, str):
                klist = [klist]
            if isinstance(klist, (list, set)):
                for pkey in klist:
                    # There is an empty string at
                    # the end of the keylist, trim it
                    if pkey:
                        keys.append(pkey)

    return keys


def find_source(
    sys_cfg, distro, paths, ds_deps, cfg_list, pkg_list, reporter
) -> Tuple[DataSource, str]:
    ds_list = list_sources(cfg_list, ds_deps, pkg_list)
    ds_names = [type_utils.obj_name(f) for f in ds_list]
    mode = "network" if DEP_NETWORK in ds_deps else "local"
    LOG.debug("Searching for %s data source in: %s", mode, ds_names)

    for name, cls in zip(ds_names, ds_list):
        myrep = events.ReportEventStack(
            name="search-%s" % name.replace("DataSource", ""),
            description="searching for %s data from %s" % (mode, name),
            message="no %s data found from %s" % (mode, name),
            parent=reporter,
        )
        try:
            with myrep:
                LOG.debug("Seeing if we can get any data from %s", cls)
                s = cls(sys_cfg, distro, paths)
                if s.update_metadata_if_supported(
                    [EventType.BOOT_NEW_INSTANCE]
                ):
                    myrep.message = "found %s data from %s" % (mode, name)
                    return (s, type_utils.obj_name(cls))
        except Exception:
            util.logexc(LOG, "Getting data from %s failed", cls)

    msg = "Did not find any data source, searched classes: (%s)" % ", ".join(
        ds_names
    )
    raise DataSourceNotFoundException(msg)


def list_sources(cfg_list, depends, pkg_list):
    """Return a list of classes that have the same depends as 'depends'
    iterate through cfg_list, loading "DataSource*" modules
    and calling their "get_datasource_list".
    Return an ordered list of classes that match (if any)
    """
    src_list = []
    LOG.debug(
        "Looking for data source in: %s,"
        " via packages %s that matches dependencies %s",
        cfg_list,
        pkg_list,
        depends,
    )

    for ds in cfg_list:
        ds_name = importer.match_case_insensitive_module_name(ds)
        m_locs, _looked_locs = importer.find_module(
            ds_name, pkg_list, ["get_datasource_list"]
        )
        if not m_locs:
            LOG.error(
                "Could not import %s. Does the DataSource exist and "
                "is it importable?",
                ds_name,
            )
        for m_loc in m_locs:
            mod = importer.import_module(m_loc)
            lister = getattr(mod, "get_datasource_list")
            matches = lister(depends)
            if matches:
                src_list.extend(matches)
                break
    return src_list


def instance_id_matches_system_uuid(
    instance_id, field: str = "system-uuid"
) -> bool:
    # quickly (local check only) if self.instance_id is still valid
    # we check kernel command line or files.
    if not instance_id:
        return False

    dmi_value = dmi.read_dmi_data(field)
    if not dmi_value:
        return False
    return instance_id.lower() == dmi_value.lower()


def canonical_cloud_id(cloud_name, region, platform):
    """Lookup the canonical cloud-id for a given cloud_name and region."""
    if not cloud_name:
        cloud_name = METADATA_UNKNOWN
    if not region:
        region = METADATA_UNKNOWN
    if region == METADATA_UNKNOWN:
        if cloud_name != METADATA_UNKNOWN:
            return cloud_name
        return platform
    for prefix, cloud_id_test in CLOUD_ID_REGION_PREFIX_MAP.items():
        (cloud_id, valid_cloud) = cloud_id_test
        if region.startswith(prefix) and valid_cloud(cloud_name):
            return cloud_id
    if cloud_name != METADATA_UNKNOWN:
        return cloud_name
    return platform


def convert_vendordata(data, recurse=True):
    """data: a loaded object (strings, arrays, dicts).
    return something suitable for cloudinit vendordata_raw.

    if data is:
       None: return None
       string: return string
       list: return data
             the list is then processed in UserDataProcessor
       dict: return convert_vendordata(data.get('cloud-init'))
    """
    if not data:
        return None
    if isinstance(data, str):
        return data
    if isinstance(data, list):
        return copy.deepcopy(data)
    if isinstance(data, dict):
        if recurse is True:
            return convert_vendordata(data.get("cloud-init"), recurse=False)
        raise ValueError("vendordata['cloud-init'] cannot be dict")
    raise ValueError("Unknown data type for vendordata: %s" % type(data))


class BrokenMetadata(IOError):
    pass


# 'depends' is a list of dependencies (DEP_FILESYSTEM)
# ds_list is a list of 2 item lists
# ds_list = [
#   ( class, ( depends-that-this-class-needs ) )
# }
# It returns a list of 'class' that matched these deps exactly
# It mainly is a helper function for DataSourceCollections
def list_from_depends(depends, ds_list):
    ret_list = []
    depset = set(depends)
    for (cls, deps) in ds_list:
        if depset == set(deps):
            ret_list.append(cls)
    return ret_list


def pkl_store(obj: DataSource, fname: str) -> bool:
    """Use pickle to serialize Datasource to a file as a cache.

    :return: True on success
    """
    try:
        pk_contents = pickle.dumps(obj)
    except Exception:
        util.logexc(LOG, "Failed pickling datasource %s", obj)
        return False
    try:
        util.write_file(fname, pk_contents, omode="wb", mode=0o400)
    except Exception:
        util.logexc(LOG, "Failed pickling datasource to %s", fname)
        return False
    return True


def pkl_load(fname: str) -> Optional[DataSource]:
    """Use pickle to deserialize a instance Datasource from a cache file."""
    pickle_contents = None
    try:
        pickle_contents = util.load_binary_file(fname)
    except Exception as e:
        if os.path.isfile(fname):
            LOG.warning("failed loading pickle in %s: %s", fname, e)

    # This is allowed so just return nothing successfully loaded...
    if not pickle_contents:
        return None
    try:
        return pickle.loads(pickle_contents)
    except DatasourceUnpickleUserDataError:
        return None
    except Exception:
        util.logexc(LOG, "Failed loading pickled blob from %s", fname)
        return None


def parse_cmdline() -> str:
    """Check if command line argument for this datasource was passed
    Passing by command line overrides runtime datasource detection
    """
    return parse_cmdline_or_dmi(util.get_cmdline())


def parse_cmdline_or_dmi(input: str) -> str:
    ds_parse_0 = re.search(r"(?:^|\s)ds=([^\s;]+)", input)
    ds_parse_1 = re.search(r"(?:^|\s)ci\.ds=([^\s;]+)", input)
    ds_parse_2 = re.search(r"(?:^|\s)ci\.datasource=([^\s;]+)", input)
    ds = ds_parse_0 or ds_parse_1 or ds_parse_2
    deprecated = ds_parse_1 or ds_parse_2
    if deprecated:
        dsname = deprecated.group(1).strip()
        util.deprecate(
            deprecated=(
                f"Defining the datasource on the command line using "
                f"ci.ds={dsname} or "
                f"ci.datasource={dsname}"
            ),
            deprecated_version="23.2",
            extra_message=f"Use ds={dsname} instead",
        )
    if ds and ds.group(1):
        return ds.group(1)
    return ""
