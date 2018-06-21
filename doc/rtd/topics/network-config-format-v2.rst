.. _network_config_v2:

Networking Config Version 2
===========================

Cloud-init's support for Version 2 network config is a subset of the
version 2 format defined for the `netplan`_ tool.  Cloud-init supports
both reading and writing of Version 2; the latter support requires a
distro with `netplan`_ present.

The ``network`` key has at least two required elements.  First
it must include ``version: 2``  and one or more of possible device
``types``..

Cloud-init will read this format from system config.
For example the following could be present in
``/etc/cloud/cloud.cfg.d/custom-networking.cfg``:

  network:
    version: 2
    ethernets: []

It may also be provided in other locations including the
:ref:`datasource_nocloud`, see :ref:`default_behavior` for other places.

Supported device ``types`` values are as follows:

- Ethernets (``ethernets``)
- Bonds (``bonds``)
- Bridges (``bridges``)
- VLANs (``vlans``)

Each type block contains device definitions as a map where the keys (called
"configuration IDs"). Each entry under the ``types`` may include IP and/or
device configuration.

Cloud-init does not current support ``wifis`` type that is present in native
`netplan`_.


Device configuration IDs
------------------------

The key names below the per-device-type definition maps (like ``ethernets:``)
are called "ID"s. They must be unique throughout the entire set of
configuration files. Their primary purpose is to serve as anchor names for
composite devices, for example to enumerate the members of a bridge that is
currently being defined.

There are two physically/structurally different classes of device definitions,
and the ID field has a different interpretation for each:

Physical devices

:   (Examples: ethernet, wifi) These can dynamically come and go between
    reboots and even during runtime (hotplugging). In the generic case, they
    can be selected by ``match:`` rules on desired properties, such as name/name
    pattern, MAC address, driver, or device paths. In general these will match
    any number of devices (unless they refer to properties which are unique
    such as the full path or MAC address), so without further knowledge about
    the hardware these will always be considered as a group.

    It is valid to specify no match rules at all, in which case the ID field is
    simply the interface name to be matched. This is mostly useful if you want
    to keep simple cases simple, and it's how network device configuration has
    been done for a long time.

    If there are ``match``: rules, then the ID field is a purely opaque name
    which is only being used  for references from definitions of compound
    devices in the config.

Virtual devices

:  (Examples: veth, bridge, bond) These are fully under the control of the
   config file(s) and the network stack. I. e. these devices are being created
   instead of matched. Thus ``match:`` and ``set-name:`` are not applicable for
   these, and the ID field is the name of the created virtual device.

Common properties for physical device types
-------------------------------------------

**match**: *<(mapping)>*

This selects a subset of available physical devices by various hardware
properties. The following configuration will then apply to all matching
devices, as soon as they appear. *All* specified properties must match.
The following properties for creating matches are supported:

**name**:  *<(scalar)>*

Current interface name. Globs are supported, and the primary use case
for matching on names, as selecting one fixed name can be more easily
achieved with having no ``match:`` at all and just using the ID (see
above). Note that currently only networkd supports globbing,
NetworkManager does not.

**macaddress**: *<(scalar)>*

Device's MAC address in the form "XX:XX:XX:XX:XX:XX". Globs are not allowed.

**driver**: *<(scalar)>*

Kernel driver name, corresponding to the ``DRIVER`` udev property.  Globs are
supported. Matching on driver is *only* supported with networkd.

**Examples**::

  # all cards on second PCI bus
  match:
    name: enp2*

  # fixed MAC address
  match:
    macaddress: 11:22:33:AA:BB:FF

  # first card of driver ``ixgbe``
  match:
    driver: ixgbe
    name: en*s0

**set-name**: *<(scalar)>*

When matching on unique properties such as path or MAC, or with additional
assumptions such as "there will only ever be one wifi device",
match rules can be written so that they only match one device. Then this
property can be used to give that device a more specific/desirable/nicer
name than the default from udev’s ifnames.  Any additional device that
satisfies the match rules will then fail to get renamed and keep the
original kernel name (and dmesg will show an error).

**wakeonlan**: *<(bool)>*

Enable wake on LAN. Off by default.


Common properties for all device types
--------------------------------------

**renderer**: *<(scalar)>*

Use the given networking backend for this definition. Currently supported are
``networkd`` and ``NetworkManager``. This property can be specified globally
in ``networks:``, for a device type (in e. g. ``ethernets:``) or
for a particular device definition. Default is ``networkd``.

.. note::

  Cloud-init only supports networkd backend if rendering version2 config
  to the instance.

**dhcp4**: *<(bool)>*

Enable DHCP for IPv4. Off by default.

**dhcp6**: *<(bool)>*

Enable DHCP for IPv6. Off by default.

**addresses**: *<(sequence of scalars)>*

