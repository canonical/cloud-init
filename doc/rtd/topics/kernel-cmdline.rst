.. _kernel_cmdline:

*******************
Kernel Command Line
*******************

In order to allow an ephemeral, or otherwise pristine image to
receive some configuration, cloud-init will read a url directed by
the kernel command line and proceed as if its data had previously existed.

This allows for configuring a meta-data service, or some other data.

.. note::

   That usage of the kernel command line is somewhat of a last resort,
   as it requires knowing in advance the correct command line or modifying
   the boot loader to append data.

For example, when ``cloud-init init --local`` runs, it will check to
see if ``cloud-config-url`` appears in key/value fashion
in the kernel command line as in:

.. code-block:: text

   root=/dev/sda ro cloud-config-url=http://foo.bar.zee/abcde

Cloud-init will then read the contents of the given url.
If the content starts with ``#cloud-config``, it will store
that data to the local filesystem in a static filename
``/etc/cloud/cloud.cfg.d/91_kernel_cmdline_url.cfg``, and consider it as
part of the config from that point forward.

If that file exists already, it will not be overwritten, and the
`cloud-config-url` parameter is completely ignored.

Then, when the DataSource runs, it will find that config already available.

So, in order to be able to configure the MAAS DataSource by controlling the
kernel command line from outside the image, you can append:

  * ``cloud-config-url=http://your.url.here/abcdefg``

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

   `url` kernel command line key is deprecated.
   Please use `cloud-config-url` parameter instead"

.. note::

   Because ``cloud-config-url=`` is so very generic, in order to avoid false
   positives,
   cloud-init requires the content to start with ``#cloud-config`` in order
   for it to be considered.

.. note::

   The ``cloud-config-url=`` is un-authed http GET, and contains credentials.
   It could be set up to be randomly generated and also check source
   address in order to be more secure.
