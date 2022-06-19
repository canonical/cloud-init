# This file is part of cloud-init. See LICENSE file for license information.

"""ubuntu_advantage: Configure Ubuntu Advantage support services"""

from textwrap import dedent

from cloudinit import log as logging
from cloudinit import subp, util
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
        one can also specify services to enable.  When the 'enable'
        list is present, any named service will supplement the contract-default
        enabled services.

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
            global_apt_http_proxy: 'https://some-global-a'pt-proxy:8088/'          
            ua_apt_http_proxy: 'http://10.0.10.10:3128'
            ua_apt_https_proxy: 'https://10.0.10.10:3128'
          enable:
          - fips
        """
        ),
    ],
    "frequency": PER_INSTANCE,
}

__doc__ = get_meta_doc(meta)

LOG = logging.getLogger(__name__)


def supplemental_schema_validation(ua_config):
    """Validate user-provided ua:config option values.

    This function supplements flexible jsonschema validation with specific
    value checks to aid in triage of invalid user-provided configuration.

    @param ua_config: Dictionary of config value under 'ubuntu_advantage'.

    @raises: ValueError describing invalid values provided.
    """
    errors = []
    for key, value in sorted(ua_config.items()):
        if key == "http_proxy":
            if not isinstance(value, str):
                errors.append(
                    f"Expected a url for ua:config:{key}. Found: {value}"
                )
        elif key == "https_proxy":
            if not isinstance(value, str):
                errors.append(
                    f"Expected a url for ua:config:{key}. Found: {value}"
                )
    if errors:
        raise ValueError(
            f"Invalid ubuntu_advantage configuration:\n{'\n'.join(errors)}"
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
            config_cmd = ["ua", "config", "set", f"{key}='{value}'"]
        
        try:
            subp.subp(config_cmd)
        except subp.ProcessExecutionError as e:
            enable_errors.append((key, e))
        
    if enable_errors:
        for param, error in enable_errors:
            msg = 'Failure enabling "{param}":\n{error}'.format(
                param=param, error=str(error)
            )
            util.logexc(LOG, msg)
        raise RuntimeError(
            "Failure enabling Ubuntu Advantage config(s): {}".format(
                ", ".join('"{}"'.format(param) for param, _ in enable_errors)
            )
        )
    enable_errors = []
    attach_cmd = ["ua", "attach", token]
    LOG.debug("Attaching to Ubuntu Advantage. %s", " ".join(attach_cmd))
    try:
        subp.subp(attach_cmd)
    except subp.ProcessExecutionError as e:
        msg = "Failure attaching Ubuntu Advantage:\n{error}".format(
            error=str(e)
        )
        util.logexc(LOG, msg)
        raise RuntimeError(msg) from e
    enable_errors = []
    for service in enable:
        try:
            cmd = ["ua", "enable", "--assume-yes", service]
            subp.subp(cmd, capture=True)
        except subp.ProcessExecutionError as e:
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


def maybe_install_ua_tools(cloud):
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


def handle(name, cfg, cloud, log, args):
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
    configure_ua(
        token=ua_section.get("token"),
        enable=ua_section.get("enable"),
        config=config,
    )


# vi: ts=4 expandtab
