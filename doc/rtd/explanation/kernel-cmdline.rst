.. _kernel_cmdline:

Kernel command line
*******************

In order to allow an ephemeral, or otherwise pristine image to receive some
configuration, ``cloud-init`` can read a URL directed by the kernel command
line and proceed as if its data had previously existed.

This allows for configuring a metadata service, or some other data.

.. note::
   Usage of the kernel command line is somewhat of a last resort,
   as it requires knowing in advance the correct command line or modifying
   the boot loader to append data.

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


# TODO: say something about datasource detection override

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
   positives, ``cloud-init`` requires the content to start with
   ``#cloud-config`` for it to be considered.


.. note::

   The ``cloud-config-url=`` is un-authed http GET, and may contain
   credentials. Care must be taken to ensure this data is only
   transferred via trusted channels.
