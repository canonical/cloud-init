.. _datasource_upcloud:

UpCloud
=============

The `UpCloud`_ datasource consumes information from UpCloud's `metadata
service`_. This metadata service serves information about the
running server via HTTP over the address 169.254.169.254 available in every
DHCP-configured interface. The metadata API endpoints are fully described in
UpCloud API documentation at
`https://developers.upcloud.com/1.3/8-servers/#metadata-service
<https://developers.upcloud.com/1.3/8-servers/#metadata-service>`_.

Providing user-data
-------------------

When creating a server, user-data is provided by specifying it as `user_data`
in the API or via the server creation tool in the control panel. User-data is
immutable during server's lifetime and can be removed by deleting the server.

.. _UpCloud: https://upcloud.com/
.. _metadata service: https://upcloud.com/community/tutorials/upcloud-metadata-service/

.. vi: textwidth=78
