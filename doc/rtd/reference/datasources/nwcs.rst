.. _datasource_nwcs:

NWCS
****

The NWCS datasource retrieves basic configuration values from the locally
accessible metadata service. All data is served over HTTP from the address
``169.254.169.254``.

Configuration
=============

The NWCS datasource can be configured as follows: ::

  datasource:
    NWCS:
      url: 'http://169.254.169.254'
      retries: 3
      timeout: 2
      wait: 2

* ``url``: The URL used to acquire the metadata configuration.
* ``retries``: Determines the number of times to attempt to connect to the
  metadata service.
* ``timeout``: Determines the timeout (in seconds) to wait for a response from
  the metadata service
* ``wait``: Determines the timeout in seconds to wait before retrying after
  accessible failure.
