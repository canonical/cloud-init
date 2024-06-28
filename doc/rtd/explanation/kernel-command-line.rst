Kernel command line
*******************

Providing configuration data via the kernel command line is somewhat of a last
resort, since this method only supports
:ref:`cloud config<user_data_formats-cloud_config>` starting with
`#cloud-config`, and many datasources do not support injecting kernel
command line arguments without modifying the bootloader.

Despite the limitations of using the kernel command line, cloud-init supports
some use-cases.

Note that this page describes kernel command line behavior that applies
to all clouds. To provide a local configuration with an image using kernel
command line, see :ref:`datasource NoCloud<datasource_nocloud>` which provides
more configuration options.

.. _kernel_datasource_override:

Datasource discovery override
=============================

During boot, cloud-init must identify which datasource it is running on
(OpenStack, AWS, Azure, GCP, etc). This discovery step can be optionally
overridden by specifying the datasource name, such as:

.. code-block:: text

   root=/dev/sda ro ds=openstack

Kernel cloud-config-url configuration
=====================================

In order to allow an ephemeral, or otherwise pristine image to receive some
configuration, ``cloud-init`` can read a URL directed by the kernel command
line and proceed as if its data had previously existed.

This allows for configuring a metadata service, or some other data.

When :ref:`the local stage<boot-Local>` runs, it will check to see if
``cloud-config-url`` appears in key/value fashion in the kernel command line,
such as:

.. code-block:: text

   root=/dev/sda ro cloud-config-url=http://foo.bar.zee/abcde

``Cloud-init`` will then read the contents of the given URL. If the content
starts with ``#cloud-config``, it will store that data to the local filesystem
in a static filename :file:`/etc/cloud/cloud.cfg.d/91_kernel_cmdline_url.cfg`,
and consider it as part of the config from that point forward.

.. note::
   If :file:`/etc/cloud/cloud.cfg.d/91_kernel_cmdline_url.cfg` already exists,
   cloud-init will not overwrite the file, and the ``cloud-config-url``
   parameter is completely ignored.


This is useful, for example, to be able to configure the MAAS datasource by
controlling the kernel command line from outside the image, you can append:

.. code-block:: text

    cloud-config-url=http://your.url.here/abcdefg

Then, have the following content at that url:

.. code-block:: yaml

    #cloud-config
    datasource:
      MAAS:
        metadata_url: http://mass-host.localdomain/source
        consumer_key: Xh234sdkljf
        token_key: kjfhgb3n
        token_secret: 24uysdfx1w4

.. warning::

   ``url`` kernel command line key is deprecated.
   Please use ``cloud-config-url`` parameter instead.

.. note::

   Since ``cloud-config-url=`` is so generic, in order to avoid false
   positives, only :ref:`cloud config<user_data_formats-cloud_config>` user
   data starting with ``#cloud-config`` is supported.


.. note::

   The ``cloud-config-url=`` is unencrypted http GET, and may contain
   credentials. Care must be taken to ensure this data is only
   transferred via trusted channels (i.e., within a closed system).
