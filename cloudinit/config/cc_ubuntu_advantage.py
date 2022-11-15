# This file is part of cloud-init. See LICENSE file for license information.

"""ubuntu_advantage: Configure Ubuntu Advantage support services"""

import json
import re
from logging import Logger
from textwrap import dedent
from typing import Any, List
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
        if the 'enable' list is not present, the contract's default
        services will be enabled.

        On Pro instances, when ``ubuntu_advantage`` config is provided to
        cloud-init, Pro's auto-attach feature will be disabled and cloud-init
        will perform the Pro auto-attach ignoring the ``token`` key.
        The ``enable`` and ``enable_beta`` values will strictly determine what
        services will be enabled, ignoring contract defaults.

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
            global_apt_https_proxy: 'https://some-global-apt-proxy:8088/'
            global_apt_http_proxy: 'http://some-global-apt-proxy:8088/'
            ua_apt_http_proxy: 'http://10.0.10.10:3128'
            ua_apt_https_proxy: 'https://10.0.10.10:3128'
          enable:
          - fips
        """
        ),
        dedent(
            """\
        # On Ubuntu PRO instances, auto-attach but enable no PRO services.
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
ERROR_MSG_SHOULD_AUTO_ATTACH = (
    "Unable to determine if this is an Ubuntu Pro instance."
    " Fallback to normal UA attach."
)
KNOWN_UA_CONFIG_PROPS = (
    "http_proxy",
    "https_proxy",
    "global_apt_http_proxy",
    "global_apt_https_proxy",
    "ua_apt_http_proxy",
    "ua_apt_https_proxy",
)


def validate_schema_features(ua_section: dict):
    if "features" not in ua_section:
        return

    # Validate ubuntu_advantage.features type
    features = ua_section["features"]
    if not isinstance(features, dict):
        msg = (
            f"'ubuntu_advantage.features' should be a dict, not a"
            f" {type(features).__name__}"
        )
        LOG.error(msg)
        raise RuntimeError(msg)

    # Validate ubuntu_advantage.features.disable_auto_attach
    if "disable_auto_attach" not in features:
        return
    disable_auto_attach = features["disable_auto_attach"]
    if not isinstance(disable_auto_attach, bool):
        msg = (
            f"'ubuntu_advantage.features.disable_auto_attach' should be a bool"
            f", not a {type(disable_auto_attach).__name__}"
        )
        LOG.error(msg)
        raise RuntimeError(msg)


def supplemental_schema_validation(ua_config: dict):
    """Validate user-provided ua:config option values.

    This function supplements flexible jsonschema validation with specific
    value checks to aid in triage of invalid user-provided configuration.

    Note: It does not log/raise config values as they could be urls containing
    sensitive auth info.

    @param ua_config: Dictionary of config value under 'ubuntu_advantage'.

    @raises: ValueError describing invalid values provided.
    """
    errors = []
    for key, value in sorted(ua_config.items()):
        if key not in KNOWN_UA_CONFIG_PROPS:
            LOG.warning(
                "Not validating unknown ubuntu_advantage.config.%s property",
                key,
            )
            continue
        elif value is None:
            # key will be unset. No extra validation needed.
            continue
        try:
            parsed_url = urlparse(value)
            if parsed_url.scheme not in ("http", "https"):
                errors.append(
                    f"Expected URL scheme http/https for ua:config:{key}"
                )
        except (AttributeError, ValueError):
            errors.append(f"Expected a URL for ua:config:{key}")

    if errors:
        raise ValueError(
            "Invalid ubuntu_advantage configuration:\n{}".format(
                "\n".join(errors)
            )
        )


def set_ua_config(ua_config: Any = None):
    if ua_config is None:
        return
    if not isinstance(ua_config, dict):
        raise RuntimeError(
            f"ubuntu_advantage: config should be a dict, not"
            f" a {type(ua_config).__name__};"
            " skipping enabling config parameters"
        )
    supplemental_schema_validation(ua_config)

    enable_errors = []
    for key, value in sorted(ua_config.items()):
        redacted_key_value = None
        subp_kwargs: dict = {}
        if value is None:
            LOG.debug("Disabling UA config for %s", key)
            config_cmd = ["ua", "config", "unset", key]
        else:
            redacted_key_value = f"{key}=REDACTED"
            LOG.debug("Enabling UA config %s", redacted_key_value)
            if re.search(r"\s", value):
                key_value = f"{key}={re.escape(value)}"
            else:
                key_value = f"{key}={value}"
            config_cmd = ["ua", "config", "set", key_value]
            subp_kwargs = {"logstring": config_cmd[:-1] + [redacted_key_value]}
        try:
            subp.subp(config_cmd, **subp_kwargs)
        except subp.ProcessExecutionError as e:
            err_msg = str(e)
            if redacted_key_value is not None:
                err_msg = err_msg.replace(value, REDACTED)
            enable_errors.append((key, err_msg))
    if enable_errors:
        for param, error in enable_errors:
            LOG.warning('Failure enabling/disabling "%s":\n%s', param, error)
        raise RuntimeError(
            "Failure enabling/disabling Ubuntu Advantage config(s): {}".format(
                ", ".join('"{}"'.format(param) for param, _ in enable_errors)
            )
        )


