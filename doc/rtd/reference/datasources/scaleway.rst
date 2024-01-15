.. _datasource_scaleway:

Scaleway
********
`Scaleway`_ datasource uses data provided by the Scaleway metadata service
to do initial configuration of the network services.

The metadata service is reachable at the following addresses :

* IPv4: ``169.254.42.42``
* IPv6: ``fd00:42::42``

Configuration
=============
Scaleway datasource may be configured in system configuration
(in `/etc/cloud cloud.cfg`) or by adding a file with the .cfg suffix containing
the following information in the `/etc/cloud.cfg.d` directory::

 datasource:
   Scaleway:
     retries: 3
     timeout: 10
     max_wait: 2
     metadata_urls:
       - alternate_url

* ``retries``

  Controls the maximum number of attempts to reach the metadata service.

* ``timeout``

  Controls the number of seconds to wait for a response from the metadata
  service for one protocol.

* ``max_wait``

  Controls the number of seconds to wait for a response from the metadata
  service for all protocols.

* ``metadata_urls``

  List of additional URLs to be used in an attempt to reach the metadata
  service in addition to the existing ones.

User Data
=========

cloud-init fetches user data using the metadata service using the `/user_data`
endpoint. Scaleway's documentation provides a detailed description on how to
use  `userdata`_. One can also interact with it using the `userdata api`_.


.. _Scaleway: https://www.scaleway.com
.. _userdata: https://www.scaleway.com/en/docs/compute/instances/api-cli/using-cloud-init/
.. _userdata api: https://www.scaleway.com/en/developers/api/instance/#path-user-data-list-user-data
