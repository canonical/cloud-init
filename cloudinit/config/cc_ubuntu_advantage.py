# This file is part of cloud-init. See LICENSE file for license information.

"""ubuntu_advantage: Configure Ubuntu Advantage support services"""

import re
from logging import Logger
from textwrap import dedent
from typing import Optional
from urllib.parse import urlparse

from cloudinit import log as logging
from cloudinit import subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.settings import PER_INSTANCE

UA_URL = "https://ubuntu.com/advantage"

distros = ["ubuntu"]

meta: MetaSchema = {
    "id": "cc_ubuntu_advantage",
    "name": "Ubuntu Advantage",
    "title": "Configure Ubuntu Advantage support services",
    "description": dedent(
        """\
        Attach machine to an existing Ubuntu Advantage support contract and
        enable or disable support services such as Livepatch, ESM,
        FIPS and FIPS Updates. When attaching a machine to Ubuntu Advantage,
        one can also specify services to enable. When the 'enable'
        list is present, only named services will be activated. Whereas
        'enable' list is not present, any named service will supplement
        contract-default enabled services.

        In Ubuntu Pro instances, `token` will be ignored. `enable` and
        `enable_beta` will fully determine what services will be enabled,
        ignoring contract defaults.

        Note that when enabling FIPS or FIPS updates you will need to schedule
        a reboot to ensure the machine is running the FIPS-compliant kernel.
        See `Power State Change`_ for information on how to configure
        cloud-init to perform this reboot.
        """
    ),
    "distros": distros,
    "examples": [
        dedent(
            """\
        # Attach the machine to an Ubuntu Advantage support contract with a
        # UA contract token obtained from %s.
        ubuntu_advantage:
          token: <ua_contract_token>
    """
            % UA_URL
        ),
        dedent(
            """\
        # Attach the machine to an Ubuntu Advantage support contract enabling
        # only fips and esm services. Services will only be enabled if
        # the environment supports said service. Otherwise warnings will
        # be logged for incompatible services specified.
        ubuntu_advantage:
          token: <ua_contract_token>
          enable:
          - fips
          - esm
    """
        ),
        dedent(
            """\
        # Attach the machine to an Ubuntu Advantage support contract and enable
        # the FIPS service.  Perform a reboot once cloud-init has
        # completed.
        power_state:
          mode: reboot
        ubuntu_advantage:
          token: <ua_contract_token>
          enable:
          - fips
        """
        ),
        dedent(
            """\
        # Set a http(s) proxy before attaching the machine to an
        # Ubuntu Advantage support contract and enabling the FIPS service.
        ubuntu_advantage:
          token: <ua_contract_token>
          config:
            http_proxy: 'http://some-proxy:8088'
            https_proxy: 'https://some-proxy:8088'
            global_apt_https_proxy: 'http://some-global-apt-proxy:8088/'
            global_apt_http_proxy: 'https://some-global-apt-proxy:8088/'
            ua_apt_http_proxy: 'http://10.0.10.10:3128'
            ua_apt_https_proxy: 'https://10.0.10.10:3128'
          enable:
          - fips
        """
        ),
        dedent(
            """\
        # Do not enable any service in Ubuntu Pro instances.
        ubuntu_advantage:
          enable: []
          enable_beta: []
        """
        ),
        dedent(
            """\
        # Enable esm and beta realtime-kernel services in Ubuntu Pro instances.
        ubuntu_advantage:
          enable:
          - esm
          enable_beta:
          - realtime-kernel
        """
        ),
        dedent(
            """\
        # Disable auto-attach in Ubuntu Pro instances.
        ubuntu_advantage:
          features:
            disable_auto_attach: True
        """
        ),
    ],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": ["ubuntu_advantage", "ubuntu-advantage"],
}

__doc__ = get_meta_doc(meta)

LOG = logging.getLogger(__name__)
REDACTED = "REDACTED"


