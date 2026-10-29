# This file is part of cloud-init. See LICENSE file for license information.

"""Installation paths configured by the build system."""

try:
    from cloudinit.meson_paths import LIB_EXEC_DIR  # type: ignore
except ImportError:
    # Source checkouts and older packages have no generated path metadata.
    LIB_EXEC_DIR = None


def get_lib_exec_dir(default: str) -> str:
    """Return the configured helper directory or the legacy default."""
    return LIB_EXEC_DIR if LIB_EXEC_DIR is not None else default
