.. _datasource_none:

None
****

The data source ``None`` may be used when no other viable datasource is
present on disk. This has three primary use cases:

1. Testing cloud-init in an environment where no datasource is
   available.
2. As a fallback for when a datasource is otherwise intermittently
   unavailable.
3. Providing user data to cloud-init from on-disk configuration when
   no other datasource is present.

When the datasource is ``None``, cloud-init is unable to obtain or
render networking configuration. Additionally, when cloud-init
completes, a warning is logged that DataSourceNone is being used.

Configuration
=============

User data and meta data may be passed to cloud-init via system
configuration in :file:`/etc/cloud/cloud.cfg` or
:file:`/etc/cloud/cloud.cfg.d/`.

``userdata_raw``
----------------

A **string** containing the user data (including header) to be used by
cloud-init.

``metadata``
------------
The metadata to be used by cloud-init.

.. _datasource_none_example:

Example configuration
---------------------

.. code-block:: yaml

  datasource:
    None:
      metadata:
        local-hostname: "myhost.internal"
      userdata_raw: |
        #cloud-config
        runcmd:
        - echo 'mydata' > /var/tmp/mydata.txt
