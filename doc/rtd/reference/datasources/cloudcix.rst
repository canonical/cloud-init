.. _datasource_cloudcix:

CloudCIX
========

`CloudCIX`_ serves metadata through an internal server, accessible at
``http://169.254.169.254/v1``. The metadata and userdata can be fetched at
the ``/metadata`` and ``/userdata`` paths respectively.

CloudCIX instances are identified by the dmi product name `CloudCIX`.

Configuration
-------------

CloudCIX datasource has the following config options:

::

  datasource:
    CloudCIX:
      retries: 3
      timeout: 2
      sec_between_retries: 2


- *retries*: The number of times the datasource should try to connect to the
  metadata service
- *timeout*: How long in seconds to wait for a response from the metadata
  service
- *wait*: How long in seconds to wait between consecutive requests to the
  metadata service

_CloudCIX: https://www.cloudcix.com/