Add static addresses to the interface in addition to the ones received
through DHCP or RA. Each sequence entry is in CIDR notation, i. e. of the
form ``addr/prefixlen`` . ``addr`` is an IPv4 or IPv6 address as recognized
by ``inet_pton``(3) and ``prefixlen`` the number of bits of the subnet.

Example: ``addresses: [192.168.14.2/24, 2001:1::1/64]``

**gateway4**: or **gateway6**: *<(scalar)>*

Set default gateway for IPv4/6, for manual address configuration. This
requires setting ``addresses`` too. Gateway IPs must be in a form
recognized by ``inet_pton(3)``

Example for IPv4: ``gateway4: 172.16.0.1``
Example for IPv6: ``gateway6: 2001:4::1``

**mtu**: *<MTU SizeBytes>*

The MTU key represents a device's Maximum Transmission Unit, the largest size
packet or frame, specified in octets (eight-bit bytes), that can be sent in a
packet- or frame-based network.  Specifying ``mtu`` is optional.

**nameservers**: *<(mapping)>*

Set DNS servers and search domains, for manual address configuration. There
are two supported fields: ``addresses:`` is a list of IPv4 or IPv6 addresses
similar to ``gateway*``, and ``search:`` is a list of search domains.

Example: ::

  nameservers:
    search: [lab, home]
    addresses: [8.8.8.8, FEDC::1]

**routes**: *<(sequence of mapping)>*

Add device specific routes.  Each mapping includes a ``to``, ``via`` key
with an IPv4 or IPv6 address as value.  ``metric`` is an optional value.

Example: ::

  routes:
   - to: 0.0.0.0/0
     via: 10.23.2.1
     metric: 3

Ethernets
~~~~~~~~~
Ethernet device definitions do not support any specific properties beyond the
common ones described above.

Bonds
~~~~~

**interfaces** *<(sequence of scalars)>*

All devices matching this ID list will be added to the bond.

Example: ::

  ethernets:
    switchports:
      match: {name: "enp2*"}
  [...]
  bonds:
    bond0:
      interfaces: [switchports]

**parameters**: *<(mapping)>*

Customization parameters for special bonding options.  Time values are specified
in seconds unless otherwise specified.

**mode**: *<(scalar)>*

Set the bonding mode used for the interfaces. The default is
``balance-rr`` (round robin). Possible values are ``balance-rr``,
``active-backup``, ``balance-xor``, ``broadcast``, ``802.3ad``,
``balance-tlb``, and ``balance-alb``.

**lacp-rate**: *<(scalar)>*

Set the rate at which LACPDUs are transmitted. This is only useful
in 802.3ad mode. Possible values are ``slow`` (30 seconds, default),
and ``fast`` (every second).

**mii-monitor-interval**: *<(scalar)>*

Specifies the interval for MII monitoring (verifying if an interface
of the bond has carrier). The default is ``0``; which disables MII
monitoring.

**min-links**: *<(scalar)>*

The minimum number of links up in a bond to consider the bond
interface to be up.

**transmit-hash-policy**: <*(scalar)>*

Specifies the transmit hash policy for the selection of slaves. This
is only useful in balance-xor, 802.3ad and balance-tlb modes.
Possible values are ``layer2``, ``layer3+4``, ``layer2+3``,
``encap2+3``, and ``encap3+4``.

**ad-select**: <*(scalar)>*

Set the aggregation selection mode. Possible values are ``stable``,
``bandwidth``, and ``count``. This option is only used in 802.3ad mode.

**all-slaves-active**: <*(bool)>*

If the bond should drop duplicate frames received on inactive ports,
set this option to ``false``. If they should be delivered, set this
option to ``true``. The default value is false, and is the desirable
behavior in most situations.

**arp-interval**: <*(scalar)>*

Set the interval value for how frequently ARP link monitoring should
happen. The default value is ``0``, which disables ARP monitoring.

**arp-ip-targets**: <*(sequence of scalars)>*

IPs of other hosts on the link which should be sent ARP requests in
order to validate that a slave is up. This option is only used when
``arp-interval`` is set to a value other than ``0``. At least one IP
address must be given for ARP link monitoring to function. Only IPv4
addresses are supported. You can specify up to 16 IP addresses. The
default value is an empty list.

**arp-validate**: <*(scalar)>*

Configure how ARP replies are to be validated when using ARP link
monitoring. Possible values are ``none``, ``active``, ``backup``,
and ``all``.

**arp-all-targets**: <*(scalar)>*

Specify whether to use any ARP IP target being up as sufficient for
a slave to be considered up; or if all the targets must be up. This
is only used for ``active-backup`` mode when ``arp-validate`` is
enabled. Possible values are ``any`` and ``all``.

**up-delay**: <*(scalar)>*

Specify the delay before enabling a link once the link is physically
up. The default value is ``0``.

**down-delay**: <*(scalar)>*

Specify the delay before disabling a link once the link has been
lost. The default value is ``0``.

**fail-over-mac-policy**: <*(scalar)>*

