# Copyright (C) 2016 Canonical Ltd.
#
# Author: Ryan Harper <ryan.harper@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""NTP: enable and configure ntp"""

import copy
import logging
import os

from cloudinit import subp, temp_utils, templater, type_utils, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.settings import PER_INSTANCE

LOG = logging.getLogger(__name__)

frequency = PER_INSTANCE
NTP_CONF = "/etc/ntp.conf"
NR_POOL_SERVERS = 4
distros = [
    "almalinux",
    "alpine",
    "azurelinux",
    "centos",
    "cloudlinux",
    "cos",
    "debian",
    "eurolinux",
    "fedora",
    "freebsd",
    "mariner",
    "miraclelinux",
    "openbsd",
    "openeuler",
    "OpenCloudOS",
    "openmandriva",
    "opensuse",
    "opensuse-microos",
    "opensuse-tumbleweed",
    "opensuse-leap",
    "photon",
    "rhel",
    "rocky",
    "sle_hpc",
    "sle-micro",
    "sles",
    "TencentOS",
    "ubuntu",
    "virtuozzo",
]

NTP_CLIENT_CONFIG = {
    "chrony": {
        "check_exe": "chronyd",
        "confpath": "/etc/chrony.conf",
        "packages": ["chrony"],
        "service_name": "chrony",
        "template_name": "chrony.conf.{distro}",
        "template": None,
    },
    "ntp": {
        "check_exe": "ntpd",
        "confpath": NTP_CONF,
        "packages": ["ntp"],
        "service_name": "ntp",
        "template_name": "ntp.conf.{distro}",
        "template": None,
    },
    "ntpdate": {
        "check_exe": "ntpdate",
        "confpath": NTP_CONF,
        "packages": ["ntpdate"],
        "service_name": "ntpdate",
        "template_name": "ntp.conf.{distro}",
        "template": None,
    },
    "openntpd": {
        "check_exe": "ntpd",
        "confpath": "/etc/ntpd.conf",
        "packages": [],
        "service_name": "ntpd",
        "template_name": "ntpd.conf.{distro}",
        "template": None,
    },
    "systemd-timesyncd": {
        "check_exe": "/lib/systemd/systemd-timesyncd",
        "confpath": "/etc/systemd/timesyncd.conf.d/cloud-init.conf",
        "packages": [],
        "service_name": "systemd-timesyncd",
        "template_name": "timesyncd.conf",
        "template": None,
    },
}

# This is Distro-specific configuration overrides of the base config
DISTRO_CLIENT_CONFIG = {
    "alpine": {
        "chrony": {
            "confpath": "/etc/chrony/chrony.conf",
            "service_name": "chronyd",
        },
        "ntp": {
            "confpath": "/etc/ntp.conf",
            "packages": [],
            "service_name": "ntpd",
        },
    },
    "azurelinux": {
        "chrony": {
            "service_name": "chronyd",
        },
        "systemd-timesyncd": {
            "check_exe": "/usr/lib/systemd/systemd-timesyncd",
            "confpath": "/etc/systemd/timesyncd.conf",
        },
    },
    "centos": {
        "ntp": {
            "service_name": "ntpd",
        },
        "chrony": {
            "service_name": "chronyd",
        },
    },
    "cos": {
        "chrony": {
            "service_name": "chronyd",
            "confpath": "/etc/chrony/chrony.conf",
        },
    },
    "debian": {
        "chrony": {
            "confpath": "/etc/chrony/chrony.conf",
        },
    },
    "freebsd": {
        "ntp": {
            "confpath": "/etc/ntp.conf",
            "service_name": "ntpd",
            "template_name": "ntp.conf.{distro}",
        },
        "chrony": {
            "confpath": "/usr/local/etc/chrony.conf",
            "packages": ["chrony"],
            "service_name": "chronyd",
            "template_name": "chrony.conf.{distro}",
        },
        "openntpd": {
            "check_exe": "/usr/local/sbin/ntpd",
            "confpath": "/usr/local/etc/ntp.conf",
            "packages": ["openntpd"],
            "service_name": "openntpd",
            "template_name": "ntpd.conf.openbsd",
        },
    },
    "mariner": {
        "chrony": {
            "service_name": "chronyd",
        },
        "systemd-timesyncd": {
            "check_exe": "/usr/lib/systemd/systemd-timesyncd",
            "confpath": "/etc/systemd/timesyncd.conf",
        },
    },
    "openbsd": {
        "openntpd": {},
    },
    "openmandriva": {
        "chrony": {
            "service_name": "chronyd",
        },
        "ntp": {
            "confpath": "/etc/ntp.conf",
            "service_name": "ntpd",
        },
        "systemd-timesyncd": {
            "check_exe": "/lib/systemd/systemd-timesyncd",
        },
    },
    "opensuse": {
        "chrony": {
            "service_name": "chronyd",
        },
        "ntp": {
            "confpath": "/etc/ntp.conf",
            "service_name": "ntpd",
        },
        "systemd-timesyncd": {
            "check_exe": "/usr/lib/systemd/systemd-timesyncd",
        },
    },
    "photon": {
        "chrony": {
            "service_name": "chronyd",
        },
        "ntp": {"service_name": "ntpd", "confpath": "/etc/ntp.conf"},
        "systemd-timesyncd": {
            "check_exe": "/usr/lib/systemd/systemd-timesyncd",
            "confpath": "/etc/systemd/timesyncd.conf",
        },
    },
    "rhel": {
        "ntp": {
            "service_name": "ntpd",
        },
        "chrony": {
            "service_name": "chronyd",
        },
    },
    "sles": {
        "chrony": {
            "service_name": "chronyd",
        },
        "ntp": {
            "confpath": "/etc/ntp.conf",
            "service_name": "ntpd",
        },
        "systemd-timesyncd": {
            "check_exe": "/usr/lib/systemd/systemd-timesyncd",
        },
    },
    "ubuntu": {
        "chrony": {
            "confpath": "/etc/chrony/chrony.conf",
        },
    },
}

