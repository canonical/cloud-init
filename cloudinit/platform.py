# This file is part of cloud-init. See LICENSE file for license information.
import glob
import logging
import os
import re

from cloudinit.util import is_container

LOG = logging.getLogger(__name__)


def _is_secureboot_present() -> bool:
    """Return True if efivars SecureBoot variable appears present.

    This checks for any path matching /sys/firmware/efi/efivars/SecureBoot-*
    and handles missing paths safely.
    """
    try:
        paths = glob.glob("/sys/firmware/efi/efivars/SecureBoot-*")
    except Exception:
        LOG.debug("Error globbing efivars, assuming no SecureBoot")
        return False
    return len(paths) > 0


def _has_tpm2() -> bool:
    """Return True if a TPM device is present."""
    try:
        return os.path.exists("/dev/tpm0")
    except OSError:
        LOG.debug("Error probing TPM presence")
        return False


def _detect_virtualization() -> str:
    """Return virtualization type string or empty if not detected.

    Detect virtualization solely by looking for the `hypervisor` flag
    in `/proc/cpuinfo`. Return "hypervisor" when present, otherwise
    return empty string.
    """
    try:
        if os.path.exists("/proc/cpuinfo"):
            with open(
                "/proc/cpuinfo", "r", encoding="utf-8", errors="ignore"
            ) as f:
                data = f.read()
                if "hypervisor" in data:
                    return "hypervisor"
    except Exception:
        LOG.debug("Error reading /proc/cpuinfo for virtualization detection")

    return ""


def sub_platform_vars(src: str) -> str:
    """Replace __platform.<key>__ placeholders with detected values.

    Supported keys: `secureboot`, `tpm2`, `virtualized`.
    Missing values are replaced with empty string to match dmi semantics.
    """
    if "__" not in src:
        return src

    valid_keys = {"secureboot", "tpm2", "virtualized"}
    for match in re.findall(r"__platform\.([^_]+)__", src):
        if match not in valid_keys:
            LOG.warning(
                "Ignoring invalid __platform.%s__ in %s. Expected one of: %s.",
                match,
                src,
                valid_keys,
            )
            continue

        # container guard: do not leak host data from containers
        if is_container():
            val = ""
        else:
            if match == "secureboot":
                val = "true" if _is_secureboot_present() else ""
            elif match == "tpm2":
                val = "true" if _has_tpm2() else ""
            elif match == "virtualized":
                val = _detect_virtualization() or ""
            else:
                val = ""

        LOG.debug(
            "Replacing __platform.%s__ in '%s' with '%s'.", match, src, val
        )
        src = src.replace(f"__platform.{match}__", val)

    return src
