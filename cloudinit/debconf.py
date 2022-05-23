# Copyright (C) 2022 Canonical Ltd.
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Cloud-init debconf interface"""

try:
    from debconf import DebconfCommunicator as _DebconfCommunicator

    HAS_DEBCONF = True
    DebconfCommunicator = _DebconfCommunicator
except ImportError:
    HAS_DEBCONF = False
    DebconfCommunicator = None


__all__ = ["DebconfCommunicator", "HAS_DEBCONF"]
