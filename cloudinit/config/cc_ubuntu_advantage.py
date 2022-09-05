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

# TODO move following import to a non-global scope
from uaclient.api.api import call_api
from uaclient.config import UAConfig
from uaclient import AutoAttachWithShortRetryOptions
from uaclient.api.u.pro.detect.should_auto_attach.v1 import should_auto_attach_on_machine

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


class NotAProInstance(Exception):
    pass


class RetryError(Exception):
    pass


def auto_attach_short(*args, **kwargs):
    """
    TODO
    - Doc
    - Args
    - Integrate UA function.
    - Raise NotProInstance or RetryError depending on the underlying problem
    """
    raise NotImplementedError()


def auto_attach_long(*args, **kwargs):
    """
    TODO
    - Doc
    - Args
    - Integrate UA function.
    """
    raise NotImplementedError()


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
    is_pro_cfg = not disable_auto_attach

    ua_config: Optional[UAConfig] = None
    if config is not None:
        ua_config = UAConfig(cfg={"ua_config": config})

    is_pro = should_auto_attach_on_machine(cfg=ua_config).should_auto_attach
    if is_pro_cfg and is_pro:
        short_retry_kwargs = {}

        enable = ua_section.get("enable")
        if enable is not None:
            short_retry_kwargs["enable"] = enable

        enable_beta = ua_section.get("enable_beta")
        if enable_beta is not None:
            short_retry_kwargs["enable_beta"] = enable_beta

        options = AutoAttachWithShortRetryOptions(**short_retry_kwargs)

        try:
            successful = call_api(
                "u.pro.auto_attach.with_short_retry.v1",
                options=options,
                cfg=ua_config,
            ).successful
        except Exception:
            pass  # TODO log exceptions
        else:
            if not successful:
                LOG.warning(
                    "Ubuntu Advantage will try to auto-attach as Pro instance"
                    " with a long retry strategy."
                    " (This could take days or more)"
                )
    else:
        # Fallback to normal attach
        token = ua_section.get("token")
        if not token:
            msg = (
                "`ubuntu-advantage.token` required in non-Pro Ubuntu"
                " instances."
            )
            LOG.error(msg)
            raise RuntimeError(msg)
        configure_ua(
            token=token,
            enable=ua_section.get("enable"),
            config=config,
        )


# vi: ts=4 expandtab
