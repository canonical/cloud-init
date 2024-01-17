.. _datasource_digital_ocean:

DigitalOcean
************
.. warning::
    Deprecated in version 23.2. Use ``DataSourceConfigDrive`` instead.


The `DigitalOcean`_ datasource consumes the content served from DigitalOcean's
metadata service. This metadata service serves information about the
running droplet via http over the link local address ``169.254.169.254``. The
metadata API endpoints are fully described in the DigitalOcean
`metadata documentation`_.

Configuration
=============

DigitalOcean's datasource can be configured as follows: ::

  datasource:
    DigitalOcean:
      retries: 3
      timeout: 2

* ``retries``

  Specifies the number of times to attempt connection to the metadata service.

* ``timeout``

  Specifies the timeout (in seconds) to wait for a response from the
  metadata service.

.. _DigitalOcean: http://digitalocean.com/
.. _metadata documentation: https://developers.digitalocean.com/metadata/
