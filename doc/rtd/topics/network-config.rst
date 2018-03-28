*********************
Network Configuration
*********************

- Default Behavior
- Disabling Network Configuration
- Fallback Networking
- Network Configuration Sources
- Network Configuration Outputs
- Network Output Policy
- Network Configuration Tools
- Examples

.. _default_behavior:

Default Behavior
================

`Cloud-init`_ 's searches for network configuration in order of increasing
precedence; each item overriding the previous.

**Datasource**

For example, OpenStack may provide network config in the MetaData Service.

**System Config**

A ``network:`` entry in /etc/cloud/cloud.cfg.d/* configuration files.

**Kernel Command Line**

``ip=`` or ``network-config=<YAML config string>``

User-data cannot change an instance's network configuration.  In the absence
of network configuration in any of the above sources , `Cloud-init`_ will
write out a network configuration that will issue a DHCP request on a "first"
network interface.


Disabling Network Configuration
===============================

Users may disable `Cloud-init`_ 's network configuration capability and rely
on other methods, such as embedded configuration or other customizations.

`Cloud-init`_ supports the following methods for disabling cloud-init.


**Kernel Command Line**

`Cloud-init`_ will check for a parameter ``network-config`` and the
value is expected to be YAML string in the :ref:`network_config_v1` format.
The YAML string may optionally be ``Base64`` encoded, and optionally
compressed with ``gzip``.

Example disabling kernel command line entry: ::

  network-config={config: disabled}


**cloud config**

In the combined cloud-init configuration dictionary. ::

  network:
    config: disabled

If `Cloud-init`_ 's networking config has not been disabled, and
no other network information is found, then it will proceed
to generate a fallback networking configuration.


Fallback Network Configuration
==============================

`Cloud-init`_ will attempt to determine which of any attached network devices
is most likely to have a connection and then generate a network
configuration to issue a DHCP request on that interface.

`Cloud-init`_ runs during early boot and does not expect composed network
devices (such as Bridges) to be available.  `Cloud-init`_ does not consider
the following interface devices as likely 'first' network interfaces for
fallback configuration; they are filtered out from being selected.

- **loopback**: ``name=lo``
- **Virtual Ethernet**: ``name=veth*``
- **Software Bridges**: ``type=bridge``
- **Software VLANs**: ``type=vlan``


`Cloud-init`_ will prefer network interfaces that indicate they are connected
via the Linux ``carrier`` flag being set.  If no interfaces are marked
connected, then all unfiltered interfaces are potential connections.

Of the potential interfaces, `Cloud-init`_ will attempt to pick the "right"
interface given the information it has available.

Finally after selecting the "right" interface, a configuration is
generated and applied to the system.


Network Configuration Sources
=============================

`Cloud-init`_ accepts a number of different network configuration formats in
support of different cloud substrates.  The Datasource for these clouds in
`Cloud-init`_ will detect and consume Datasource-specific network
configuration formats for use when writing an instance's network
configuration.

The following Datasources optionally provide network configuration:

- :ref:`datasource_config_drive`

  - `OpenStack Metadata Service Network`_
  - :ref:`network_config_eni`

- :ref:`datasource_digital_ocean`

  - `DigitalOcean JSON metadata`_

- :ref:`datasource_nocloud`

  - :ref:`network_config_v1`
  - :ref:`network_config_v2`
  - :ref:`network_config_eni`

- :ref:`datasource_opennebula`

  - :ref:`network_config_eni`

- :ref:`datasource_openstack`

  - :ref:`network_config_eni`
  - `OpenStack Metadata Service Network`_

- :ref:`datasource_smartos`

  - `SmartOS JSON Metadata`_

For more information on network configuration formats

.. toctree::
  :maxdepth: 1

  network-config-format-eni.rst
  network-config-format-v1.rst
  network-config-format-v2.rst


Network Configuration Outputs
=============================

`Cloud-init`_ converts various forms of user supplied or automatically
generated configuration into an internal network configuration state. From
this state `Cloud-init`_ delegates rendering of the configuration to Distro
supported formats.  The following ``renderers`` are supported in cloud-init:

- **ENI**

/etc/network/interfaces or ``ENI`` is supported by the ``ifupdown`` package
found in Ubuntu and Debian.

- **Netplan**

Since Ubuntu 16.10, codename Yakkety, the ``netplan`` project has been an
optional network configuration tool which consumes :ref:`network_config_v2`
input and renders network configuration for supported backends such as
``systemd-networkd`` and ``NetworkManager``.

- **Sysconfig**

Sysconfig format is used by RHEL, CentOS, Fedora and other derivatives.


Network Output Policy
=====================

The default policy for selecting a network ``renderer`` in order of preference
is as follows:

- ENI
- Sysconfig
- Netplan

When applying the policy, `Cloud-init`_ checks if the current instance has the
correct binaries and paths to support the renderer.  The first renderer that
can be used is selected.  Users may override the network renderer policy by
supplying an updated configuration in cloud-config. ::

  system_info:
    network:
      renderers: ['netplan', 'eni', 'sysconfig']


Network Configuration Tools
===========================

`Cloud-init`_ contains one tool used to test input/output conversion between
formats.  The ``tools/net-convert.py`` in the `Cloud-init`_ source repository
is helpful for examining expected output for a given input format.

CLI Interface :

.. code-block:: shell-session

  % tools/net-convert.py --help
  usage: net-convert.py [-h] --network-data PATH --kind
                        {eni,network_data.json,yaml} -d PATH [-m name,mac]
                        --output-kind {eni,netplan,sysconfig}

  optional arguments:
    -h, --help            show this help message and exit
    --network-data PATH, -p PATH
    --kind {eni,network_data.json,yaml}, -k {eni,network_data.json,yaml}
    -d PATH, --directory PATH
                          directory to place output in
    -m name,mac, --mac name,mac
                          interface name to mac mapping
    --output-kind {eni,netplan,sysconfig}, -ok {eni,netplan,sysconfig}


Example output converting V2 to sysconfig:

.. code-block:: shell-session

  % tools/net-convert.py --network-data v2.yaml --kind yaml \
      --output-kind sysconfig -d target
  % cat target/etc/sysconfig/network-scripts/ifcfg-eth*
  # Created by cloud-init on instance boot automatically, do not edit.
  #
  BOOTPROTO=static
  DEVICE=eth7
  IPADDR=192.168.1.5/255.255.255.0
  NM_CONTROLLED=no
  ONBOOT=yes
  TYPE=Ethernet
  USERCTL=no
  # Created by cloud-init on instance boot automatically, do not edit.
  #
  BOOTPROTO=dhcp
  DEVICE=eth9
  NM_CONTROLLED=no
  ONBOOT=yes
  TYPE=Ethernet
  USERCTL=no


.. _Cloud-init: https://launchpad.net/cloud-init
.. _DigitalOcean JSON metadata: https://developers.digitalocean.com/documentation/metadata/#network-interfaces-index
.. _OpenStack Metadata Service Network: https://specs.openstack.org/openstack/nova-specs/specs/liberty/implemented/metadata-service-network-info.html
.. _SmartOS JSON Metadata: https://eng.joyent.com/mdata/datadict.html

.. vi: textwidth=78
