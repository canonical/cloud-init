.. _datasource_vultr:

Vultr
=====

The `Vultr`_ datasource retrieves basic configuration values from the locally
accessible `metadata service`_. All data is served over HTTP from the address
169.254.169.254. The endpoints are documented in
`https://www.vultr.com/metadata/
<https://www.vultr.com/metadata/>`_

Configuration
-------------

Vultr's datasource can be configured as follows:

  datasource:
    Vultr:
      url: 'http://169.254.169.254'
      retries: 3
      timeout: 2
      wait: 2

- *url*: The URL used to acquire the metadata configuration from
- *retries*: Determines the number of times to attempt to connect to the
  metadata service
- *timeout*: Determines the timeout in seconds to wait for a response from the
  metadata service
- *wait*: Determines the timeout in seconds to wait before retrying after
  accessible failure

.. _Vultr: https://www.vultr.com/
.. _metadata service: https://www.vultr.com/metadata/

.. vi: textwidth=79
