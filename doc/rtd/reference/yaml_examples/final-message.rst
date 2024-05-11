.. _cce-final-message:

Output message when cloud-init finishes
***************************************

It is possible to configure the final message that cloud-init prints when it
has finished.

The message is written to the cloud-init log (usually
``/var/log/cloud-init.log``) and stderr.

For a full list of keys, refer to the `final message module`_ schema.

.. code-block:: yaml

    #cloud-config
    final_message: |
      cloud-init has finished
      version: $version
      timestamp: $timestamp
      datasource: $datasource
      uptime: $uptime

.. LINKS
.. _final message module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#final-message
