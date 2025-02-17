.. _cce-datasources:

Configure datasources
*********************

These examples show datasource configuration options for various datasources.

The options shown are as follows:

* ``timeout``: The timeout value for a request at instance metadata service
* ``max_wait``: The length of time to wait (in seconds) before giving up on
  the instance metadata service. The actual total wait could be up to:
  ``len(resolvable_metadata_urls)*timeout``
* ``metadata_url``: List of URLs to check for instance metadata services. There
  are no default values for this field.

EC2
===

.. code-block:: yaml

    #cloud-config
    datasource:
      EC2:
        timeout : 50
        max_wait : 120
        metadata_url:
         - http://169.254.169.254:80
         - http://instance-data:8773

MAAS
====

.. code-block:: yaml

    #cloud-config
    datasource:
      MAAS:
        timeout : 50
        max_wait : 120
        metadata_url: http://mass-host.localdomain/source
        consumer_key: Xh234sdkljf
        token_key: kjfhgb3n
        token_secret: 24uysdfx1w4

NoCloud
=======

.. code-block:: yaml

    #cloud-config
    datasource:
      NoCloud:
        seedfrom: None
        fs_label: cidata
        user-data: |
          # This is the user-data verbatim
        meta-data:
          instance-id: i-87018aed
          local-hostname: myhost.internal

* ``seedfrom``: The default value is None. If found, it should contain a URL
  with ``<url>/user-data`` and ``<url>/meta-data``. For example:
  ``seedfrom: http://my.example.com/i-abcde/``
* ``fs_label``: The label on filesystems to be searched for NoCloud source
* ``user-data`` and ``meta-data`` (optional): Allows a datasource to be
  provided directly.

SmartOS
=======

.. code-block:: yaml

    #cloud-config
    datasource:
      SmartOS:
        # For KVM guests:
        # Smart OS datasource works over a serial console interacting with
        # a server on the other end. By default, the second serial console is the
        # device. SmartOS also uses a serial timeout of 60 seconds.
        serial_device: /dev/ttyS1
        serial_timeout: 60
        # For LX-Brand Zones guests:
        # Smart OS datasource works over a socket interacting with
        # the host on the other end. By default, the socket file is in
        # the native .zoncontrol directory.
        metadata_sockfile: /native/.zonecontrol/metadata.sock
        # a list of keys that will not be base64 decoded even if base64_all
        no_base64_decode: ['root_authorized_keys', 'motd_sys_info',
                           'iptables_disable']
        # a plaintext, comma delimited list of keys whose values are b64 encoded
        base64_keys: []
        # a boolean indicating that all keys not in 'no_base64_decode' are encoded
        base64_all: False

