# This file is part of cloud-init. See LICENSE file for license information.
import os
from collections import namedtuple
from typing import Optional

from cloudinit import log as logging
from cloudinit import subp
from cloudinit.util import is_container, is_FreeBSD

LOG = logging.getLogger(__name__)

# Path for DMI Data
DMI_SYS_PATH = "/sys/class/dmi/id"

KernelNames = namedtuple("KernelNames", ["linux", "freebsd"])
KernelNames.__new__.__defaults__ = (None, None)

# FreeBSD's kenv(1) and Linux /sys/class/dmi/id/* both use different names from
# dmidecode. The values are the same, and ultimately what we're interested in.
# These tools offer a "cheaper" way to access those values over dmidecode.
# This is our canonical translation table. If we add more tools on other
# platforms to find dmidecode's values, their keys need to be put in here.
DMIDECODE_TO_KERNEL = {
    "baseboard-asset-tag": KernelNames("board_asset_tag", "smbios.planar.tag"),
    "baseboard-manufacturer": KernelNames(
        "board_vendor", "smbios.planar.maker"
    ),
    "baseboard-product-name": KernelNames(
        "board_name", "smbios.planar.product"
    ),
    "baseboard-serial-number": KernelNames(
        "board_serial", "smbios.planar.serial"
    ),
    "baseboard-version": KernelNames("board_version", "smbios.planar.version"),
    "bios-release-date": KernelNames("bios_date", "smbios.bios.reldate"),
    "bios-vendor": KernelNames("bios_vendor", "smbios.bios.vendor"),
    "bios-version": KernelNames("bios_version", "smbios.bios.version"),
    "chassis-asset-tag": KernelNames(
        "chassis_asset_tag", "smbios.chassis.tag"
    ),
    "chassis-manufacturer": KernelNames(
        "chassis_vendor", "smbios.chassis.maker"
    ),
    "chassis-serial-number": KernelNames(
        "chassis_serial", "smbios.chassis.serial"
    ),
    "chassis-version": KernelNames(
        "chassis_version", "smbios.chassis.version"
    ),
    "system-manufacturer": KernelNames("sys_vendor", "smbios.system.maker"),
    "system-product-name": KernelNames(
        "product_name", "smbios.system.product"
    ),
    "system-serial-number": KernelNames(
        "product_serial", "smbios.system.serial"
    ),
    "system-uuid": KernelNames("product_uuid", "smbios.system.uuid"),
    "system-version": KernelNames("product_version", "smbios.system.version"),
}


def _read_dmi_syspath(key: str) -> Optional[str]:
    """
    Reads dmi data from /sys/class/dmi/id
    """
    kmap = DMIDECODE_TO_KERNEL.get(key)
    if kmap is None or kmap.linux is None:
        return None
    dmi_key_path = "{0}/{1}".format(DMI_SYS_PATH, kmap.linux)
    LOG.debug("querying dmi data %s", dmi_key_path)
    if not os.path.exists(dmi_key_path):
        LOG.debug("did not find %s", dmi_key_path)
        return None

    try:
        with open(dmi_key_path, "rb") as fp:
            key_data = fp.read()
    except PermissionError:
        LOG.debug("Could not read %s", dmi_key_path)
        return None

    # uninitialized dmi values show as all \xff and /sys appends a '\n'.
    # in that event, return empty string.
    if key_data == b"\xff" * (len(key_data) - 1) + b"\n":
        key_data = b""

    try:
        return key_data.decode("utf8").strip()
    except UnicodeDecodeError as e:
        LOG.error(
            "utf-8 decode of content (%s) in %s failed: %s",
            dmi_key_path,
            key_data,
            e,
        )

    return None


def _read_kenv(key: str) -> Optional[str]:
    """
    Reads dmi data from FreeBSD's kenv(1)
    """
    kmap = DMIDECODE_TO_KERNEL.get(key)
    if kmap is None or kmap.freebsd is None:
        return None

    LOG.debug("querying dmi data %s", kmap.freebsd)

    try:
        cmd = ["kenv", "-q", kmap.freebsd]
        (result, _err) = subp.subp(cmd)
        result = result.strip()
        LOG.debug("kenv returned '%s' for '%s'", result, kmap.freebsd)
        return result
    except subp.ProcessExecutionError as e:
        LOG.debug("failed kenv cmd: %s\n%s", cmd, e)

    return None


def _call_dmidecode(key: str, dmidecode_path: str) -> Optional[str]:
    """
    Calls out to dmidecode to get the data out. This is mostly for supporting
    OS's without /sys/class/dmi/id support.
    """
    try:
        cmd = [dmidecode_path, "--string", key]
        (result, _err) = subp.subp(cmd)
        result = result.strip()
        LOG.debug("dmidecode returned '%s' for '%s'", result, key)
        if result.replace(".", "") == "":
            return ""
        return result
    except subp.ProcessExecutionError as e:
        LOG.debug("failed dmidecode cmd: %s\n%s", cmd, e)
        return None


def read_dmi_data(key: str) -> Optional[str]:
    """
    Wrapper for reading DMI data.

    If running in a container return None.  This is because DMI data is
    assumed to be not useful in a container as it does not represent the
    container but rather the host.

    This will do the following (returning the first that produces a
    result):
        1) Use a mapping to translate `key` from dmidecode naming to
           sysfs naming and look in /sys/class/dmi/... for a value.
        2) Use `key` as a sysfs key directly and look in /sys/class/dmi/...
        3) Fall-back to passing `key` to `dmidecode --string`.

    If all of the above fail to find a value, None will be returned.
    """

    if is_container():
        return None

    if is_FreeBSD():
        return _read_kenv(key)

    syspath_value = _read_dmi_syspath(key)
    if syspath_value is not None:
        return syspath_value

    def is_x86(arch):
        return arch == "x86_64" or (arch[0] == "i" and arch[2:] == "86")

    # running dmidecode can be problematic on some arches (LP: #1243287)
    uname_arch = os.uname()[4]
    if not (is_x86(uname_arch) or uname_arch in ("aarch64", "amd64")):
        LOG.debug("dmidata is not supported on %s", uname_arch)
        return None

    dmidecode_path = subp.which("dmidecode")
    if dmidecode_path:
        return _call_dmidecode(key, dmidecode_path)

    LOG.debug("did not find either path %s or dmidecode command", DMI_SYS_PATH)
    return None


# vi: ts=4 expandtab