Set whether to set all slaves to the same MAC address when adding
them to the bond, or how else the system should handle MAC addresses.
The possible values are ``none``, ``active``, and ``follow``.

**gratuitious-arp**: <*(scalar)>*

Specify how many ARP packets to send after failover. Once a link is
up on a new slave, a notification is sent and possibly repeated if
this value is set to a number greater than ``1``. The default value
is ``1`` and valid values are between ``1`` and ``255``. This only
affects ``active-backup`` mode.

**packets-per-slave**: <*(scalar)>*

In ``balance-rr`` mode, specifies the number of packets to transmit
on a slave before switching to the next. When this value is set to
``0``, slaves are chosen at random. Allowable values are between
``0`` and ``65535``. The default value is ``1``. This setting is
only used in ``balance-rr`` mode.

**primary-reselect-policy**: <*(scalar)>*

Set the reselection policy for the primary slave. On failure of the
active slave, the system will use this policy to decide how the new
active slave will be chosen and how recovery will be handled. The
possible values are ``always``, ``better``, and ``failure``.

**learn-packet-interval**: <*(scalar)>*

Specify the interval between sending learning packets to each slave.
The value range is between ``1`` and ``0x7fffffff``. The default
value is ``1``. This option only affects ``balance-tlb`` and
``balance-alb`` modes.


Bridges
~~~~~~~

**interfaces**: <*(sequence of scalars)>*

All devices matching this ID list will be added to the bridge.

Example: ::

  ethernets:
    switchports:
      match: {name: "enp2*"}
  [...]
  bridges:
    br0:
      interfaces: [switchports]

**parameters**: <*(mapping)>*

Customization parameters for special bridging options.  Time values are specified
in seconds unless otherwise specified.

**ageing-time**: <*(scalar)>*

Set the period of time to keep a MAC address in the forwarding
database after a packet is received.

**priority**: <*(scalar)>*

Set the priority value for the bridge. This value should be an
number between ``0`` and ``65535``. Lower values mean higher
priority. The bridge with the higher priority will be elected as
the root bridge.

**forward-delay**: <*(scalar)>*

Specify the period of time the bridge will remain in Listening and
Learning states before getting to the Forwarding state. This value
should be set in seconds for the systemd backend, and in milliseconds
for the NetworkManager backend.

**hello-time**: <*(scalar)>*

Specify the interval between two hello packets being sent out from
the root and designated bridges. Hello packets communicate
information about the network topology.

**max-age**: <*(scalar)>*

Set the maximum age of a hello packet. If the last hello packet is
older than that value, the bridge will attempt to become the root
bridge.

**path-cost**: <*(scalar)>*

Set the cost of a path on the bridge. Faster interfaces should have
a lower cost. This allows a finer control on the network topology
so that the fastest paths are available whenever possible.

**stp**: <*(bool)>*

Define whether the bridge should use Spanning Tree Protocol. The
default value is "true", which means that Spanning Tree should be
used.


VLANs
~~~~~

**id**: <*(scalar)>*

VLAN ID, a number between 0 and 4094.

**link**: <*(scalar)>*

ID of the underlying device definition on which this VLAN gets
created.

Example: ::

  ethernets:
    eno1: {...}
  vlans:
    en-intra:
      id: 1
      link: eno1
      dhcp4: yes
    en-vpn:
      id: 2
      link: eno1
      address: ...


Examples
--------
Configure an ethernet device with networkd, identified by its name, and enable
DHCP: ::

  network:
    version: 2
    ethernets:
      eno1:
        dhcp4: true

This is a complex example which shows most available features: ::

  network:
    version: 2
    ethernets:
      # opaque ID for physical interfaces, only referred to by other stanzas
      id0:
        match:
          macaddress: 00:11:22:33:44:55
        wakeonlan: true
        dhcp4: true
        addresses:
          - 192.168.14.2/24
          - 2001:1::1/64
        gateway4: 192.168.14.1
        gateway6: 2001:1::2
        nameservers:
          search: [foo.local, bar.local]
          addresses: [8.8.8.8]
      lom:
        match:
          driver: ixgbe
        # you are responsible for setting tight enough match rules
        # that only match one device if you use set-name
        set-name: lom1
        dhcp6: true
      switchports:
        # all cards on second PCI bus; unconfigured by themselves, will be added
        # to br0 below
        match:
          name: enp2*
        mtu: 1280
    bonds:
      bond0:
        interfaces: [id0, lom]
    bridges:
      # the key name is the name for virtual (created) interfaces; no match: and
      # set-name: allowed
      br0:
        # IDs of the components; switchports expands into multiple interfaces
        interfaces: [wlp1s0, switchports]
        dhcp4: true
    vlans:
      en-intra:
        id: 1
        link: id0
        dhcp4: yes
    # static routes
    routes:
     - to: 0.0.0.0/0
       via: 11.0.0.1
       metric: 3

.. _netplan: https://launchpad.net/netplan
.. vi: textwidth=78
