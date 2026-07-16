.. _datasource_scaleway:

Scaleway
********
`Scaleway`_ datasource uses data provided by the Scaleway instance metadata
service to do initial configuration of the network services.

The instance metadata service is reachable at the following addresses :

* IPv4: ``169.254.42.42``
* IPv6: ``fd00:42::42``

Configuration
=============
Scaleway datasource may be configured in system configuration
(in :file:`/etc/cloud/cloud.cfg`) or by adding a file with the .cfg suffix
containing the following information in the `/etc/cloud.cfg.d` directory::

 datasource:
   Scaleway:
     retries: 3
     timeout: 10
     max_wait: 2
     metadata_urls:
       - alternate_url

* ``retries``

  Controls the maximum number of attempts to reach the instance metadata
  service.

* ``timeout``

  Controls the number of seconds to wait for a response from the instance
  metadata service for one protocol.

* ``max_wait``

  Controls the number of seconds to wait for a response from the instance
  metadata service for all protocols.

* ``metadata_urls``

  List of additional URLs to be used in an attempt to reach the instance
  metadata service in addition to the existing ones.

User-data
=========

cloud-init fetches user-data using the instance metadata service using the
`/user_data` endpoint. Scaleway's documentation provides a detailed description
on how to use `user-data`_. One can also interact with it using the
`user-data api`_.


.. _Scaleway: https://www.scaleway.com
.. _user-data: https://www.scaleway.com/en/docs/compute/instances/api-cli/using-cloud-init/
.. _user-data api: https://www.scaleway.com/en/developers/api/instance/#path-user-data-list-user-data
