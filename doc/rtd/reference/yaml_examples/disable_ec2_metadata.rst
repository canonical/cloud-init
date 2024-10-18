.. _cce-disable-ec2-metadata:

Disable AWS EC2 metadata
************************

The default value for this module is ``false``. Setting it to ``true`` disables
the IPv4 routes to EC2 metadata.

For more details, refer to the
:ref:`disable EC2 metadata module <mod_cc_disable_ec2_metadata>` schema.

.. literalinclude:: ../../../module-docs/cc_disable_ec2_metadata/example1.yaml
   :language: yaml
   :linenos:

