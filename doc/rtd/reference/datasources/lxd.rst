.. _datasource_lxd:

LXD
***

The LXD datasource allows the user to provide custom ``user-data``,
``vendor-data``, ``meta-data`` and ``network-config`` to the instance without
running a network service (or even without having a network at all). This
datasource performs HTTP GETs against the `LXD socket device`_ which is
provided to each running LXD container and VM as :file:`/dev/lxd/sock`.

The LXD socket device :file:`/dev/lxd/sock` is required to use the LXD
datasource. This file is present in containers and VMs when the instance
configuration sets ``security.devlxd=true``.

The LXD datasource is detected as viable by ``ds-identify`` during the
:ref:`detect stage<boot-Detect>` when either :file:`/dev/lxd/sock` exists
or an LXD serial device is present in :file:`/sys/class/virtio-ports`.

The LXD datasource provides ``cloud-init`` with the ability to react to
``meta-data``, ``vendor-data``, ``user-data`` and ``network-config``
changes, and to render the updated configuration across a system reboot.

To modify which ``meta-data``, ``vendor-data`` or ``user-data`` are provided
to the launched container, use either LXD profiles or
``lxc launch ... -c <key>="<value>"`` at initial container launch, by setting
one of the following keys:

- ``cloud-init.user-data``: YAML which takes precedence and overrides both
  meta-data and vendor-data values.
- ``cloud-init.vendor-data``: YAML which overrides any ``meta-data`` values.
- ``cloud-init.network-config``: YAML representing either
  :ref:`network_config_v1` or :ref:`network_config_v2` format.
- ``user.<any-key>``: Keys prefixed with ``user.`` are included in
  :ref:`instance-data<instance-data>` under the ``ds.config`` key. These
  key value pairs are used in jinja :ref:`cloud-config<jinja-config>`
  and :ref:`user-data scripts<jinja-script>`. These key-value pairs may be
  inspected on a launched instance using ``cloud-init query ds.config``.

.. note::

    Periods (.) and hyphens (-) in Jinja2 have special meaning. Keys which contain a
    period or hyphen cannot use dot notation to access nested values. To support dot
    notation, cloud-init provides an alias by converting each hyphen (-) and period (.)
    character to an underscore (_). This means that an instance launched with
    ``-c user.special-key=1FE321`` can be queried using standard jinja notation,
    ``cloud-init query --format "{{ds.config['user.special-key']}}"`` or may use the alias
    notation ``cloud-init query --format "{{ds.config.user_special_key}}"`` or
    ``cloud-init query ds.config.user_special_key``.


Configuration
=============

By default, network configuration from this datasource will be:

.. code-block:: yaml

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

Hotplug
=======

Network hotplug functionality is supported for the LXD datasource as described
in the :ref:`events` documentation. As hotplug functionality relies on the
cloud-provided network meta-data, the LXD datasource will only meaningfully
react to a hotplug event if it has the configuration necessary to respond to
the change. Practically, this means that even with hotplug enabled, **the
default behavior for adding a new virtual NIC will result in no change**.

To update the configuration to be used by hotplug, first pass the network
configuration via the ``cloud-init.network-config`` (or
``user.network-config`` on older versions).

Example
-------

Given an LXD instance named ``my-lxd`` with hotplug enabled and
an LXD bridge named ``my-bridge``, the following will allow for additional
DHCP configuration of ``eth1``:

.. code-block:: shell-session

    $ cat /tmp/cloud-network-config.yaml
    version: 2
    ethernets:
        eth0:
            dhcp4: true
        eth1:
            dhcp4: true

    $ lxc config set my-lxd cloud-init.network-config="$(cat /tmp/cloud-network-config.yaml)"
    $ lxc config device add my-lxd eth1 nic name=eth1 nictype=bridged parent=my-bridge
    Device eth1 added to my-lxd

.. _LXD socket device: https://documentation.ubuntu.com/lxd/en/latest/dev-lxd/