for distro in ("opensuse-microos", "opensuse-tumbleweed", "opensuse-leap"):
    DISTRO_CLIENT_CONFIG[distro] = DISTRO_CLIENT_CONFIG["opensuse"]

for distro in ("almalinux", "cloudlinux"):
    DISTRO_CLIENT_CONFIG[distro] = DISTRO_CLIENT_CONFIG["rhel"]

for distro in ("sle_hpc", "sle-micro"):
    DISTRO_CLIENT_CONFIG[distro] = DISTRO_CLIENT_CONFIG["sles"]

# The schema definition for each cloud-config module is a strict contract for
# describing supported configuration parameters for each cloud-config section.
# It allows cloud-config to validate and alert users to invalid or ignored
# configuration options before actually attempting to deploy with said
# configuration.

meta: MetaSchema = {
    "id": "cc_ntp",
    "distros": distros,
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": ["ntp"],
}  # type: ignore


REQUIRED_NTP_CONFIG_KEYS = frozenset(
    ["check_exe", "confpath", "packages", "service_name"]
)


def distro_ntp_client_configs(distro):
    """Construct a distro-specific ntp client config dictionary by merging
       distro specific changes into base config.

    @param distro: String providing the distro class name.
    @returns: Dict of distro configurations for ntp clients.
    """
    dcfg = DISTRO_CLIENT_CONFIG
    cfg = copy.copy(NTP_CLIENT_CONFIG)
    if distro in dcfg:
        cfg = util.mergemanydict([cfg, dcfg[distro]], reverse=True)
    return cfg


def select_ntp_client(ntp_client, distro):
    """Determine which ntp client is to be used, consulting the distro
       for its preference.

    @param ntp_client: String name of the ntp client to use.
    @param distro: Distro class instance.
    @returns: Dict of the selected ntp client or {} if none selected.
    """

    # construct distro-specific ntp_client_config dict
    distro_cfg = distro_ntp_client_configs(distro.name)

    # user specified client, return its config
    if ntp_client and ntp_client != "auto":
        LOG.debug(
            'Selected NTP client "%s" via user-data configuration', ntp_client
        )
        return distro_cfg.get(ntp_client, {})

    # default to auto if unset in distro
    distro_ntp_client = distro.get_option("ntp_client", "auto")

    clientcfg = {}
    if distro_ntp_client == "auto":
        for client in distro.preferred_ntp_clients:
            cfg = distro_cfg.get(client)
            if subp.which(cfg.get("check_exe")):
                LOG.debug(
                    'Selected NTP client "%s", already installed', client
                )
                clientcfg = cfg
                break

        if not clientcfg:
            client = distro.preferred_ntp_clients[0]
            LOG.debug(
                'Selected distro preferred NTP client "%s", not yet installed',
                client,
            )
            clientcfg = distro_cfg.get(client)
    else:
        LOG.debug(
            'Selected NTP client "%s" via distro system config',
            distro_ntp_client,
        )
        clientcfg = distro_cfg.get(distro_ntp_client, {})

    return clientcfg


