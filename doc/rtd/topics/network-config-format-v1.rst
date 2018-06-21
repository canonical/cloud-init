.. _network_config_v1:

Networking Config Version 1
===========================

This network configuration format lets users customize their instance's
networking interfaces by assigning subnet configuration, virtual device
creation (bonds, bridges, vlans) routes and DNS configuration.

Required elements of a Network Config Version 1 are ``config`` and
``version``.

Cloud-init will read this format from system config.
For example the following could be present in
``/etc/cloud/cloud.cfg.d/custom-networking.cfg``:

.. code-block:: yaml

  network:
    version: 1
    config:
    - type: physical
      name: eth0
      subnets:
        - type: dhcp

The :ref:`datasource_nocloud` datasource can also provide cloud-init
networking configuration in this Format.

Configuration Types
-------------------
Within the network ``config`` portion, users include a list of configuration
types.  The current list of support ``type`` values are as follows:

- Physical (``physical``)
- Bond (``bond``)
- Bridge (``bridge``)
- VLAN (``vlan``)
- Nameserver (``nameserver``)
- Route (``route``)

Physical, Bond, Bridge and VLAN types may also include IP configuration under
the key ``subnets``.

- Subnet/IP (``subnets``)


Physical
~~~~~~~~
The ``physical`` type configuration represents a "physical" network device,
typically Ethernet-based.  At least one of of these entries is required for
external network connectivity.  Type ``physical`` requires only one key:
``name``.  A ``physical`` device may contain some or all of the following
keys:

**name**: *<desired device name>*

A devices name must be less than 15 characters.  Names exceeding the maximum
will be truncated. This is a limitation of the Linux kernel network-device
structure.

**mac_address**: *<MAC Address>*

The MAC Address is a device unique identifier that most Ethernet-based network
devices possess.  Specifying a MAC Address is optional.


.. note::

  Cloud-init will handle the persistent mapping between a
  device's ``name`` and the ``mac_address``.

**mtu**: *<MTU SizeBytes>*

The MTU key represents a device's Maximum Transmission Unit, the largest size
packet or frame, specified in octets (eight-bit bytes), that can be sent in a
packet- or frame-based network.  Specifying ``mtu`` is optional.

.. note::

  The possible supported values of a device's MTU is not available at
  configuration time.  It's possible to specify a value too large or to
  small for a device and may be ignored by the device.


**Physical Example**::

  network:
    version: 1
    config:
      # Simple network adapter
      - type: physical
        name: interface0
        mac_address: 00:11:22:33:44:55
      # Second nic with Jumbo frames
      - type: physical
        name: jumbo0
        mac_address: aa:11:22:33:44:55
        mtu: 9000
      # 10G pair
      - type: physical
        name: gbe0
        mac_address: cd:11:22:33:44:00
      - type: physical
        name: gbe1
        mac_address: cd:11:22:33:44:02

Bond
~~~~
A ``bond`` type will configure a Linux software Bond with one or more network
devices.  A ``bond`` type requires the following keys:

**name**: *<desired device name>*

A devices name must be less than 15 characters.  Names exceeding the maximum
will be truncated. This is a limitation of the Linux kernel network-device
structure.

**mac_address**: *<MAC Address>*

When specifying MAC Address on a bond this value will be assigned to the bond
device and may be different than the MAC address of any of the underlying
bond interfaces.  Specifying a MAC Address is optional.  If ``mac_address`` is
not present, then the bond will use one of the MAC Address values from one of
the bond interfaces.


**bond_interfaces**: *<List of network device names>*

The ``bond_interfaces`` key accepts a list of network device ``name`` values
from the configuration.  This list may be empty.

**mtu**: *<MTU SizeBytes>*

The MTU key represents a device's Maximum Transmission Unit, the largest size
packet or frame, specified in octets (eight-bit bytes), that can be sent in a
packet- or frame-based network.  Specifying ``mtu`` is optional.

.. note::

  The possible supported values of a device's MTU is not available at
  configuration time.  It's possible to specify a value too large or to
  small for a device and may be ignored by the device.

**params**:  *<Dictionary of key: value bonding parameter pairs>*

The ``params`` key in a bond holds a dictionary of bonding parameters.
This dictionary may be empty. For more details on what the various bonding
parameters mean please read the Linux Kernel Bonding.txt.

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

**Bond Example**::

   network:
    version: 1
    config:
      # Simple network adapter
      - type: physical
        name: interface0
        mac_address: 00:11:22:33:44:55
      # 10G pair
      - type: physical
        name: gbe0
        mac_address: cd:11:22:33:44:00
      - type: physical
        name: gbe1
        mac_address: cd:11:22:33:44:02
      - type: bond
        name: bond0
        bond_interfaces:
          - gbe0
          - gbe1
        params:
          bond-mode: active-backup

Bridge
~~~~~~
Type ``bridge`` requires the following keys:

- ``name``: Set the name of the bridge.
- ``bridge_interfaces``: Specify the ports of a bridge via their ``name``.
  This list may be empty.
- ``params``:  A list of bridge params.  For more details, please read the
  bridge-utils-interfaces manpage.

Valid keys are:

  - ``bridge_ageing``: Set the bridge's ageing value.
  - ``bridge_bridgeprio``: Set the bridge device network priority.
  - ``bridge_fd``: Set the bridge's forward delay.
  - ``bridge_hello``: Set the bridge's hello value.
  - ``bridge_hw``: Set the bridge's MAC address.
  - ``bridge_maxage``: Set the bridge's maxage value.
  - ``bridge_maxwait``:  Set how long network scripts should wait for the
    bridge to be up.
  - ``bridge_pathcost``:  Set the cost of a specific port on the bridge.
  - ``bridge_portprio``:  Set the priority of a specific port on the bridge.
  - ``bridge_ports``:  List of devices that are part of the bridge.
  - ``bridge_stp``:  Set spanning tree protocol on or off.
  - ``bridge_waitport``: Set amount of time in seconds to wait on specific
    ports to become available.


**Bridge Example**::

   network:
    version: 1
    config:
      # Simple network adapter
      - type: physical
        name: interface0
        mac_address: 00:11:22:33:44:55
      # Second nic with Jumbo frames
      - type: physical
        name: jumbo0
        mac_address: aa:11:22:33:44:55
        mtu: 9000
      - type: bridge
        name: br0
        bridge_interfaces:
          - jumbo0
        params:
          bridge_ageing: 250
          bridge_bridgeprio: 22
          bridge_fd: 1
          bridge_hello: 1
          bridge_maxage: 10
          bridge_maxwait: 0
          bridge_pathcost:
            - jumbo0 75
          bridge_pathprio:
            - jumbo0 28
          bridge_stp: 'off'
          bridge_maxwait:
            - jumbo0 0


VLAN
~~~~
Type ``vlan`` requires the following keys:

- ``name``: Set the name of the VLAN
- ``vlan_link``: Specify the underlying link via its ``name``.
- ``vlan_id``: Specify the VLAN numeric id.

The following optional keys are supported:

**mtu**: *<MTU SizeBytes>*

The MTU key represents a device's Maximum Transmission Unit, the largest size
packet or frame, specified in octets (eight-bit bytes), that can be sent in a
packet- or frame-based network.  Specifying ``mtu`` is optional.

.. note::

  The possible supported values of a device's MTU is not available at
  configuration time.  It's possible to specify a value too large or to
  small for a device and may be ignored by the device.


**VLAN Example**::

   network:
     version: 1
     config:
       # Physical interfaces.
       - type: physical
         name: eth0
         mac_address: "c0:d6:9f:2c:e8:80"
       # VLAN interface.
       - type: vlan
         name: eth0.101
         vlan_link: eth0
         vlan_id: 101
         mtu: 1500

Nameserver
~~~~~~~~~~

Users can specify a ``nameserver`` type.  Nameserver dictionaries include
the following keys:

- ``address``: List of IPv4 or IPv6 address of nameservers.
- ``search``: List of of hostnames to include in the resolv.conf search path.

**Nameserver Example**::

  network:
    version: 1
    config:
      - type: physical
        name: interface0
        mac_address: 00:11:22:33:44:55
        subnets:
           - type: static
             address: 192.168.23.14/27
             gateway: 192.168.23.1
      - type: nameserver:
        address:
          - 192.168.23.2
          - 8.8.8.8
        search:
          - exemplary



Route
~~~~~

Users can include static routing information as well.  A ``route`` dictionary
has the following keys:

- ``destination``: IPv4 network address with CIDR netmask notation.
- ``gateway``: IPv4 gateway address with CIDR netmask notation.
- ``metric``: Integer which sets the network metric value for this route.

**Route Example**::

  network:
    version: 1
    config:
      - type: physical
        name: interface0
        mac_address: 00:11:22:33:44:55
        subnets:
           - type: static
             address: 192.168.23.14/24
             gateway: 192.168.23.1
      - type: route
        destination: 192.168.24.0/24
        gateway: 192.168.24.1
        metric: 3

Subnet/IP
~~~~~~~~~

For any network device (one of the Config Types) users can define a list of
``subnets`` which contain ip configuration dictionaries.  Multiple subnet
entries will create interface alias allowing a single interface to use
different ip configurations.

Valid keys for ``subnets`` include the following:

- ``type``: Specify the subnet type.
- ``control``: Specify manual, auto or hotplug.  Indicates how the interface
  will be handled during boot.
