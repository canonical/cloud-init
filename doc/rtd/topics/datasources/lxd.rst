.. _datasource_lxd:

LXD
===

The data source ``LXD`` allows the user to provide custom user-data,
vendor-data, meta-data and network-config to the instance without running
a network service (or even without having a network at all). This datasource
performs HTTP GETs against the `LXD socket device`_ which is provided to each
running LXD container and VM as ``/dev/lxd/sock`` and represents all
instance-metadata as versioned HTTP routes such as:

  - 1.0/meta-data
  - 1.0/config/user.meta-data
  - 1.0/config/user.vendor-data
  - 1.0/config/user.user-data
  - 1.0/config/user.<any-custom-key>

The LXD socket device ``/dev/lxd/sock`` is only present on containers and VMs
when the instance configuration has ``security.devlxd=true`` (default).
Disabling ``security.devlxd`` configuration setting at initial launch will
ensure that cloud-init uses the :ref:`datasource_nocloud` datasource.
Disabling ``security.devlxd`` ove the life of the container will result in
warnings from cloud-init and cloud-init will keep the originally detected LXD
datasource.

The LXD datasource provides cloud-init the opportunity to react to meta-data,
vendor-data, user-data and network-config changes and render the updated
configuration across a system reboot.

One can manipulate what meta-data, vendor-data or user-data is provided to
the launched container using the LXD profiles or
``lxc launch ... -c <key>="<value>"`` at initial container launch using one of
the following keys:

 - user.meta-data: YAML metadata which will be appended to base meta-data
 - user.vendor-data: YAML which overrides any meta-data values
 - user.network-config: YAML representing either :ref:`network_config_v1` or
   :ref:`network_config_v2` format
 - user.user-data: YAML which takes preference and overrides both meta-data
   and vendor-data values
 - user.any-key: Custom user configuration key and value pairs can be passed to
   cloud-init. Those keys/values will be present in instance-data which can be
   used by both `#template: jinja` #cloud-config templates and
   the `cloud-init query` command.


By default, network configuration from this datasource will be:

.. code:: yaml

  version: 1
  config:
      - type: physical
        name: eth0
        subnets:
            - type: dhcp
              control: auto

This datasource is intended to replace :ref:`datasource_nocloud`
datasource for LXD instances with a more direct support for LXD APIs instead
of static NoCloud seed files.

.. _LXD socket device: https://linuxcontainers.org/lxd/docs/master/dev-lxd
.. vi: textwidth=79