def configure_ua(token, enable=None):
    """Call ua commandline client to attach and/or enable services."""
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

    # Perform attach
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
        err = str(e).replace(token, REDACTED)
        msg = f"Failure attaching Ubuntu Advantage:\n{err}"
        util.logexc(LOG, msg)
        raise RuntimeError(msg) from e

    # Enable services
    if not enable:
        return
    cmd = ["ua", "enable", "--assume-yes", "--format", "json", "--"] + enable
    try:
        enable_stdout, _ = subp.subp(cmd, capture=True, rcs={0, 1})
    except subp.ProcessExecutionError as e:
        raise RuntimeError(
            "Error while enabling service(s): " + ", ".join(enable)
        ) from e

    try:
        enable_resp = json.loads(enable_stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"UA response was not json: {enable_stdout}") from e

    # At this point we were able to load the json response from UA. This
    # response contains a list of errors under the key 'errors'. E.g.
    #
    #   {
    #      "errors": [
    #        {
    #           "message": "UA Apps: ESM is already enabled ...",
    #           "message_code": "service-already-enabled",
    #           "service": "esm-apps",
    #           "type": "service"
    #        },
    #        {
    #           "message": "Cannot enable unknown service 'asdf' ...",
    #           "message_code": "invalid-service-or-failure",
    #           "service": null,
    #           "type": "system"
    #        }
    #      ]
    #   }
    #
    # From our pov there are two type of errors, service and non-service
    # related. We can distinguish them by checking if `service` is non-null
    # or null respectively.

    # pylint: disable=import-error
    from uaclient.messages import ALREADY_ENABLED

    # pylint: enable=import-error

    UA_MC_ALREADY_ENABLED = ALREADY_ENABLED.name

    enable_errors: List[dict] = []
    for err in enable_resp.get("errors", []):
        if err["message_code"] == UA_MC_ALREADY_ENABLED:
            LOG.debug("Service `%s` already enabled.", err["service"])
            continue
        enable_errors.append(err)

    if enable_errors:
        error_services: List[str] = []
        for err in enable_errors:
            service = err.get("service")
            if service is not None:
                error_services.append(service)
                msg = f'Failure enabling `{service}`: {err["message"]}'
            else:
                msg = f'Failure of type `{err["type"]}`: {err["message"]}'
            util.logexc(LOG, msg)

        raise RuntimeError(
            "Failure enabling Ubuntu Advantage service(s): "
            + ", ".join(error_services)
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


def _should_auto_attach(ua_section: dict) -> bool:
    disable_auto_attach = bool(
        ua_section.get("features", {}).get("disable_auto_attach", False)
    )
    if disable_auto_attach:
        return False

    # pylint: disable=import-error
    from uaclient.api.exceptions import UserFacingError
    from uaclient.api.u.pro.attach.auto.should_auto_attach.v1 import (
        should_auto_attach,
    )

    # pylint: enable=import-error

    try:
        result = should_auto_attach()
    except UserFacingError as ex:
        LOG.debug("Error during `should_auto_attach`: %s", ex)
        LOG.warning(ERROR_MSG_SHOULD_AUTO_ATTACH)
        return False
    return result.should_auto_attach


def _attach(ua_section: dict):
    token = ua_section.get("token")
    if not token:
        msg = "`ubuntu-advantage.token` required in non-Pro Ubuntu instances."
        LOG.error(msg)
        raise RuntimeError(msg)
    enable_beta = ua_section.get("enable_beta")
    if enable_beta:
        LOG.debug(
            "Ignoring `ubuntu-advantage.enable_beta` services in UA attach:"
            " %s",
            ", ".join(enable_beta),
        )
    configure_ua(token=token, enable=ua_section.get("enable"))


def _auto_attach(ua_section: dict):

    # pylint: disable=import-error
    from uaclient.api.exceptions import AlreadyAttachedError, UserFacingError
    from uaclient.api.u.pro.attach.auto.full_auto_attach.v1 import (
        FullAutoAttachOptions,
        full_auto_attach,
    )

    # pylint: enable=import-error

    enable = ua_section.get("enable")
    enable_beta = ua_section.get("enable_beta")
    options = FullAutoAttachOptions(
        enable=enable,
        enable_beta=enable_beta,
    )
    try:
        full_auto_attach(options=options)
    except AlreadyAttachedError:
        if enable_beta is not None or enable is not None:
            # Only warn if the user defined some service to enable/disable.
            LOG.warning(
                "The instance is already attached to Pro. Leaving enabled"
                " services untouched. Ignoring config directives"
                " ubuntu_advantage: enable and enable_beta"
            )
    except UserFacingError as ex:
        msg = f"Error during `full_auto_attach`: {ex.msg}"
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
    elif not isinstance(ua_section, dict):
        msg = (
            f"'ubuntu_advantage' should be a dict, not a"
            f" {type(ua_section).__name__}"
        )
        LOG.error(msg)
        raise RuntimeError(msg)
    if "commands" in ua_section:
        msg = (
            'Deprecated configuration "ubuntu-advantage: commands" provided.'
            ' Expected "token"'
        )
        LOG.error(msg)
        raise RuntimeError(msg)

    maybe_install_ua_tools(cloud)
    set_ua_config(ua_section.get("config"))

    # ua-auto-attach.service had noop-ed as ua_section is not empty
    validate_schema_features(ua_section)
    if _should_auto_attach(ua_section):
        _auto_attach(ua_section)

    # If ua-auto-attach.service did noop, we did not auto-attach and more keys
    # than `features` are given under `ubuntu_advantage`, then try to attach.
    # This supports the cases:
    #
    # 1) Previous attach behavior on non-pro instances.
    # 2) Previous attach behavior on instances where ubuntu-advantage-tools
    #    is < v28.0 (UA apis for should_auto-attach and auto-attach are not
    #    available.
    # 3) The user wants to disable auto-attach and attach by giving:
    #    `{"ubuntu_advantage": "features": {"disable_auto_attach": True}}`
    elif not ua_section.keys() <= {"features"}:
        _attach(ua_section)


# vi: ts=4 expandtab