- ``address``: IPv4 or IPv6 address.  It may include CIDR netmask notation.
- ``netmask``: IPv4 subnet mask in dotted format or CIDR notation.
- ``gateway``: IPv4 address of the default gateway for this subnet.
- ``dns_nameserver``: Specify a list of IPv4 dns server IPs to end up in
  resolv.conf.
- ``dns_search``: Specify a list of search paths to be included in
  resolv.conf.
- ``routes``:  Specify a list of routes for a given interface


Subnet types are one of the following:

- ``dhcp4``: Configure this interface with IPv4 dhcp.
- ``dhcp``: Alias for ``dhcp4``
- ``dhcp6``: Configure this interface with IPv6 dhcp.
- ``static``: Configure this interface with a static IPv4.
- ``static6``: Configure this interface with a static IPv6 .

When making use of ``dhcp`` types, no additional configuration is needed in
the subnet dictionary.


**Subnet DHCP Example**::

   network:
     version: 1
     config:
       - type: physical
         name: interface0
         mac_address: 00:11:22:33:44:55
         subnets:
           - type: dhcp


**Subnet Static Example**::

   network:
     version: 1
     config:
       - type: physical
         name: interface0
         mac_address: 00:11:22:33:44:55
         subnets:
           - type: static
             address: 192.168.23.14/27
             gateway: 192.168.23.1
             dns_nameservers:
               - 192.168.23.2
               - 8.8.8.8
             dns_search:
               - exemplary.maas

The following will result in an ``interface0`` using DHCP and ``interface0:1``
using the static subnet configuration.

**Multiple subnet Example**::

   network:
     version: 1
     config:
       - type: physical
         name: interface0
         mac_address: 00:11:22:33:44:55
         subnets:
           - type: dhcp
           - type: static
             address: 192.168.23.14/27
             gateway: 192.168.23.1
             dns_nameservers:
               - 192.168.23.2
               - 8.8.8.8
             dns_search:
               - exemplary

**Subnet with routes Example**::

   network:
     version: 1
     config:
       - type: physical
         name: interface0
         mac_address: 00:11:22:33:44:55
         subnets:
           - type: dhcp
           - type: static
             address: 10.184.225.122
             netmask: 255.255.255.252
             routes:
               - gateway: 10.184.225.121
                 netmask: 255.240.0.0
                 network: 10.176.0.0
               - gateway: 10.184.225.121
                 netmask: 255.240.0.0
                 network: 10.208.0.0


Multi-layered configurations
----------------------------

Complex networking sometimes uses layers of configuration.  The syntax allows
users to build those layers one at a time.  All of the virtual network devices
supported allow specifying an underlying device by their ``name`` value.

**Bonded VLAN Example**::

  network:
    version: 1
    config:
      # 10G pair
      - type: physical
        name: gbe0
        mac_address: cd:11:22:33:44:00
      - type: physical
        name: gbe1
        mac_address: cd:11:22:33:44:02
      # Bond.
      - type: bond
        name: bond0
        bond_interfaces:
          - gbe0
          - gbe1
        params:
          bond-mode: 802.3ad
          bond-lacp-rate: fast
      # A Bond VLAN.
      - type: vlan
          name: bond0.200
          vlan_link: bond0
          vlan_id: 200
          subnets:
              - type: dhcp4

More Examples
-------------
Some more examples to explore the various options available.

**Multiple VLAN example**::

  network:
    version: 1
    config:
    - id: eth0
      mac_address: d4:be:d9:a8:49:13
      mtu: 1500
      name: eth0
      subnets:
      - address: 10.245.168.16/21
        dns_nameservers:
        - 10.245.168.2
        gateway: 10.245.168.1
        type: static
      type: physical
    - id: eth1
      mac_address: d4:be:d9:a8:49:15
      mtu: 1500
      name: eth1
      subnets:
      - address: 10.245.188.2/24
        dns_nameservers: []
        type: static
      type: physical
    - id: eth1.2667
      mtu: 1500
      name: eth1.2667
      subnets:
      - address: 10.245.184.2/24
        dns_nameservers: []
        type: static
      type: vlan
      vlan_id: 2667
      vlan_link: eth1
    - id: eth1.2668
      mtu: 1500
      name: eth1.2668
      subnets:
      - address: 10.245.185.1/24
        dns_nameservers: []
        type: static
      type: vlan
      vlan_id: 2668
      vlan_link: eth1
    - id: eth1.2669
      mtu: 1500
      name: eth1.2669
      subnets:
      - address: 10.245.186.1/24
        dns_nameservers: []
        type: static
      type: vlan
      vlan_id: 2669
      vlan_link: eth1
    - id: eth1.2670
      mtu: 1500
      name: eth1.2670
      subnets:
      - address: 10.245.187.2/24
        dns_nameservers: []
        type: static
      type: vlan
      vlan_id: 2670
      vlan_link: eth1
    - address: 10.245.168.2
      search:
      - dellstack
      type: nameserver

.. vi: textwidth=78
