# Copyright (C) 2011 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Update Etc Hosts: Update the hosts file (usually ``/etc/hosts``)"""

from logging import Logger
from textwrap import dedent

from cloudinit import templater, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.settings import PER_ALWAYS

MODULE_DESCRIPTION = """\
This module will update the contents of the local hosts database (hosts file;
usually ``/etc/hosts``) based on the hostname/fqdn specified in config.
Management of the hosts file is controlled using ``manage_etc_hosts``. If this
is set to false, cloud-init will not manage the hosts file at all. This is the
default behavior.

If set to ``true``, cloud-init will generate the hosts file
using the template located in ``/etc/cloud/templates/hosts.tmpl``. In the
``/etc/cloud/templates/hosts.tmpl`` template, the strings ``$hostname`` and
``$fqdn`` will be replaced with the hostname and fqdn respectively.

If ``manage_etc_hosts`` is set to ``localhost``, then cloud-init will not
rewrite the hosts file entirely, but rather will ensure that a entry for the
fqdn with a distribution dependent ip is present (i.e. ``ping <hostname>`` will
ping ``127.0.0.1`` or ``127.0.1.1`` or other ip).

.. note::
    if ``manage_etc_hosts`` is set ``true``, the contents
    of the hosts file will be updated every boot. To make any changes to
    the hosts file persistent they must be made in
    ``/etc/cloud/templates/hosts.tmpl``

.. note::
    for instructions on specifying hostname and fqdn, see documentation for
    ``cc_set_hostname``
"""

distros = ["all"]

meta: MetaSchema = {
    "id": "cc_update_etc_hosts",
    "name": "Update Etc Hosts",
    "title": "Update the hosts file (usually ``/etc/hosts``)",
    "description": MODULE_DESCRIPTION,
    "distros": distros,
    "examples": [
        dedent(
            """\
    # Do not update or manage /etc/hosts at all. This is the default behavior.
    #
    # Whatever is present at instance boot time will be present after boot.
    # User changes will not be overwritten.
    manage_etc_hosts: false
    """
        ),
        dedent(
            """\
    # Manage /etc/hosts with cloud-init.
    # On every boot, /etc/hosts will be re-written from
    # ``/etc/cloud/templates/hosts.tmpl``.
    #
    # The strings '$hostname' and '$fqdn' are replaced in the template
    # with the appropriate values either from the config-config ``fqdn`` or
    # ``hostname`` if provided. When absent, the cloud metadata will be
    # checked for ``local-hostname` which can be split into <hostname>.<fqdn>.
    #
    # To make modifications persistent across a reboot, you must modify
    # ``/etc/cloud/templates/hosts.tmpl``.
    manage_etc_hosts: true
    """
        ),
        dedent(
            """\
    # Update /etc/hosts every boot providing a "localhost" 127.0.1.1 entry
    # with the latest hostname and fqdn as provided by either IMDS or
    # cloud-config.
    # All other entries will be left as is.
    # 'ping `hostname`' will ping 127.0.1.1
    manage_etc_hosts: localhost
    """
        ),
    ],
    "frequency": PER_ALWAYS,
    "activate_by_schema_keys": ["manage_etc_hosts"],
}

__doc__ = get_meta_doc(meta)


def handle(
    name: str, cfg: Config, cloud: Cloud, log: Logger, args: list
) -> None:
    manage_hosts = util.get_cfg_option_str(cfg, "manage_etc_hosts", False)

    hosts_fn = cloud.distro.hosts_fn

    if util.translate_bool(manage_hosts, addons=["template"]):
        if manage_hosts == "template":
            log.warning(
                "DEPRECATED: please use manage_etc_hosts: true instead of"
                " 'template'"
            )
        (hostname, fqdn, _) = util.get_hostname_fqdn(cfg, cloud)
        if not hostname:
            log.warning(
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
            log.warning(
                "Option 'manage_etc_hosts' was set, but no hostname was found"
            )
            return

        log.debug("Managing localhost in %s", hosts_fn)
        cloud.distro.update_etc_hosts(hostname, fqdn)
    else:
        log.debug(
            "Configuration option 'manage_etc_hosts' is not set,"
            " not managing %s in module %s",
            hosts_fn,
            name,
        )


# vi: ts=4 expandtab
