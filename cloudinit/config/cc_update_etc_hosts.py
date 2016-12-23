# Copyright (C) 2011 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""
Update Etc Hosts
----------------
**Summary:** update ``/etc/hosts``

This module will update the contents of ``/etc/hosts`` based on the
hostname/fqdn specified in config. Management of ``/etc/hosts`` is controlled
using ``manage_etc_hosts``. If this is set to false, cloud-init will not manage
``/etc/hosts`` at all. This is the default behavior.

If set to ``true`` or ``template``, cloud-init will generate ``/etc/hosts``
using the template located in ``/etc/cloud/templates/hosts.tmpl``. In the
``/etc/cloud/templates/hosts.tmpl`` template, the strings ``$hostname`` and
``$fqdn`` will be replaced with the hostname and fqdn respectively.

If ``manage_etc_hosts`` is set to ``localhost``, then cloud-init will not
rewrite ``/etc/hosts`` entirely, but rather will ensure that a entry for the
fqdn with ip ``127.0.1.1`` is present in ``/etc/hosts`` (i.e.
``ping <hostname>`` will ping ``127.0.1.1``).

.. note::
    if ``manage_etc_hosts`` is set ``true`` or ``template``, the contents
    of ``/etc/hosts`` will be updated every boot. to make any changes to
    ``/etc/hosts`` persistant they must be made in
    ``/etc/cloud/templates/hosts.tmpl``

.. note::
    for instructions on specifying hostname and fqdn, see documentation for
    ``cc_set_hostname``

**Internal name:** ``cc_update_etc_hosts``

**Module frequency:** per always

**Supported distros:** all

**Config keys**::

    manage_etc_hosts: <true/"template"/false/"localhost">
    fqdn: <fqdn>
    hostname: <fqdn/hostname>
"""

from cloudinit import templater
from cloudinit import util

from cloudinit.settings import PER_ALWAYS

frequency = PER_ALWAYS


def handle(name, cfg, cloud, log, _args):
    manage_hosts = util.get_cfg_option_str(cfg, "manage_etc_hosts", False)
    if util.translate_bool(manage_hosts, addons=['template']):
        (hostname, fqdn) = util.get_hostname_fqdn(cfg, cloud)
        if not hostname:
            log.warn(("Option 'manage_etc_hosts' was set,"
                     " but no hostname was found"))
            return

        # Render from a template file
        tpl_fn_name = cloud.get_template_filename("hosts.%s" %
                                                  (cloud.distro.osfamily))
        if not tpl_fn_name:
            raise RuntimeError(("No hosts template could be"
                                " found for distro %s") %
                               (cloud.distro.osfamily))

        templater.render_to_file(tpl_fn_name, '/etc/hosts',
                                 {'hostname': hostname, 'fqdn': fqdn})

    elif manage_hosts == "localhost":
        (hostname, fqdn) = util.get_hostname_fqdn(cfg, cloud)
        if not hostname:
            log.warn(("Option 'manage_etc_hosts' was set,"
                     " but no hostname was found"))
            return

        log.debug("Managing localhost in /etc/hosts")
        cloud.distro.update_etc_hosts(hostname, fqdn)
    else:
        log.debug(("Configuration option 'manage_etc_hosts' is not set,"
                   " not managing /etc/hosts in module %s"), name)

# vi: ts=4 expandtab