def install_ntp_client(install_func, packages=None, check_exe="ntpd"):
    """Install ntp client package if not already installed.

    @param install_func: function.  This parameter is invoked with the contents
    of the packages parameter.
    @param packages: list.  This parameter defaults to ['ntp'].
    @param check_exe: string.  The name of a binary that indicates the package
    the specified package is already installed.
    """
    if subp.which(check_exe):
        return
    if packages is None:
        packages = ["ntp"]

    install_func(packages)


def rename_ntp_conf(confpath=None):
    """Rename any existing ntp client config file

    @param confpath: string. Specify a path to an existing ntp client
    configuration file.
    """
    if os.path.exists(confpath):
        util.rename(confpath, confpath + ".dist")


def generate_server_names(distro):
    """Generate a list of server names to populate an ntp client configuration
    file.

    @param distro: string.  Specify the distro name
    @returns: list: A list of strings representing ntp servers for this distro.
    """
    names = []
    pool_distro = distro

    if distro == "sles":
        # For legal reasons x.pool.sles.ntp.org does not exist,
        # use the opensuse pool
        pool_distro = "opensuse"
    elif distro == "alpine" or distro == "eurolinux":
        # Alpine-specific pool (i.e. x.alpine.pool.ntp.org) does not exist
        # so use general x.pool.ntp.org instead. The same applies to EuroLinux
        pool_distro = ""

    for x in range(NR_POOL_SERVERS):
        names.append(
            ".".join(
                [n for n in [str(x)] + [pool_distro] + ["pool.ntp.org"] if n]
            )
        )

    return names


def write_ntp_config_template(
    distro_name,
    service_name=None,
    servers=None,
    pools=None,
    allow=None,
    peers=None,
    path=None,
    template_fn=None,
    template=None,
):
    """Render a ntp client configuration for the specified client.

    @param distro_name: string.  The distro class name.
    @param service_name: string. The name of the NTP client service.
    @param servers: A list of strings specifying ntp servers. Defaults to empty
    list.
    @param pools: A list of strings specifying ntp pools. Defaults to empty
    list.
    @param allow: A list of strings specifying a network/CIDR. Defaults to
    empty list.
    @param peers: A list nodes that should peer with each other. Defaults to
    empty list.
    @param path: A string to specify where to write the rendered template.
    @param template_fn: A string to specify the template source file.
    @param template: A string specifying the contents of the template. This
    content will be written to a temporary file before being used to render
    the configuration file.

    @raises: ValueError when path is None.
    @raises: ValueError when template_fn is None and template is None.
    """
    if not servers:
        servers = []
    if not pools:
        pools = []
    if not allow:
        allow = []
    if not peers:
        peers = []

    if len(servers) == 0 and len(pools) == 0 and distro_name == "cos":
        return
    if (
        len(servers) == 0
        and distro_name == "alpine"
        and service_name == "ntpd"
    ):
        # Alpine's Busybox ntpd only understands "servers" configuration
        # and not "pool" configuration.
        servers = generate_server_names(distro_name)
        LOG.debug("Adding distro default ntp servers: %s", ",".join(servers))
    elif len(servers) == 0 and len(pools) == 0:
        pools = generate_server_names(distro_name)
        LOG.debug(
            "Adding distro default ntp pool servers: %s", ",".join(pools)
        )

    if not path:
        raise ValueError("Invalid value for path parameter")

    if not template_fn and not template:
        raise ValueError("Not template_fn or template provided")

    params = {
        "servers": servers,
        "pools": pools,
        "allow": allow,
        "peers": peers,
    }
    if template:
        tfile = temp_utils.mkstemp(prefix="template_name-", suffix=".tmpl")
        template_fn = tfile[1]  # filepath is second item in tuple
        util.write_file(template_fn, content=template)

    templater.render_to_file(template_fn, path, params)
    # clean up temporary template
    if template:
        util.del_file(template_fn)


def supplemental_schema_validation(ntp_config):
    """Validate user-provided ntp:config option values.

    This function supplements flexible jsonschema validation with specific
    value checks to aid in triage of invalid user-provided configuration.

    @param ntp_config: Dictionary of configuration value under 'ntp'.

    @raises: ValueError describing invalid values provided.
    """
    errors = []
    missing = REQUIRED_NTP_CONFIG_KEYS.difference(set(ntp_config.keys()))
    if missing:
        keys = ", ".join(sorted(missing))
        errors.append(
            "Missing required ntp:config keys: {keys}".format(keys=keys)
        )
    elif not any(
        [ntp_config.get("template"), ntp_config.get("template_name")]
    ):
        errors.append(
            "Either ntp:config:template or ntp:config:template_name values"
            " are required"
        )
    for key, value in sorted(ntp_config.items()):
        keypath = "ntp:config:" + key
        if key == "confpath":
            if not all([value, isinstance(value, str)]):
                errors.append(
                    "Expected a config file path {keypath}."
                    " Found ({value})".format(keypath=keypath, value=value)
                )
        elif key == "packages":
            if not isinstance(value, list):
                errors.append(
                    "Expected a list of required package names for {keypath}."
                    " Found ({value})".format(keypath=keypath, value=value)
                )
        elif key in ("template", "template_name"):
            if value is None:  # Either template or template_name can be none
                continue
            if not isinstance(value, str):
                errors.append(
                    "Expected a string type for {keypath}."
                    " Found ({value})".format(keypath=keypath, value=value)
                )
        elif not isinstance(value, str):
            errors.append(
                "Expected a string type for {keypath}. Found ({value})".format(
                    keypath=keypath, value=value
                )
            )

    if errors:
        raise ValueError(
            r"Invalid ntp configuration:\n{errors}".format(
                errors="\n".join(errors)
            )
        )


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    """Enable and configure ntp."""
    if "ntp" not in cfg:
        LOG.debug(
            "Skipping module named %s, not present or disabled by cfg", name
        )
        return
    ntp_cfg = cfg["ntp"]
    if ntp_cfg is None:
        ntp_cfg = {}  # Allow empty config which will install the package

    # TODO drop this when validate_cloudconfig_schema is strict=True
    if not isinstance(ntp_cfg, (dict)):
        raise RuntimeError(
            "'ntp' key existed in config, but not a dictionary type,"
            " is a {_type} instead".format(_type=type_utils.obj_name(ntp_cfg))
        )

    # Allow users to explicitly enable/disable
    enabled = ntp_cfg.get("enabled", True)
    if util.is_false(enabled):
        LOG.debug("Skipping module named %s, disabled by cfg", name)
        return

    # Select which client is going to be used and get the configuration
    ntp_client_config = select_ntp_client(
        ntp_cfg.get("ntp_client"), cloud.distro
    )
    # Allow user ntp config to override distro configurations
    ntp_client_config = util.mergemanydict(
        [ntp_client_config, ntp_cfg.get("config", {})], reverse=True
    )

    supplemental_schema_validation(ntp_client_config)
    rename_ntp_conf(confpath=ntp_client_config.get("confpath"))

    template_fn = None
    if not ntp_client_config.get("template"):
        template_name = ntp_client_config.get("template_name").replace(
            "{distro}", cloud.distro.name
        )
        template_fn = cloud.get_template_filename(template_name)
        if not template_fn:
            msg = (
                "No template found, not rendering %s"
                % ntp_client_config.get("template_name")
            )
            raise RuntimeError(msg)

    LOG.debug("service_name: %s", ntp_client_config.get("service_name"))
    LOG.debug("servers: %s", ntp_cfg.get("servers", []))
    LOG.debug("pools: %s", ntp_cfg.get("pools", []))
    LOG.debug("allow: %s", ntp_cfg.get("allow", []))
    LOG.debug("peers: %s", ntp_cfg.get("peers", []))
    write_ntp_config_template(
        cloud.distro.name,
        service_name=ntp_client_config.get("service_name"),
        servers=ntp_cfg.get("servers", []),
        pools=ntp_cfg.get("pools", []),
        allow=ntp_cfg.get("allow", []),
        peers=ntp_cfg.get("peers", []),
        path=ntp_client_config.get("confpath"),
        template_fn=template_fn,
        template=ntp_client_config.get("template"),
    )

    install_ntp_client(
        cloud.distro.install_packages,
        packages=ntp_client_config["packages"],
        check_exe=ntp_client_config["check_exe"],
    )
    if util.is_BSD():
        if ntp_client_config.get("service_name") != "ntpd":
            try:
                cloud.distro.manage_service("stop", "ntpd")
            except subp.ProcessExecutionError:
                LOG.warning("Failed to stop base ntpd service")
            try:
                cloud.distro.manage_service("disable", "ntpd")
            except subp.ProcessExecutionError:
                LOG.warning("Failed to disable base ntpd service")

        try:
            cloud.distro.manage_service(
                "enable", ntp_client_config.get("service_name")
            )
        except subp.ProcessExecutionError as e:
            LOG.exception("Failed to enable ntp service: %s", e)
            raise
    try:
        cloud.distro.manage_service(
            "reload", ntp_client_config.get("service_name")
        )
    except subp.ProcessExecutionError as e:
        LOG.exception("Failed to reload/start ntp service: %s", e)
        raise
