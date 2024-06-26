.. _network_config_v1:

Networking config Version 1
***************************

This network configuration format lets users customise their instance's
networking interfaces by assigning subnet configuration, virtual device
creation (bonds, bridges, VLANs) routes and DNS configuration.

Required elements of a `network config Version 1` are ``config`` and
``version``.

``Cloud-init`` will read this format from :ref:`base_config_reference`.

For example, the following could be present in
:file:`/etc/cloud/cloud.cfg.d/custom-networking.cfg`:

.. literalinclude:: ../../examples/network-config-v1-physical-dhcp.yaml
   :language: yaml

The :ref:`datasource_nocloud` datasource can also provide ``cloud-init``
networking configuration in this format.

Configuration types
===================

Within the network ``config`` portion, users include a list of configuration
types. The current list of support ``type`` values are as follows:

- ``physical``: Physical
- ``bond``: Bond
- ``bridge``: Bridge
- ``vlan``: VLAN
- ``nameserver``: Nameserver
- ``route``: Route

Physical, Bond, Bridge and VLAN types may also include IP configuration under
the key ``subnets``.

- ``subnets``: Subnet/IP

Physical
--------

The ``physical`` type configuration represents a "physical" network device,
typically Ethernet-based. At least one of these entries is required for
external network connectivity. Type ``physical`` requires only one key:
``name``. A ``physical`` device may contain some or all of the following
keys:

``name: <desired device name>``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

A device's name must be less than 15 characters. Names exceeding the maximum
will be truncated. This is a limitation of the Linux kernel network-device
structure.

``mac_address: <MAC Address>``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The MAC Address is a device unique identifier that most Ethernet-based network
devices possess. Specifying a MAC Address is optional.
Letters must be lowercase.

.. note::
   It is best practice to "quote" all MAC addresses, since an unquoted MAC
   address might be incorrectly interpreted as an integer in `YAML`_.

.. note::
   ``Cloud-init`` will handle the persistent mapping between a device's
   ``name`` and the ``mac_address``.

``mtu: <MTU SizeBytes>``
^^^^^^^^^^^^^^^^^^^^^^^^

The MTU key represents a device's Maximum Transmission Unit, which is the
largest size packet or frame, specified in octets (eight-bit bytes), that can
be sent in a packet- or frame-based network. Specifying ``mtu`` is optional.

.. note::
   The possible supported values of a device's MTU are not available at
   configuration time. It's possible to specify a value too large or to
   small for a device, and may be ignored by the device.

``accept-ra: <boolean>``
^^^^^^^^^^^^^^^^^^^^^^^^

The ``accept-ra`` key is a boolean value that specifies whether or not to
accept Router Advertisements (RA) for this interface. Specifying ``accept-ra``
is optional.

Physical example
^^^^^^^^^^^^^^^^

.. literalinclude:: ../../examples/network-config-v1-physical-3-nic.yaml
   :language: yaml

Bond
----

A ``bond`` type will configure a Linux software Bond with one or more network
devices. A ``bond`` type requires the following keys:

``name: <desired device name>``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

A device's name must be less than 15 characters. Names exceeding the maximum
will be truncated. This is a limitation of the Linux kernel network-device
structure.

``mac_address: <MAC Address>``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When specifying MAC Address on a bond this value will be assigned to the bond
device and may be different than the MAC address of any of the underlying
bond interfaces. Specifying a MAC Address is optional. If ``mac_address`` is
not present, then the bond will use one of the MAC Address values from one of
the bond interfaces.

.. note::
   It is best practice to "quote" all MAC addresses, since an unquoted MAC
   address might be incorrectly interpreted as an integer in `YAML`_.

``bond_interfaces: <List of network device names>``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The ``bond_interfaces`` key accepts a list of network device ``name`` values
from the configuration. This list may be empty.

``mtu: <MTU SizeBytes>``
^^^^^^^^^^^^^^^^^^^^^^^^

The MTU key represents a device's Maximum Transmission Unit, the largest size
packet or frame, specified in octets (eight-bit bytes), that can be sent in a
packet- or frame-based network. Specifying ``mtu`` is optional.

.. note::
   The possible supported values of a device's MTU are not available at
   configuration time. It's possible to specify a value too large or to
   small for a device, and may be ignored by the device.

``params: <Dictionary of key: value bonding parameter pairs>``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
The ``params`` key in a bond holds a dictionary of bonding parameters.
This dictionary may be empty. For more details on what the various bonding
parameters mean please read the Linux Kernel :file:`Bonding.txt`.