def supplemental_schema_validation(ua_config):
    """Validate user-provided ua:config option values.

    This function supplements flexible jsonschema validation with specific
    value checks to aid in triage of invalid user-provided configuration.

    @param ua_config: Dictionary of config value under 'ubuntu_advantage'.

    @raises: ValueError describing invalid values provided.
    """
    errors = []
    nl = "\n"
    for key, value in sorted(ua_config.items()):
        if key in (
            "http_proxy",
            "https_proxy",
            "global_apt_http_proxy",
            "global_apt_https_proxy",
            "ua_apt_http_proxy",
            "ua_apt_https_proxy",
        ):
            try:
                parsed_url = urlparse(value)
                if parsed_url.scheme not in ("http", "https"):
                    errors.append(
                        f"Expected URL scheme http/https for ua:config:{key}."
                        f" Found: {value}"
                    )
            except (AttributeError, ValueError):
                errors.append(
                    f"Expected a URL for ua:config:{key}. Found: {value}"
                )

    if errors:
        raise ValueError(
            f"Invalid ubuntu_advantage configuration:{nl}{nl.join(errors)}"
        )


def configure_ua(token=None, enable=None, config=None):
    """Call ua commandline client to attach or enable services."""
    error = None
    if not token:
        error = "ubuntu_advantage: token must be provided"
        LOG.error(error)
        raise RuntimeError(error)

    if enable is None:
        enable = []
    elif isinstance(enable, str):
        LOG.warning(
            "ubuntu_advantage: enable should be a list, not"
            " a string; treating as a single enable"
        )
        enable = [enable]
    elif not isinstance(enable, list):
        LOG.warning(
            "ubuntu_advantage: enable should be a list, not"
            " a %s; skipping enabling services",
            type(enable).__name__,
        )
        enable = []

    if config is None:
        config = dict()
    elif not isinstance(config, dict):
        LOG.warning(
            "ubuntu_advantage: config should be a dict, not"
            " a %s; skipping enabling config parameters",
            type(config).__name__,
        )
        config = dict()

    enable_errors = []

    # UA Config
    for key, value in sorted(config.items()):
        if value is None:
            LOG.debug("Unsetting UA config for %s", key)
            config_cmd = ["ua", "config", "unset", key]
        else:
            LOG.debug("Setting UA config %s=%s", key, value)
            if re.search(r"\s", value):
                key_value = f"{key}={re.escape(value)}"
            else:
                key_value = f"{key}={value}"
            config_cmd = ["ua", "config", "set", key_value]

        try:
            subp.subp(config_cmd)
        except subp.ProcessExecutionError as e:
            enable_errors.append((key, e))

    if enable_errors:
        for param, error in enable_errors:
            LOG.warning('Failure enabling "%s":\n%s', param, error)
        raise RuntimeError(
            "Failure enabling Ubuntu Advantage config(s): {}".format(
                ", ".join('"{}"'.format(param) for param, _ in enable_errors)
            )
        )

    if enable:
        attach_cmd = ["ua", "attach", "--no-auto-enable", token]
    else:
        attach_cmd = ["ua", "attach", token]
    redacted_cmd = attach_cmd[:-1] + [REDACTED]
    LOG.debug("Attaching to Ubuntu Advantage. %s", " ".join(redacted_cmd))
    try:
        # Allow `ua attach` to fail in already attached machines
        subp.subp(attach_cmd, rcs={0, 2}, logstring=redacted_cmd)
    except subp.ProcessExecutionError as e:
        error = str(e).replace(token, REDACTED)
        msg = f"Failure attaching Ubuntu Advantage:\n{error}"
        util.logexc(LOG, msg)
        raise RuntimeError(msg) from e

    enable_errors = []
    for service in enable:
        try:
            cmd = ["ua", "enable", "--assume-yes", service]
            subp.subp(cmd, capture=True)
        except subp.ProcessExecutionError as e:
            if re.search("is already enabled.", str(e)):
                LOG.debug('Service "%s" already enabled.', service)
            else:
                enable_errors.append((service, e))

    if enable_errors:
        for service, error in enable_errors:
            msg = 'Failure enabling "{service}":\n{error}'.format(
                service=service, error=str(error)
            )
            util.logexc(LOG, msg)

        raise RuntimeError(
            "Failure enabling Ubuntu Advantage service(s): {}".format(
                ", ".join(
                    '"{}"'.format(service) for service, _ in enable_errors
                )
            )
        )


