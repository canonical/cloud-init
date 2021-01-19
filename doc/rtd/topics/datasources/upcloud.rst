.. _datasource_upcloud:

UpCloud
=============

The `UpCloud`_ datasource consumes information from UpCloud's `metadata
service`_. This metadata service serves information about the
running server via HTTP over the address 169.254.169.254 available in every
DHCP-configured interface. The metadata API endpoints are fully described in
UpCloud documentation at
`https://developers.upcloud.com/1.3/8-servers/#metadata-service
<https://developers.upcloud.com/1.3/8-servers/#metadata-service>`_.

Configuration
-------------

UpCloud's datasource can be configured as follows:

  datasource:
    UpCloud:
      retries: 5
      timeout: 2

- *retries*: Determines the number of times to attempt to connect to the
  metadata service
- *timeout*: Determines the timeout in seconds to wait for a response from the
  metadata service

.. _UpCloud: https://upcloud.com/
.. _metadata service: https://developers.upcloud.com/1.3/8-servers/#metadata-service
.. _Full documentation: https://upcloud.com/community/tutorials/upcloud-metadata-service/

.. vi: textwidth=78
