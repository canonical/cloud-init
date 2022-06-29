# This file is part of cloud-init. See LICENSE file for license information.
"""Wireguard"""
from logging import Logger
from textwrap import dedent

from cloudinit import subp
from cloudinit.cloud import Cloud
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.distros import ALL_DISTROS
from cloudinit.settings import PER_INSTANCE

MODULE_DESCRIPTION = """\
Module to set up Wireguard connection. Including installation and configuration of WG interfaces. In addition certain readinessprobes can be provided.
"""

meta: MetaSchema = {
    "id": "cc_wireguard",
    "name": "Wireguard",
    "title": "Module to configure Wireguard tunnel",
    "description": MODULE_DESCRIPTION,
    "distros": ["ubuntu"],
    "frequency": PER_INSTANCE,
    "examples": [
        dedent(
            """\
    # Configure one or more Wireguard interfaces and provide optinal readinessprobes
    wireguard:
    interfaces:
        - name: <interface_name_wg0>
        config_path: <path_to_interface_configuration_file_wg0>
        content: |
            [Interface]
            PrivateKey = <private_key>
            Address = <address>
            [Peer]
            PublicKey = <public_key>
            Endpoint = <endpoint_ip>:<endpoint_ip_port>
            AllowedIPs = <allowedips>
        - name: <interface_name_wg1>
        config_path:  <path_to_interface_configuration_file_wg1>
        content: |
            [Interface]
            PrivateKey = <private_key>
            Address = <address>
            [Peer]
            PublicKey = <public_key>
            Endpoint = <endpoint_ip>:<endpoint_ip_port>
            AllowedIPs = <allowedips>
    readinessprobe:
        - 'service example restart'
        - 'curl https://webhook.endpoint/example'
    """
        ),
    ],
}

__doc__ = get_meta_doc(meta)


def writeconfig(wg_section: dict, log: Logger) -> bool:
    for i in wg_section["interfaces"]:
        log.debug("Configuring Wireguard interface {}".format(str(i["name"])))
        try:
            with open(i["config_path"], "w", encoding="utf-8") as wgconfig:
                wgconfig.write(i["content"])
        except Exception as e:
            return False
    return True


def enablewg(wg_section: dict, log: Logger) -> bool:
    for i in wg_section["interfaces"]:
        try:
            log.debug(
                "Running: systemctl enable wg-quick@{}".format(str(i["name"]))
            )
            subp.subp(
                "systemctl enable wg-quick@{}".format(str(i["name"])),
                capture=True,
                shell=True,
            )
            subp.subp(
                "systemctl start wg-quick@{}".format(str(i["name"])),
                capture=True,
                shell=True,
            )
        except Exception as e:
            return False
    return True


def readinessprobe(wg_section: dict, log: Logger, cloud: Cloud) -> bool:
    for c in wg_section["readinessprobe"]:
        if isinstance(c, str):
            log.debug("Running readinessprobe: '{}'".format(str(c)))
            subp.subp(c, capture=True, shell=True)
    return True


def handle(name: str, cfg: dict, cloud: Cloud, log: Logger, args: list):
    log.debug(f"Starting clound-init module {name}")
    wg_section = None

    if "wireguard" in cfg:
        log.debug("Found Wireguard section in config")
        wg_section = cfg["wireguard"]

    if wg_section is None:
        log.debug(
            "Skipping module named %s," " no 'wireguard' configuration found",
            name,
        )
        raise RuntimeError("Skipping Wireguard module")

    # install wireguard tools, enable kernel module
    cloud.distro.install_packages(("wireguard-tools",))
    subp.subp("modprobe wireguard", capture=True, shell=True)

    # write wg config files
    state = writeconfig(wg_section, log)
    if not state:
        log.error("Writing Wireguard configuration file failed")
        raise RuntimeError("Writing Wireguard configuration file failed")

    # enable wg interfaces
    state = enablewg(wg_section, log)
    if not state:
        log.error("Enable Wireguard interface(s) failed")
        raise RuntimeError("Enable Wireguard interface(s) failed")

    # run readinessprobe probe, if any
    if (
        "readinessprobe" in wg_section
        and wg_section["readinessprobe"] is not None
    ):
        state = readinessprobe(wg_section, log, cloud)
        if not state:
            log.error("Error during readinessprobe")
            raise RuntimeError("Error during readinessprobe")
    else:
        log.debug("Skipping readinessprobe - no checks defined")
