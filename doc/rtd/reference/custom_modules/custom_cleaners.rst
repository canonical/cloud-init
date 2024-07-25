.. _custom_cleaners:

Custom Cleaners
***************

Cloud-init provides the directory :file:`/etc/cloud/clean.d/` for third party
applications which need additional configuration artifact cleanup from
the filesystem when the :ref:`cloud-init clean<cli_clean>` command is invoked.

The :command:`clean` operation is typically performed by image creators
when preparing a golden image for clone and redeployment. The clean command
removes any cloud-init semaphores, allowing cloud-init to treat the next
boot of this image as the "first boot". When the image is next booted
cloud-init will performing all initial configuration based on any valid
datasource meta-data and user-data.

Any executable scripts in this subdirectory will be invoked in lexicographical
order with run-parts when running the :command:`clean` command.

Typical format of such scripts would be a ##-<some-app> like the following:
:file:`/etc/cloud/clean.d/99-live-installer`

An example of a script is:

.. code-block:: bash

   sudo rm -rf /var/lib/installer_imgs/
   sudo rm -rf /var/log/installer/
