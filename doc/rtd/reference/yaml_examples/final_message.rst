.. _cce-final-message:

Output message when cloud-init finishes
***************************************

It is possible to configure the final message that cloud-init prints when it
has finished.

The message is written to the cloud-init log (usually
``/var/log/cloud-init.log``) and stderr.

For a full list of keys, refer to the
:ref:`final message module <mod_cc_final_message>` schema.

.. literalinclude:: ../../../module-docs/cc_final_message/example1.yaml
   :language: yaml
   :linenos:

