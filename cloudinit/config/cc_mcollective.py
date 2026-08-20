# Copyright (C) 2009-2011 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Marc Cluet <marc.cluet@canonical.com>
# Based on code by Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Mcollective: Install, configure and start mcollective"""

import errno
import io
import logging

from cloudinit import subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.settings import PER_INSTANCE

PUBCERT_FILE = "/etc/mcollective/ssl/server-public.pem"
PRICERT_FILE = "/etc/mcollective/ssl/server-private.pem"
SERVER_CFG = "/etc/mcollective/server.cfg"

meta: MetaSchema = {
    "id": "cc_mcollective",
    "distros": ["all"],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": ["mcollective"],
}

LOG = logging.getLogger(__name__)


class _McollectiveConfig:
    """Simple key=value config parser for mcollective server.cfg.

    Supports optional INI sections.  Top-level (sectionless) keys and
    sections are stored separately and written back in original order.
    """

    def __init__(self, infile=None):
        self._keys = {}  # top-level key -> value
        self._key_order = []  # insertion order for top-level keys
        self._sections = {}  # section_name -> dict of key-value
        self._section_order = []  # insertion order for sections
        self._interleaved_order = []  # ('key', name) or ('section', name)
        if infile is not None:
            self._load(infile)

    def _load(self, infile):
        if hasattr(infile, "read"):
            content = infile.read()
        else:
            content = infile
        if isinstance(content, (bytes, bytearray)):
            content = content.decode("utf-8")
        current_section = None
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("[") and stripped.endswith("]"):
                current_section = stripped[1:-1].strip()
                if current_section not in self._sections:
                    self._sections[current_section] = {}
                    self._section_order.append(current_section)
                    self._interleaved_order.append(("section", current_section))
            elif "=" in stripped:
                key, _, value = stripped.partition("=")
                key = key.strip()
                value = value.strip()
                if current_section:
                    self._sections[current_section][key] = value
                else:
                    if key not in self._keys:
                        self._key_order.append(key)
                        self._interleaved_order.append(("key", key))
                    self._keys[key] = value

    @property
    def sections(self):
        return list(self._sections.keys())

    def __getitem__(self, name):
        if name in self._sections:
            return self._sections[name]
        return self._keys[name]

    def __setitem__(self, name, value):
        if isinstance(value, dict):
            if name not in self._sections:
                self._sections[name] = {}
                self._section_order.append(name)
                self._interleaved_order.append(("section", name))
            self._sections[name].update(value)
        else:
            if name not in self._keys:
                self._key_order.append(name)
                self._interleaved_order.append(("key", name))
            self._keys[name] = str(value)

    def __contains__(self, name):
        return name in self._keys or name in self._sections

    def write(self, outfile):
        lines = []
        seen_sections = set()
        for type_, name in self._interleaved_order:
            if type_ == "key" and name in self._keys:
                lines.append("%s = %s" % (name, self._keys[name]))
            elif type_ == "section" and name in self._sections:
                if name not in seen_sections:
                    seen_sections.add(name)
                    lines.append("[%s]" % name)
                    for k, v in self._sections[name].items():
                        lines.append("%s = %s" % (k, v))
        content = "\n".join(lines)
        if isinstance(outfile, io.BytesIO):
            outfile.write(content.encode("utf-8"))
        else:
            outfile.write(content)


def configure(
    config,
    server_cfg=SERVER_CFG,
    pubcert_file=PUBCERT_FILE,
    pricert_file=PRICERT_FILE,
):
    # Read server.cfg (if it exists) values from the
    # original file in order to be able to mix the rest up.
    try:
        old_contents = util.load_binary_file(server_cfg, quiet=False)
        mcollective_config = _McollectiveConfig(io.BytesIO(old_contents))
    except IOError as e:
        if e.errno != errno.ENOENT:
            raise
        else:
            LOG.debug(
                "Did not find file %s (starting with an empty config)",
                server_cfg,
            )
            mcollective_config = _McollectiveConfig()
    for cfg_name, cfg in config.items():
        if cfg_name == "public-cert":
            util.write_file(pubcert_file, cfg, mode=0o644)
            mcollective_config["plugin.ssl_server_public"] = pubcert_file
            mcollective_config["securityprovider"] = "ssl"
        elif cfg_name == "private-cert":
            util.write_file(pricert_file, cfg, mode=0o600)
            mcollective_config["plugin.ssl_server_private"] = pricert_file
            mcollective_config["securityprovider"] = "ssl"
        else:
            if isinstance(cfg, str):
                # Just set it in the 'main' section
                mcollective_config[cfg_name] = cfg
            elif isinstance(cfg, (dict)):
                # Iterate through the config items, create a section if
                # it is needed and then add/or create items as needed
                if cfg_name not in mcollective_config.sections:
                    mcollective_config[cfg_name] = {}
                for o, v in cfg.items():
                    mcollective_config[cfg_name][o] = v
            else:
                # Otherwise just try to convert it to a string
                mcollective_config[cfg_name] = str(cfg)

    try:
        # We got all our config as wanted we'll copy
        # the previous server.cfg and overwrite the old with our new one
        util.copy(server_cfg, "%s.old" % (server_cfg))
    except IOError as e:
        if e.errno == errno.ENOENT:
            # Doesn't exist to copy...
            pass
        else:
            raise

    # Now we got the whole (new) file, write to disk...
    contents = io.BytesIO()
    mcollective_config.write(contents)
    util.write_file(server_cfg, contents.getvalue(), mode=0o644)


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    # If there isn't a mcollective key in the configuration don't do anything
    if "mcollective" not in cfg:
        LOG.debug(
            "Skipping module named %s, no 'mcollective' key in configuration",
            name,
        )
        return

    mcollective_cfg = cfg["mcollective"]

    # Start by installing the mcollective package ...
    cloud.distro.install_packages(["mcollective"])

    # ... and then update the mcollective configuration
    if "conf" in mcollective_cfg:
        configure(config=mcollective_cfg["conf"])

    # restart mcollective to handle updated config
    subp.subp(["service", "mcollective", "restart"], capture=False)
