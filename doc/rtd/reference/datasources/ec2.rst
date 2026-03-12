.. _datasource_ec2:

Amazon EC2
**********

The EC2 datasource is the oldest and most widely used datasource that
``cloud-init`` supports. Various clouds have been designed to emulate
EC2. Many of these clouds use the same datasource including Brightbox,
E24Cloud, Outscale, Tilaa, and Zscale.

This datasource interacts with a *magic* IP provided
to the instance by the cloud provider (typically this IP is
``169.254.169.254``). At this IP a http server is provided to the
instance so that the instance can make calls to get instance user-data and
instance-data.

The instance metadata service is accessible via the following URL: ::

    GET http://169.254.169.254/2009-04-04/meta-data/
    ami-id
    ami-launch-index
    ami-manifest-path
    block-device-mapping/
    hostname
    instance-id
    instance-type
    local-hostname
    local-ipv4
    placement/
    public-hostname
    public-ipv4
    public-keys/
    reservation-id
    security-groups

User-data is accessible via the following URL: ::

    GET http://169.254.169.254/2009-04-04/user-data
    1234,fred,reboot,true | 4512,jimbo, | 173,,,

Note that there are multiple EC2 instance metadata service versions of this
data provided to instances. ``Cloud-init`` attempts to use the most recent API
version it supports in order to get the latest API features and
``instance-data``. If a given API version is not exposed to the instance, those
API features will be unavailable to the instance.

+----------------+----------------------------------------------------------+
+ EC2 version    | supported instance-data/feature                          |
+================+==========================================================+
+ **2021-03-23** | Required for Instance tag support. This feature must be  |
|                | enabled individually on each instance. See the           |
|                | `EC2 tags user guide`_.                                  |
+----------------+----------------------------------------------------------+
| **2016-09-02** | Required for secondary IP address support.               |
+----------------+----------------------------------------------------------+
| **2009-04-04** | Minimum supports EC2 API version for meta-data and       |
|                | user-data.                                               |
+----------------+----------------------------------------------------------+

To see which versions are supported by your cloud provider use the following
URL: ::

    GET http://169.254.169.254/
    1.0
    2007-01-19
    2007-03-01
    2007-08-29
    2007-10-10
    2007-12-15
    2008-02-01
    2008-09-01
    2009-04-04
    ...
    latest


Configuration settings
======================

The following configuration can be set for the datasource in system
configuration (in :file:`/etc/cloud/cloud.cfg` or
:file:`/etc/cloud/cloud.cfg.d/`).

The settings that may be configured are:

``metadata_urls``
-----------------

This list of URLs will be searched for an EC2 instance metadata service. The
first entry that successfully returns a 200 response for
``<url>/<version>/meta-data/instance-id`` will be selected.

Default: [``'http://169.254.169.254'``, ``'http://[fd00:ec2::254]'``,
``'http://instance-data.:8773'``].

``max_wait``
------------

The maximum amount of clock time in seconds that should be spent searching
``metadata_urls``. A value less than zero will result in only one request
being made, to the first in the list.

Default: 120

``timeout``
-----------

The timeout value provided to ``urlopen`` for each individual http request.
This is used both when selecting a ``metadata_url`` and when crawling the
instance metadata service.

Default: 50

``apply_full_imds_network_config``
----------------------------------

Boolean (default: True) to allow ``cloud-init`` to configure any secondary
NICs and secondary IPs described by the instance metadata service. All network
interfaces are configured with DHCP (v4) to obtain a primary IPv4 address and
route. Interfaces which have a non-empty ``ipv6s`` list will also enable
DHCPv6 to obtain a primary IPv6 address and route. The DHCP response (v4 and
v6) return an IP that matches the first element of ``local-ipv4s`` and
``ipv6s`` lists respectively. All additional values (secondary addresses) in
the static IP lists will be added to the interface.

An example configuration with the default values is provided below:

.. code-block:: yaml

   datasource:
     Ec2:
       metadata_urls: ["http://169.254.169.254:80", "http://instance-data:8773"]
       max_wait: 120
       timeout: 50
       apply_full_imds_network_config: true

Notes
=====

 * There are 2 types of EC2 instances, network-wise: Virtual Private
   Cloud (VPC) ones and Classic ones (also known as non-VPC). One major
   difference between them is that Classic instances have their MAC address
   changed on stop/restart operations, so ``cloud-init`` will recreate the
   network config file for EC2 Classic instances every boot. On VPC instances
   this file is generated only on the first boot of the instance.
   The check for the instance type is performed by ``is_classic_instance()``
   method.

 * For EC2 instances with multiple network interfaces (NICs) attached, DHCP4
   will be enabled to obtain the primary private IPv4 address of those NICs.
   Wherever DHCP4 or DHCP6 is enabled for a NIC, a DHCP route-metric will be
   added with the value of ``<device-number + 1> * 100`` to ensure DHCP
   routes on the primary NIC are preferred to any secondary NICs.
   For example: the primary NIC will have a DHCP route-metric of 100,
   the next NIC will have 200.

 * For EC2 instances with multiple NICs, policy-based routing will be
   configured on secondary NICs / secondary IPs to ensure outgoing packets
   are routed via the correct interface.
   This network configuration is only applied on distros using Netplan and
   at first boot only but it can be configured to be applied on every boot
   and when NICs are hotplugged, see :ref:`events`.

.. _EC2 tags user guide: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/Using_Tags.html
