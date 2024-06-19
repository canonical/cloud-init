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

* ``metadata_url``

  Specifies the URL to retrieve the VPS meta-data. (optional)

* ``userdata_url``

  Specifies the URL to retrieve the user-data. (optional)

* ``vendordata_url``

  Specifies the URL to retrieve the vendor-data. (optional)

.. note::
   ``{id}`` in URLs is system-uuid DMI value.

.. _Aeza: https://wiki.aeza.net/cloud-init
