# Copyright (C) 2023 Microsoft Corporation.
#
# This file is part of cloud-init. See LICENSE file for license information.

import enum
import logging
import os
import uuid
from typing import Optional

from cloudinit import dmi
from cloudinit.sources.helpers.azure import report_diagnostic_event

LOG = logging.getLogger(__name__)


def byte_swap_system_uuid(system_uuid: str) -> str:
    """Byte swap system uuid.

    Azure always uses little-endian for the first three fields in the uuid.
    This behavior was made strict in SMBIOS 2.6+, but Linux and dmidecode
    follow RFC 4122 and assume big-endian for earlier SMBIOS versions.

    Azure's gen1 VMs use SMBIOS 2.3 which requires byte swapping to match
    compute.vmId presented by IMDS.

    Azure's gen2 VMs use SMBIOS 3.1 which does not require byte swapping.

    :raises ValueError: if UUID is invalid.
    """
    try:
        original_uuid = uuid.UUID(system_uuid)
    except ValueError:
        msg = f"Failed to parse system uuid: {system_uuid!r}"
        report_diagnostic_event(msg, logger_func=LOG.error)
        raise

    return str(uuid.UUID(bytes=original_uuid.bytes_le))


def convert_system_uuid_to_vm_id(system_uuid: str) -> str:
    """Determine VM ID from system uuid."""
    if is_vm_gen1():
        return byte_swap_system_uuid(system_uuid)

    return system_uuid


def is_vm_gen1() -> bool:
    """Determine if VM is gen1 or gen2.

    Gen2 guests use UEFI while gen1 is legacy BIOS.
    """
    # Linux
    if os.path.exists("/sys/firmware/efi"):
        return False

    # BSD
    if os.path.exists("/dev/efi"):
        return False

    return True


def query_system_uuid() -> str:
    """Query system uuid in lower-case."""
    system_uuid = dmi.read_dmi_data("system-uuid")
    if system_uuid is None:
        raise RuntimeError("failed to read system-uuid")

    # Kernels older than 4.15 will have upper-case system uuid.
    system_uuid = system_uuid.lower()
    LOG.debug("Read product uuid: %s", system_uuid)
    return system_uuid


def query_vm_id() -> str:
    """Query VM ID from system."""
    system_uuid = query_system_uuid()
    return convert_system_uuid_to_vm_id(system_uuid)


class ChassisAssetTag(enum.Enum):
    AZURE_CLOUD = "7783-7084-3265-9085-8269-3286-77"

    @classmethod
    def query_system(cls) -> Optional["ChassisAssetTag"]:
        """Check platform environment to report if this datasource may run.

        :returns: ChassisAssetTag if matching tag found, else None.
        """
        asset_tag = dmi.read_dmi_data("chassis-asset-tag")
        try:
            tag = cls(asset_tag)
        except ValueError:
            report_diagnostic_event(
                "Non-Azure chassis asset tag: %r" % asset_tag,
                logger_func=LOG.debug,
            )
            return None

        report_diagnostic_event(
            "Azure chassis asset tag: %r (%s)" % (asset_tag, tag.name),
            logger_func=LOG.debug,
        )
        return tag
