# This file is part of cloud-init. See LICENSE file for license information.

"""Wireguard"""
from textwrap import dedent

from cloudinit import log as logging
from cloudinit import subp, util
from cloudinit.cloud import Cloud
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.settings import PER_INSTANCE

MODULE_DESCRIPTION = dedent(
    """\
Module to set up Wireguard connection.
Including installation and configuration of WG interfaces.
In addition certain readinessprobes can be provided.
"""
)

NL = "\n"

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
    # Configure one or more WG interfaces and provide optinal readinessprobes
    wireguard:
      interfaces:
        - name: wg0
          config_path: /etc/wireguard/wg0.conf
          content: |
            [Interface]
            PrivateKey = <private_key>
            Address = <address>
            [Peer]
            PublicKey = <public_key>
            Endpoint = <endpoint_ip>:<endpoint_ip_port>
            AllowedIPs = <allowedip1>, <allowedip2>, ...
        - name: wg1
          config_path: /opt/etc/wireguard/wg1.conf
          content: |
            [Interface]
            PrivateKey = <private_key>
            Address = <address>
            [Peer]
            PublicKey = <public_key>
            Endpoint = <endpoint_ip>:<endpoint_ip_port>
            AllowedIPs = <allowedip1>
      readinessprobe:
        - 'systemctl restart service'
        - 'curl https://webhook.endpoint/example'
        - 'nc -zv some-service-fqdn 443'
    """
        ),
    ],
}

__doc__ = get_meta_doc(meta)

LOG = logging.getLogger(__name__)


def writeconfig(wg_section: dict):
    for i in wg_section["interfaces"]:
        LOG.debug("Configuring Wireguard interface %s", i["name"])
        try:
            with open(i["config_path"], "w", encoding="utf-8") as wgconfig:
                wgconfig.write(i["content"])
        except Exception as e:
            raise RuntimeError(
                f"Failure writing Wireguard configuration file:" f"{e}"
            ) from e


def enablewg(wg_section: dict):
    for i in wg_section["interfaces"]:
        try:
            LOG.debug("Running: systemctl enable wg-quick@%s", {i["name"]})
            subp.subp(
                f'systemctl enable wg-quick@{i["name"]}',
                capture=True,
                shell=True,
            )
            subp.subp(
                f'systemctl start wg-quick@{i["name"]}',
                capture=True,
                shell=True,
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed enabling Wireguard interface(s):" f"{e}"
            ) from e


def readinessprobe_command_validation(wg_section: dict):
    errors = []
    pos = 0
    for c in wg_section[readinessprobe]:
        if not isinstance(c, str):
            errors.append(
                f"Expected a string for readinessprobe at {pos}. Found {c}"
            )
            pos += 1

    if errors:
        raise ValueError(
            f"Invalid readinessProbe commands:{NL}{NL.join(errors)}"
        )


def readinessprobe(wg_section: dict, cloud: Cloud):
    errors = []
    for c in wg_section["readinessprobe"]:
        try:
            LOG.debug("Running readinessprobe: '%s'", str(c))
            subp.subp(c, capture=True, shell=True)
        except subp.ProcessExecutionError as e:
            errors.append(f"{c}: {e}")

    if errors:
        raise RuntimeError(
            f"Failed running readinessprobe command:{NL}{NL.join(errors)}"
        )


def handle(name: str, cfg: dict, cloud: Cloud, args: list):
    LOG.debug("Starting clound-init module %s", name)
    wg_section = None

    if "wireguard" in cfg:
        LOG.debug("Found Wireguard section in config")
        wg_section = cfg["wireguard"]

    if wg_section is None:
        LOG.debug(
            "Skipping module named %s," " no 'wireguard' configuration found",
            name,
        )
        raise RuntimeError("Skipping Wireguard module")

    # install wireguard tools, enable kernel module
    cloud.distro.install_packages(("wireguard-tools",))
    subp.subp("modprobe wireguard", capture=True, shell=True)

    try:
        # write wg config files
        writeconfig(wg_section)

        # enable wg interfaces
        enablewg(wg_section)

        # parse and run readinessprobe paremeters
        if (
            "readinessprobe" in wg_section
            and wg_section["readinessprobe"] is not None
        ):
            readinessprobe_command_validation(wg_section)
            readinessprobe(wg_section, cloud)
        else:
            LOG.debug("Skipping readinessprobe - no checks defined")
    except RuntimeError as e:
        util.logexc(LOG, e)
