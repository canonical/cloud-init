.. _datasource_upcloud:

UpCloud
*******

The `UpCloud`_ datasource consumes information from UpCloud's
`instance metadata service`_. This instance metadata service serves information
about the running server via HTTP over the address ``169.254.169.254``
available in every DHCP-configured interface. The meta-data API endpoints are
fully described in `UpCloud API documentation`_.

Providing user-data
===================

When creating a server, user-data is provided by specifying it as
``user_data`` in the API or via the server creation tool in the control panel.
User-data is immutable during the server's lifetime, and can be removed by
deleting the server.

.. _UpCloud: https://upcloud.com/
.. _instance metadata service: https://upcloud.com/community/tutorials/upcloud-metadata-service/
.. _UpCloud API documentation: https://developers.upcloud.com/1.3/8-servers/#metadata-service
