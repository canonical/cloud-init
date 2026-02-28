.. _datasource_akamai:

Akamai
******

The Akamai datasource provides an interface to consume ``instance-data`` on the
`Akamai Connected Cloud`_.  This service is available at ``169.254.169.254``
and ``fd00:a9fe:a9fe::1`` from within the instance.

.. _Akamai Connected Cloud: https://www.linode.com/docs/


Configuration
=============

The Akamai datasource supports the following configuration, although in normal
use no changes to the defaults should be necessary: ::

 datasource:
   Akamai:
     base_urls:
       ipv4: http://169.254.169.254
       ipv6: http://[fd00:a9fe:a9fe::1]
     paths:
         token: /v1/token
         metadata: /v1/instance
         userdata: /v1/user-data
     allow_local_stage: True
     allow_init_stage: True
     allow_dhcp: True
     allow_ipv4: True
     allow_ipv6: True
     preferred_mac_prefixes:
     - f2:3

* ``base_urls``

  The URLs used to access the instance metadata service over IPv4 and IPv6
  respectively.

* ``paths``

  The paths used to reach specific endpoints within the service.

* ``allow_local_stage``

  Allows this datasource to fetch data during the local stage.  This can be
  disabled if your image does not want ephemeral networking used.

* ``allow_init_stage``

  Allows this datasource to fetch data during the init stage, once networking
  is online.

* ``allow_dhcp``

  Allows this datasource to use DHCP to find an IPv4 address to fetch
  ``instance-data`` with during the local stage.

* ``allow_ipv4``

  Allow the use of IPv4 when fetching ``instance-data`` during any stage.

* ``allow_ipv6``

  Allows the use of IPv6 when fetching ``instance-data`` during any stage.

* ``preferred_mac_prefixes``

  A list of MAC Address prefixes that will be preferred when selecting an
  interface to use for ephemeral networking.  This is ignored during the init
  stage.

Configuration Overrides
^^^^^^^^^^^^^^^^^^^^^^^

In some circumstances, the Akamai platform may send configurations overrides to
instances via dmi data to prevent certain behavior that may not be supported
based on the instance's region or configuration.  For example, if deploying an
instance in a region that does not yet support ``instance-data``, both the
local and init stages will be disabled, preventing cloud-init from attempting
to fetch ``instance-data``.  Configuration overrides sent this way will appears
in the ``baseboard-serial-number`` field.
