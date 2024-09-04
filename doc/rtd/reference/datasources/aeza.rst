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
      metadata_url: "http://77.221.156.49/v1/cloudinit/{id}/"

* ``metadata_url``

  Specifies the URL to retrieve the VPS meta-data. (optional)
  Default: ``http://77.221.156.49/v1/cloudinit/{id}/``

* ``timeout``

  The timeout value provided to ``urlopen`` for each individual http request.
  This is used both when selecting a ``metadata_url`` and when crawling the
  metadata service.

  Default: 10

* ``retries``

  The number of retries that should be attempted for an http request. This
  value is used only after ``metadata_url`` is selected.

  Default: 5

.. note::
   ``{id}`` in URLs is system-uuid DMI value.

.. _Aeza: https://wiki.aeza.net/cloud-init
