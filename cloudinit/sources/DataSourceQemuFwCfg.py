# This file is part of cloud-init. See LICENSE file for license information.

"""DataSource for QEMU fw_cfg sysfs interface.

QEMU exposes arbitrary blobs to the guest via the fw_cfg mechanism.  The
Linux ``qemu_fw_cfg`` kernel driver surfaces these blobs under
``/sys/firmware/qemu_fw_cfg/by_name/<entry-name>/raw``.

This datasource reads the following fw_cfg entries
(all under the ``opt/io.cloud-init/cloud-init/`` namespace),
in the order that cloud-init processes them:

``meta-data``
    YAML dict with instance metadata (``instance-id``, ``local-hostname``, …)
``network-config``
    Network configuration in v1 or v2 YAML format.
``user-data``
    User-data payload (cloud-config YAML, shell script, etc.)
``vendor-data``
    Vendor-data payload.

Both ``meta-data`` and ``user-data`` must be present for the datasource to
claim the instance.
"""

import logging
import os

from cloudinit import sources, util

LOG = logging.getLogger(__name__)

# Base sysfs path exposed by the qemu_fw_cfg kernel driver.
FWCFG_SYSFS = "/sys/firmware/qemu_fw_cfg/by_name"
# fw_cfg entry namespace agreed upon by the cloud-init project.
FWCFG_PREFIX = "opt/io.cloud-init/cloud-init"
FWCFG_PATH = os.path.join(FWCFG_SYSFS, FWCFG_PREFIX)

DEFAULT_IID = "iid-qemufwcfg"
DEFAULT_METADATA = {"instance-id": DEFAULT_IID}

# Slots in the order they are read and applied by cloud-init:
_SLOT_FILES = ("meta-data", "network-config", "user-data", "vendor-data")
_REQUIRED_SLOTS = frozenset({"meta-data", "user-data"})


def _read_fwcfg_slot(name: str):
    """Return raw bytes from a fw_cfg slot, or None if the slot is absent."""
    raw_path = os.path.join(FWCFG_PATH, name, "raw")
    try:
        return util.load_binary_file(raw_path)
    except FileNotFoundError:
        return None
    except OSError as exc:
        LOG.warning("Failed to read fw_cfg slot %s: %s", name, exc)
        return None


class DataSourceQemuFwCfg(sources.DataSource):
    """Read instance configuration from QEMU fw_cfg sysfs entries."""

    dsname = "QemuFwCfg"

    def __init__(self, sys_cfg, distro, paths):
        super().__init__(sys_cfg, distro, paths)
        self._network_config = None

    def _unpickle(self, ci_pkl_version: int) -> None:
        super()._unpickle(ci_pkl_version)
        if not hasattr(self, "_network_config"):
            self._network_config = None

    def ds_detect(self) -> bool:
        """Return True when the fw_cfg namespace directory exists in sysfs."""
        return os.path.isdir(FWCFG_PATH)

    def _get_data(self) -> bool:
        mydata: dict = {
            "meta-data": {},
            "network-config": None,
            "user-data": "",
            "vendor-data": "",
        }
        found: set = set()

        for slot in _SLOT_FILES:
            raw = _read_fwcfg_slot(slot)
            if raw is None:
                continue
            found.add(slot)
            text = raw.decode("utf-8", errors="replace")

            if slot == "meta-data":
                md = util.load_yaml(text)
                if isinstance(md, dict):
                    mydata["meta-data"] = md
                else:
                    LOG.warning(
                        "meta-data did not parse as a YAML dict: ignoring"
                    )
            elif slot == "network-config":
                nc = util.load_yaml(text)
                if nc:
                    mydata["network-config"] = nc
            else:
                mydata[slot] = text

        missing = _REQUIRED_SLOTS - found
        if missing:
            LOG.debug(
                "QemuFwCfg: required slot(s) missing: %s",
                ", ".join(sorted(missing)),
            )
            return False

        # DEFAULT_METADATA to fill gap if user did not specify
        mydata["meta-data"] = util.mergemanydict(
            [mydata["meta-data"], DEFAULT_METADATA]
        )
        self.metadata = mydata["meta-data"]
        self._network_config = mydata["network-config"]
        self.userdata_raw = mydata["user-data"]
        self.vendordata_raw = mydata["vendor-data"]
        return True

    def _get_subplatform(self) -> str:
        return "fw_cfg (%s)" % FWCFG_PATH

    def _get_cloud_name(self) -> str:
        return sources.METADATA_UNKNOWN

    @property
    def network_config(self):
        return self._network_config


# QemuFwCfg only needs the filesystem (sysfs is available in the local stage).
datasources = [
    (DataSourceQemuFwCfg, (sources.DEP_FILESYSTEM,)),
]


def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
