.. _network_config_eni:

Network configuration ENI (legacy)
**********************************

``Cloud-init`` supports reading and writing network config in the ``ENI``
format which is consumed by the ``ifupdown`` tool to parse and apply network
configuration.

As an input format this is **legacy**. In cases where ENI format is available
and another format is also available, ``cloud-init`` will prefer to use the
other, newer format.

This can happen in either :ref:`datasource_nocloud` or
:ref:`datasource_openstack` datasources.

Please reference existing `documentation`_ for the
:file:`/etc/network/interfaces(5)` format.

.. _documentation: http://manpages.ubuntu.com/manpages/trusty/en/man5/interfaces.5.html
