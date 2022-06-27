# This file is part of cloud-init. See LICENSE file for license information.
"""Wireguard"""

from logging import Logger

from cloudinit.cloud import Cloud
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.distros import ALL_DISTROS
from cloudinit.settings import PER_INSTANCE

import subprocess
import time
import re

MODULE_DESCRIPTION = """\
Module to set up Wireguard conneciton
"""

meta: MetaSchema = {
    "id": "cc_wireguard",
    "name": "Wireguard",
    "title": "Module to configure Wireguard tunnel",
    "description": MODULE_DESCRIPTION,
    "distros": [ALL_DISTROS],
    "frequency": PER_INSTANCE,
    "examples": [
        "example_key: example_value",
        "example_other_key: ['value', 2]",
    ],
}

__doc__ = get_meta_doc(meta)

def writeconfig(wg_section:dict, log: Logger) -> bool:
    log.debug(f"Writing wg config files")
    for i in wg_section['interfaces']:
        log.debug("Configuring interface {}".format(str(i['name'])))
        try:
            with open(i['config_path'], 'w', encoding="utf-8") as wgconfig:
                wgconfig.write("[Interface]\n")
                wgconfig.write("PrivateKey = {}\n".format(wg_section['wg_private_key']))
                wgconfig.write("Address = {}\n".format(i['interface']['address']))
                wgconfig.write("Table = off\n")
                wgconfig.write("[Peer]\n")
                wgconfig.write("PublicKey = {}\n".format(i['peer']['public_key']))
                wgconfig.write("Endpoint = {}:{}\n".format(i['peer']['endpoint'],i['peer']['port']))
                wgconfig.write("AllowedIPs = {}\n".format(i['peer']['allowedips']))
                wgconfig.write("PersistentKeepalive = 25\n")
        except Exception as e:
            return False
    return True

def enablewg(wg_section:dict, log: Logger) -> bool:
    log.debug(f"Enable wg interface(s)")
    for i in wg_section['interfaces']:
        try:
            log.debug("Running: systemctl enable wg-quick@{}".format(str(i['name'])))
            subprocess.call("systemctl enable wg-quick@{}".format(str(i['name'])), shell=True)
            subprocess.call("systemctl start wg-quick@{}".format(str(i['name'])), shell=True)
        except Exception as e:
            return False
    return True

def wait(log: Logger) -> bool:
    log.debug("Waiting for Wireguard Hub connection")
    while True:
        if re.match(r'wg\d\s\S+\s+\d{10,}',subprocess.check_output("wg show all latest-handshakes",shell=True).decode()):
            break
        time.sleep(10)
    log.debug("Connection to Wireguard Hub ok")
    return True

def handle(name: str, cfg: dict, cloud: Cloud, log: Logger, args: list):
    log.debug(f"Starting clound-init module {name}")
    wg_section = None

    if "wireguard" in cfg:
        log.debug(f"Found wireguard section in config")
        wg_section = cfg["wireguard"]

    if wg_section is None:
        log.debug(
            "Skipping module named %s,"
            " no 'wireguard' configuration found",
            name,
        )
        raise RuntimeError("Skipping wireguard module")

    #write wg config files
    state = writeconfig(wg_section, log)
    if not state:
        log.error("Writing WG configuration file failed")
        raise RuntimeError("Writing WG configuration file failed")

    #enable wg interfaces
    state = enablewg(wg_section, log)
    if not state:
        log.error("Enable wg interface(s) failed")
        raise RuntimeError("Enable wg interface(s) failed")

    #wait for connection
    if wg_section['wait_for_connection']:
        log.debug("Waiting for connection")
        state = wait(log)
        if not state:
            log.error("Error during waiting ... ")
            raise RuntimeError("Error during waiting ...")
    else:
        log.debug("Not waiting for connection")