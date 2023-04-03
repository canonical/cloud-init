# Copyright (C) 2023 Microsoft Corporation.
#
# This file is part of cloud-init. See LICENSE file for license information.

import logging
from typing import Optional

from cloudinit import dmi

LOG = logging.getLogger(__name__)


def query_vm_id() -> Optional[str]:
    system_uuid = dmi.read_dmi_data("system-uuid")
    LOG.debug("Read product uuid: %s", system_uuid)
    if not system_uuid:
        return None

    system_uuid = system_uuid.lower()
    parts = system_uuid.split("-")

    # Swap endianess for first three parts.
    for i in [0, 1, 2]:
        try:
            parts[i] = bytearray.fromhex(parts[i])[::-1].hex()
        except ValueError as error:
            LOG.error(
                "Failed to parse product uuid %r due to error: %r",
                system_uuid,
                error,
            )
            return None

    vm_id = "-".join(parts)
    LOG.debug("Azure VM identifier: %s", vm_id)
    return vm_id
