.. _datasource_aeza:

Aeza
****

The `Aeza`_ datasource consumes the content served from Aeza's metadata
service. This metadata service serves information about the running VPS
via http at ``77.221.156.49``.

Configuration
=============

Aeza's datasource can be configured as follows: ::

  datasource:
    Aeza:
      metadata_url: "http://77.221.156.49/v1/cloudinit/{id}/meta-data"
      userdata_url: "http://77.221.156.49/v1/cloudinit/{id}/user-data"
      vendordata_url: "http://77.221.156.49/v1/cloudinit/{id}/vendor-data"
      retries: 60
      timeout: 2
      wait_retry: 2

* ``metadata_url``

  Specifies the URL to retrieve the VPS meta-data. (optional)

* ``userdata_url``

  Specifies the URL to retrieve the user-data. (optional)

* ``vendordata_url``

  Specifies the URL to retrieve the vendor-data. (optional)

* ``retries``

  The number of times the data retrieval operation should be retried in case of failures. (optional)

* ``timeout``

  The maximum number of seconds to wait for a response from the server for each attempt. (optional)

* ``wait_retry``

  The number of seconds to wait between retries. (optional)

.. note::
   ``{id}`` in URLs is system-uuid DMI value.

.. _Aeza: https://aeza.net/
