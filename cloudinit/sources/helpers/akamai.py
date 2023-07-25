import re
from typing import Any, Dict, Optional, Union

from cloudinit import dmi

# dmi data can override
DMI_OVERRIDE_MAP = {
    "als": "allow_local_stage",
    "ais": "allow_init_stage",
    "dhcp": "allow_dhcp",
    "v4": "allow_ipv4",
    "v6": "allow_ipv6",
    "pmp": "preferred_mac_prefixes",
}


def get_dmi_config() -> Dict[str, Union[bool, str]]:
    """
    Parses flags from dmi data and updates self.ds_cfg accordingly
    """
    dmi_flags = dmi.read_dmi_data("baseboard-serial-number")
    ret: Dict[str, Any] = {}

    if not dmi_flags:
        return ret

    # parse the value into individual flags, then set them in our config
    # based on the short name lookup table
    for key, value, _ in re.findall(r"([a-z0-9]+)=(.*?)(;|$)", dmi_flags):
        if key in DMI_OVERRIDE_MAP:
            if value in "01":
                value = bool(int(value))
            elif key == "pmp":
                value = value.split(",")
            ret[DMI_OVERRIDE_MAP[key]] = value

    return ret


def is_on_akamai() -> bool:
    """
    Reads the BIOS vendor from dmi data to determine if we are running in the
    Akamai Connected Cloud.
    """
    vendor = dmi.read_dmi_data("system-manufacturer")
    return vendor in ("Linode", "Akamai")


def get_local_instance_id() -> Optional[str]:
    """
    Returns the instance id read from dmi data without requiring the metadata
    service to be reachable
    """
    return dmi.read_dmi_data("system-serial-number")
