.. _cce-reporting:

Reporting
*********

The following sets up 2 reporting endpoints; a 'webhook' and a 'log' type.

.. code-block:: yaml

    #cloud-config
    reporting:
      smtest:
        type: webhook
        endpoint: 'http://myhost:8000/'
        consumer_key: 'ckey_foo'
        consumer_secret: 'csecret_foo'
        token_key: 'tkey_foo'
        token_secret: 'tkey_foo'
      smlogger:
        type: log
        level: WARN
