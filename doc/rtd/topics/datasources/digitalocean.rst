Digital Ocean
=============

The `DigitalOcean`_ datasource consumes the content served from DigitalOcean's
`metadata service`_.  This metadata service serves information about the
running droplet via HTTP over the link local address 169.254.169.254.  The
metadata API endpoints are fully described at
`https://developers.digitalocean.com/metadata/
<https://developers.digitalocean.com/metadata/>`_.

Configuration
-------------

DigitalOcean's datasource can be configured as follows:

  datasource:
    DigitalOcean:
      retries: 3
      timeout: 2

- *retries*: Determines the number of times to attempt to connect to the metadata service
- *timeout*: Determines the timeout in seconds to wait for a response from the metadata service

.. _DigitalOcean: http://digitalocean.com/
.. _metadata service: https://developers.digitalocean.com/metadata/
.. _Full documentation: https://developers.digitalocean.com/metadata/

.. vi: textwidth=78
