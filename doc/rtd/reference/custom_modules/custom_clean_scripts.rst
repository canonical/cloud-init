.. _custom_clean_scripts:

Custom Clean Scripts
********************

Cloud-init provides the directory :file:`/etc/cloud/clean.d/` for third party
applications which need additional configuration artifact cleanup from
the filesystem when the :ref:`cloud-init clean<cli_clean>` command is invoked.

The :command:`clean` operation is typically performed by image creators
when preparing a golden image for clone and redeployment. The clean command
removes any cloud-init internal state, allowing cloud-init to treat the next
boot of this image as the "first boot".
Any executable scripts in this subdirectory will be invoked in lexicographical
order when running the :command:`clean` command.

Example
=======

.. code-block:: bash

   $ cat /etc/cloud/clean.d/99-live-installer
   #!/bin/sh
   sudo rm -rf /var/lib/installer_imgs/
   sudo rm -rf /var/log/installer/
