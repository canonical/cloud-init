# Author: Fabian Lichtenegger-Lukas <fabian.lichtenegger-lukas@nts.eu>
# Author: Josef Tschiggerl <josef.tschiggerl@nts.eu>
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
          config_path: /etc/wireguard/wg1.conf
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

REQUIRED_WG_INT_KEYS = frozenset(["name", "config_path", "content"])


def supplemental_schema_validation(wg_int: dict):
    """Validate user-provided wg:interfaces option values.

    This function supplements flexible jsonschema validation with specific
    value checks to aid in triage of invalid user-provided configuration.

    @param wg_int: Dict of configuration value under 'wg:interfaces'.

    @raises: ValueError describing invalid values provided.
    """
    errors = []
    missing = REQUIRED_WG_INT_KEYS.difference(set(wg_int.keys()))
    if missing:
        keys = ", ".join(sorted(missing))
        errors.append(f"Missing required wg:interfaces keys: {keys}")

    for key, value in sorted(wg_int.items()):
        if key == "name" or key == "config_path" or key == "content":
            if not isinstance(value, str):
                errors.append(
                    f"Expected a str for wg:interfaces:{key}. Found: {value}"
                )

    if errors:
        raise ValueError(
            f"Invalid wireguard interface configuration:{NL}{NL.join(errors)}"
        )


def write_config(wg_int: dict):
    """Writing user-provided configuration into Wirguard
    interface configuration file.

    @param wg_int: Dict of configuration value under 'wg:interfaces'.

    @raises: RuntimeError for issues writing of configuration file.
    """
    LOG.debug("Configuring Wireguard interface %s", wg_int["name"])
    try:
        with open(wg_int["config_path"], "w", encoding="utf-8") as wgconfig:
            wgconfig.write(wg_int["content"])
    except Exception as e:
        raise RuntimeError(
            f"Failure writing Wireguard configuration file:" f"{e}"
        ) from e


def enable_wg(wg_int: dict):
    """Enable and start Wireguard interface

    @param wg_int: Dict of configuration value under 'wg:interfaces'.

    @raises: RuntimeError for issues enabling WG interface.
    """
    try:
        LOG.debug("Running: systemctl enable wg-quick@%s", {wg_int["name"]})
        subp.subp(
            f'systemctl enable wg-quick@{wg_int["name"]}',
            capture=True,
            shell=True,
        )
        subp.subp(
            f'systemctl start wg-quick@{wg_int["name"]}',
            capture=True,
            shell=True,
        )
    except Exception as e:
        raise RuntimeError(
            f"Failed enabling Wireguard interface(s):" f"{e}"
        ) from e


def readinessprobe_command_validation(wg_section: dict):
    """Basic validation of user-provided probes

    @param wg_section: Dict of readinessprobe probe(s) under 'wireguard'.

    @raises: ValueError of wrong datatype provided for probes.
    """
    errors = []
    pos = 0
    for c in wg_section["readinessprobe"]:
        if not isinstance(c, str):
            errors.append(
                f"Expected a string for readinessprobe at {pos}. Found {c}"
            )
            pos += 1

    if errors:
        raise ValueError(
            f"Invalid readinessProbe commands:{NL}{NL.join(errors)}"
        )


def readinessprobe(wg_section: dict):
    """Execute provided readiness probe(s)

    @param wg_section: Dict of readinessprobe probe(s) under 'wireguard'.

    @raises: ProcessExecutionError for issues during execution of probes.
    """
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


def maybe_install_wireguard_tools(cloud: Cloud):
    """Install wireguard-tools if not present."""
    if subp.which("wg"):
        return
    try:
        cloud.distro.update_package_sources()
    except Exception:
        util.logexc(LOG, "Package update failed")
        raise
    try:
        cloud.distro.install_packages(["wireguard-tools"])
    except Exception:
        util.logexc(LOG, "Failed to install wireguard-tools")
        raise


def handle(name: str, cfg: dict, cloud: Cloud, log, args: list):
    wg_section = None

    if "wireguard" in cfg:
        LOG.debug("Found Wireguard section in config")
        wg_section = cfg["wireguard"]

    if wg_section is None:
        LOG.debug(
            "Skipping module named %s," " no 'wireguard' configuration found",
            name,
        )
        return

    # install wireguard tools, enable kernel module
    maybe_install_wireguard_tools(cloud)
    try:
        subp.subp("modprobe wireguard", capture=True, shell=True)
    except subp.ProcessExecutionError as e:
        util.logexc(LOG, f"Could not load wireguard module: {e}")

    for wg_int in wg_section["interfaces"]:
        # check schema
        supplemental_schema_validation(wg_int)

        # write wg config files
        write_config(wg_int)

        # enable wg interfaces
        enable_wg(wg_int)

    # parse and run readinessprobe parameters
    if (
        "readinessprobe" in wg_section
        and wg_section["readinessprobe"] is not None
    ):
        readinessprobe_command_validation(wg_section)
        readinessprobe(wg_section)
    else:
        LOG.debug("Skipping readinessprobe - no checks defined")
