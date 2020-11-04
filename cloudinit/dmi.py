# This file is part of cloud-init. See LICENSE file for license information.
from cloudinit import log as logging
from cloudinit import subp
from cloudinit.util import is_container

import os

LOG = logging.getLogger(__name__)

# Path for DMI Data
DMI_SYS_PATH = "/sys/class/dmi/id"

# dmidecode and /sys/class/dmi/id/* use different names for the same value,
# this allows us to refer to them by one canonical name
DMIDECODE_TO_DMI_SYS_MAPPING = {
    'baseboard-asset-tag': 'board_asset_tag',
    'baseboard-manufacturer': 'board_vendor',
    'baseboard-product-name': 'board_name',
    'baseboard-serial-number': 'board_serial',
    'baseboard-version': 'board_version',
    'bios-release-date': 'bios_date',
    'bios-vendor': 'bios_vendor',
    'bios-version': 'bios_version',
    'chassis-asset-tag': 'chassis_asset_tag',
    'chassis-manufacturer': 'chassis_vendor',
    'chassis-serial-number': 'chassis_serial',
    'chassis-version': 'chassis_version',
    'system-manufacturer': 'sys_vendor',
    'system-product-name': 'product_name',
    'system-serial-number': 'product_serial',
    'system-uuid': 'product_uuid',
    'system-version': 'product_version',
}


def _read_dmi_syspath(key):
    """
    Reads dmi data with from /sys/class/dmi/id
    """
    if key not in DMIDECODE_TO_DMI_SYS_MAPPING:
        return None
    mapped_key = DMIDECODE_TO_DMI_SYS_MAPPING[key]
    dmi_key_path = "{0}/{1}".format(DMI_SYS_PATH, mapped_key)

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
    if key_data == b'\xff' * (len(key_data) - 1) + b'\n':
        key_data = b""

    try:
        return key_data.decode('utf8').strip()
    except UnicodeDecodeError as e:
        LOG.error("utf-8 decode of content (%s) in %s failed: %s",
                  dmi_key_path, key_data, e)

    return None


def _call_dmidecode(key, dmidecode_path):
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
    except (IOError, OSError) as e:
        LOG.debug('failed dmidecode cmd: %s\n%s', cmd, e)
        return None


def read_dmi_data(key):
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

    syspath_value = _read_dmi_syspath(key)
    if syspath_value is not None:
        return syspath_value

    def is_x86(arch):
        return (arch == 'x86_64' or (arch[0] == 'i' and arch[2:] == '86'))

    # running dmidecode can be problematic on some arches (LP: #1243287)
    uname_arch = os.uname()[4]
    if not (is_x86(uname_arch) or uname_arch in ('aarch64', 'amd64')):
        LOG.debug("dmidata is not supported on %s", uname_arch)
        return None

    dmidecode_path = subp.which('dmidecode')
    if dmidecode_path:
        return _call_dmidecode(key, dmidecode_path)

    LOG.warning("did not find either path %s or dmidecode command",
                DMI_SYS_PATH)
    return None

# vi: ts=4 expandtab