Valid ``params`` keys are:

  - ``active_slave``: Set bond attribute
  - ``ad_actor_key``: Set bond attribute
  - ``ad_actor_sys_prio``: Set bond attribute
  - ``ad_actor_system``: Set bond attribute
  - ``ad_aggregator``: Set bond attribute
  - ``ad_num_ports``: Set bond attribute
  - ``ad_partner_key``: Set bond attribute
  - ``ad_partner_mac``: Set bond attribute
  - ``ad_select``: Set bond attribute
  - ``ad_user_port_key``: Set bond attribute
  - ``all_slaves_active``: Set bond attribute
  - ``arp_all_targets``: Set bond attribute
  - ``arp_interval``: Set bond attribute
  - ``arp_ip_target``: Set bond attribute
  - ``arp_validate``: Set bond attribute
  - ``downdelay``: Set bond attribute
  - ``fail_over_mac``: Set bond attribute
  - ``lacp_rate``: Set bond attribute
  - ``lp_interval``: Set bond attribute
  - ``miimon``: Set bond attribute
  - ``mii_status``: Set bond attribute
  - ``min_links``: Set bond attribute
  - ``mode``: Set bond attribute
  - ``num_grat_arp``: Set bond attribute
  - ``num_unsol_na``: Set bond attribute
  - ``packets_per_slave``: Set bond attribute
  - ``primary``: Set bond attribute
  - ``primary_reselect``: Set bond attribute
  - ``queue_id``: Set bond attribute
  - ``resend_igmp``: Set bond attribute
  - ``slaves``: Set bond attribute
  - ``tlb_dynamic_lb``: Set bond attribute
  - ``updelay``: Set bond attribute
  - ``use_carrier``: Set bond attribute
  - ``xmit_hash_policy``: Set bond attribute

Bond example
^^^^^^^^^^^^

.. literalinclude:: ../../examples/network-config-v1-bonded-pair.yaml
   :language: yaml

Bridge
------

Type ``bridge`` requires the following keys:

- ``name``: Set the name of the bridge.
- ``bridge_interfaces``: Specify the ports of a bridge via their ``name``.
  This list may be empty.
- ``params``:  A list of bridge params. For more details, please read the
  ``bridge-utils-interfaces`` manpage.

Valid keys are:

  - ``bridge_ageing``: Set the bridge's ageing value.
  - ``bridge_bridgeprio``: Set the bridge device network priority.
  - ``bridge_fd``: Set the bridge's forward delay.
  - ``bridge_hello``: Set the bridge's hello value.
  - ``bridge_hw``: Set the bridge's MAC address.
  - ``bridge_maxage``: Set the bridge's maxage value.
  - ``bridge_maxwait``: Set how long network scripts should wait for the
    bridge to be up.
  - ``bridge_pathcost``: Set the cost of a specific port on the bridge.
  - ``bridge_portprio``: Set the priority of a specific port on the bridge.
  - ``bridge_ports``: List of devices that are part of the bridge.
  - ``bridge_stp``: Set spanning tree protocol on or off.
  - ``bridge_waitport``: Set amount of time in seconds to wait on specific
    ports to become available.

Bridge example
^^^^^^^^^^^^^^

.. literalinclude:: ../../examples/network-config-v1-bridge.yaml
   :language: yaml

VLAN
----

Type ``vlan`` requires the following keys:

- ``name``: Set the name of the VLAN
- ``vlan_link``: Specify the underlying link via its ``name``.
- ``vlan_id``: Specify the VLAN numeric id.

The following optional keys are supported:

``mtu: <MTU SizeBytes>``
^^^^^^^^^^^^^^^^^^^^^^^^

The MTU key represents a device's Maximum Transmission Unit, the largest size
packet or frame, specified in octets (eight-bit bytes), that can be sent in a
packet- or frame-based network.  Specifying ``mtu`` is optional.

.. note::
   The possible supported values of a device's MTU are not available at
   configuration time. It's possible to specify a value too large or to
   small for a device and may be ignored by the device.

VLAN example
^^^^^^^^^^^^

.. literalinclude:: ../../examples/network-config-v1-vlan.yaml
   :language: yaml

Nameserver
----------

Users can specify a ``nameserver`` type. Nameserver dictionaries include
the following keys:

- ``address``: List of IPv4 or IPv6 address of nameservers.
- ``search``: Optional. List of hostnames to include in the search path.
- ``interface``: Optional. Ties the nameserver definition to the specified
  interface. The value specified here must match the ``name`` of an interface
  defined in this config. If unspecified, this nameserver will be considered
  a global nameserver.

Nameserver example
^^^^^^^^^^^^^^^^^^

.. literalinclude:: ../../examples/network-config-v1-nameserver.yaml
   :language: yaml

Route
-----

Users can include static routing information as well. A ``route`` dictionary
has the following keys:

- ``destination``: IPv4 network address with CIDR netmask notation.
- ``gateway``: IPv4 gateway address with CIDR netmask notation.
- ``metric``: Integer which sets the network metric value for this route.

Route example
^^^^^^^^^^^^^

.. literalinclude:: ../../examples/network-config-v1-route.yaml
   :language: yaml

Subnet/IP
---------

For any network device (one of the "config types") users can define a list of
``subnets`` which contain ip configuration dictionaries. Multiple subnet
entries will create interface aliases, allowing a single interface to use
different ip configurations.

Valid keys for ``subnets`` include the following:

- ``type``: Specify the subnet type.
- ``control``: Specify 'manual', 'auto' or 'hotplug'. Indicates how the
  interface will be handled during boot.
- ``address``: IPv4 or IPv6 address. It may include CIDR netmask notation.
- ``netmask``: IPv4 subnet mask in dotted format or CIDR notation.
- ``broadcast`` : IPv4 broadcast address in dotted format. This is
  only rendered if :file:`/etc/network/interfaces` is used.
- ``gateway``: IPv4 address of the default gateway for this subnet.
- ``dns_nameservers``: Specify a list of IPv4 DNS server IPs.
- ``dns_search``: Specify a list of DNS search paths.
- ``routes``: Specify a list of routes for a given interface.

Subnet types are one of the following:

- ``dhcp4``: Configure this interface with IPv4 dhcp.
- ``dhcp``: Alias for ``dhcp4``.
- ``dhcp6``: Configure this interface with IPv6 dhcp.
- ``static``: Configure this interface with a static IPv4.
- ``static6``: Configure this interface with a static IPv6.
- ``ipv6_dhcpv6-stateful``: Configure this interface with ``dhcp6``.
- ``ipv6_dhcpv6-stateless``: Configure this interface with SLAAC and DHCP.
- ``ipv6_slaac``: Configure address with SLAAC.

When making use of ``dhcp`` or either of the ``ipv6_dhcpv6`` types,
no additional configuration is needed in the subnet dictionary.

Using ``ipv6_dhcpv6-stateless`` or ``ipv6_slaac`` allows the IPv6 address to be
automatically configured with StateLess Address AutoConfiguration (`SLAAC`_).
SLAAC requires support from the network, so verify that your cloud or network
offering has support before trying it out. With ``ipv6_dhcpv6-stateless``,
DHCPv6 is still used to fetch other subnet details such as gateway or DNS
servers. If you only want to discover the address, use ``ipv6_slaac``.

Subnet DHCP example
^^^^^^^^^^^^^^^^^^^

.. literalinclude:: ../../examples/network-config-v1-subnet-dhcp.yaml
   :language: yaml

Subnet static example
^^^^^^^^^^^^^^^^^^^^^

.. literalinclude:: ../../examples/network-config-v1-subnet-static.yaml
   :language: yaml

Multiple subnet example
^^^^^^^^^^^^^^^^^^^^^^^

The following will result in an ``interface0`` using DHCP and ``interface0:1``
using the static subnet configuration:

.. literalinclude:: ../../examples/network-config-v1-subnet-multiple.yaml
   :language: yaml

Subnet with routes example
^^^^^^^^^^^^^^^^^^^^^^^^^^

.. literalinclude:: ../../examples/network-config-v1-subnet-routes.yaml
   :language: yaml

Multi-layered configurations
============================

Complex networking sometimes uses layers of configuration. The syntax allows
users to build those layers one at a time. All of the virtual network devices
supported allow specifying an underlying device by their ``name`` value.

Bonded VLAN example
-------------------

.. literalinclude:: ../../examples/network-config-v1-bonded-vlan.yaml
   :language: yaml

Multiple VLAN example
---------------------

.. literalinclude:: ../../examples/network-config-v1-multiple-vlan.yaml
   :language: yaml

.. _SLAAC: https://tools.ietf.org/html/rfc4862

.. _YAML: https://yaml.org/type/int.html
