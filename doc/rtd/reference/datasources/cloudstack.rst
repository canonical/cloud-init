.. _datasource_cloudstack:

CloudStack
**********

`Apache CloudStack`_ exposes user data, metadata, user password, and account
SSH key through the ``virtual router``. The datasource obtains the ``virtual
router`` address via DHCP lease information given to the instance.
For more details on metadata and user data, refer to the
`CloudStack Administrator Guide`_.

The following URLs provide to access user data and metadata from the Virtual
Machine. ``data-server.`` is a well-known hostname provided by the CloudStack
``virtual router`` that points to the next ``UserData`` server (which is
usually also the ``virtual router``).

.. code-block:: bash

    http://data-server./latest/user-data
    http://data-server./latest/meta-data
    http://data-server./latest/meta-data/{metadata type}

If ``data-server.`` cannot be resolved, ``cloud-init`` will try to obtain the
``virtual router``'s address from the system's DHCP leases. If that fails,
it will use the system's default gateway.

Configuration
=============

The following configuration can be set for the datasource in system
configuration (in :file:`/etc/cloud/cloud.cfg` or
:file:`/etc/cloud/cloud.cfg.d/`).

The settings that may be configured are:

* :command:`max_wait`

  The maximum amount of clock time in seconds that should be spent searching
  ``metadata_urls``. A value less than zero will result in only one request
  being made, to the first in the list.

  Default: 120

* :command:`timeout`

  The timeout value provided to ``urlopen`` for each individual http request.
  This is used both when selecting a ``metadata_url`` and when crawling
  the metadata service.

  Default: 50

Example
-------

An example configuration with the default values is provided below:

.. code-block:: yaml

   datasource:
     CloudStack:
       max_wait: 120
       timeout: 50


.. _Apache CloudStack: http://cloudstack.apache.org/
.. _CloudStack Administrator Guide: https://docs.cloudstack.apache.org/en/latest/adminguide/virtual_machines.html#user-data-and-meta-data
