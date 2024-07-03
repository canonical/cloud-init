# Copyright (C) 2011 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Update Etc Hosts: Update the hosts file (usually ``/etc/hosts``)"""

import logging

from cloudinit import templater, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.settings import PER_ALWAYS

meta: MetaSchema = {
    "id": "cc_update_etc_hosts",
    "distros": ["all"],
    "frequency": PER_ALWAYS,
    "activate_by_schema_keys": ["manage_etc_hosts"],
}  # type: ignore

LOG = logging.getLogger(__name__)


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    manage_hosts = util.get_cfg_option_str(cfg, "manage_etc_hosts", False)

    hosts_fn = cloud.distro.hosts_fn

    if util.translate_bool(manage_hosts, addons=["template"]):
        if manage_hosts == "template":
            util.deprecate(
                deprecated="Value 'template' for key 'manage_etc_hosts'",
                deprecated_version="22.2",
                extra_message="Use 'true' instead.",
            )
        (hostname, fqdn, _) = util.get_hostname_fqdn(cfg, cloud)
        if not hostname:
            LOG.warning(
                "Option 'manage_etc_hosts' was set, but no hostname was found"
            )
            return

        # Render from a template file
        tpl_fn_name = cloud.get_template_filename(
            "hosts.%s" % (cloud.distro.osfamily)
        )
        if not tpl_fn_name:
            raise RuntimeError(
                "No hosts template could be found for distro %s"
                % (cloud.distro.osfamily)
            )

        templater.render_to_file(
            tpl_fn_name, hosts_fn, {"hostname": hostname, "fqdn": fqdn}
        )

    elif manage_hosts == "localhost":
        (hostname, fqdn, _) = util.get_hostname_fqdn(cfg, cloud)
        if not hostname:
            LOG.warning(
                "Option 'manage_etc_hosts' was set, but no hostname was found"
            )
            return

        LOG.debug("Managing localhost in %s", hosts_fn)
        cloud.distro.update_etc_hosts(hostname, fqdn)
    else:
        LOG.debug(
            "Configuration option 'manage_etc_hosts' is not set,"
            " not managing %s in module %s",
            hosts_fn,
            name,
        )