def maybe_install_ua_tools(cloud: Cloud):
    """Install ubuntu-advantage-tools if not present."""
    if subp.which("ua"):
        return
    try:
        cloud.distro.update_package_sources()
    except Exception:
        util.logexc(LOG, "Package update failed")
        raise
    try:
        cloud.distro.install_packages(["ubuntu-advantage-tools"])
    except Exception:
        util.logexc(LOG, "Failed to install ubuntu-advantage-tools")
        raise


def _is_pro() -> bool:
    try:
        from uaclient.api.u.pro.attach.auto.should_auto_attach.v1 import (
            should_auto_attach,
        )
    except ImportError as ex:
        LOG.debug("Unable to import `uaclient`: %s", ex)
        return False
    try:
        result = should_auto_attach()
    except Exception as ex:
        LOG.debug("Error during `should_auto_attach`: %s", ex)
        LOG.warning(
            "Unable to determine if this is an Ubuntu Pro instance."
            " Fallback to normal UA attach."
        )
        return False
    return result.should_auto_attach


def _attach(ua_section: dict, config: Optional[dict] = None):
    token = ua_section.get("token")
    if not token:
        msg = "`ubuntu-advantage.token` required in non-Pro Ubuntu instances."
        LOG.error(msg)
        raise RuntimeError(msg)
    configure_ua(
        token=token,
        enable=ua_section.get("enable"),
        config=config,
    )


def _auto_attach(ua_section: dict):
    try:
        from uaclient.api.u.pro.attach.auto.full_auto_attach.v1 import (
            FullAutoAttachOptions,
            full_auto_attach,
        )
        from uaclient.exceptions import UserFacingError
    except ImportError as ex:
        msg = f"Unable to import `uaclient`: {ex}"
        LOG.error(msg)
        raise RuntimeError(msg) from ex

    options = FullAutoAttachOptions(
        enable=ua_section.get("enable"),
        enable_beta=ua_section.get("enable_beta"),
    )
    try:
        full_auto_attach(options=options)
    except UserFacingError as ex:
        msg = f"Error during `full_auto_attach`: {ex}"
        LOG.error(msg)
        raise RuntimeError(msg) from ex


def handle(
    name: str, cfg: Config, cloud: Cloud, log: Logger, args: list
) -> None:
    ua_section = None
    if "ubuntu-advantage" in cfg:
        LOG.warning(
            'Deprecated configuration key "ubuntu-advantage" provided.'
            ' Expected underscore delimited "ubuntu_advantage"; will'
            " attempt to continue."
        )
        ua_section = cfg["ubuntu-advantage"]
    if "ubuntu_advantage" in cfg:
        ua_section = cfg["ubuntu_advantage"]
    if ua_section is None:
        LOG.debug(
            "Skipping module named %s,"
            " no 'ubuntu_advantage' configuration found",
            name,
        )
        return
    if "commands" in ua_section:
        msg = (
            'Deprecated configuration "ubuntu-advantage: commands" provided.'
            ' Expected "token"'
        )
        LOG.error(msg)
        raise RuntimeError(msg)

    config = ua_section.get("config")
    if config is not None:
        supplemental_schema_validation(config)

    maybe_install_ua_tools(cloud)

    # ua-auto-attach.service had noop-ed as ua_section is not empty
    disable_auto_attach = bool(
        ua_section.get("features", {}).get("disable_auto_attach", False)
    )
    if not disable_auto_attach and _is_pro():
        _auto_attach(ua_section)
    elif not ua_section.keys() <= {"features"}:
        _attach(ua_section, config)


# vi: ts=4 expandtab
