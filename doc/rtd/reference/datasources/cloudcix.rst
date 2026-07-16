.. _datasource_cloudcix:

CloudCIX
========

`CloudCIX`_ serves meta-data through an internal server, accessible at
``http://169.254.169.254/v1``. The meta-data and user-data can be fetched at
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
  instance metadata service
- *timeout*: How long in seconds to wait for a response from the meta-data
  service
- *sec_between_retries*: How long in seconds to wait between consecutive
  requests to the instance metadata service

_CloudCIX: https://www.cloudcix.com/
