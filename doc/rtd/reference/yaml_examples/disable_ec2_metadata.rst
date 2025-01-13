.. _cce-disable-ec2-metadata:

Disable AWS EC2 IMDS
********************

The default value for this module is ``false``. Setting it to ``true`` disables
the IPv4 routes to EC2 IMDS.

For more details, refer to the
:ref:`disable EC2 IMDS module <mod_cc_disable_ec2_metadata>` schema.

.. literalinclude:: ../../../module-docs/cc_disable_ec2_metadata/example1.yaml
   :language: yaml
   :linenos:

