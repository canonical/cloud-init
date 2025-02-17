.. _cce-mcollective:

Install and configure MCollective
*********************************

This example shows how MCollective can be installed, configured and started.
For a full list of keys, refer to the
:ref:`MCollective module <mod_cc_mcollective>` schema.

.. warning::
   The EC2 instance metadata service is a network service, and thus is readable by
   non-root users on the system (i.e. ``ec2metadata --user-data``).

   If you want security against this, use ``include-once`` + SSL URLs.

The example provides server private and public keys, and provides the following
config settings in ``/etc/mcollective/server.cfg``:

.. literalinclude:: ../../../module-docs/cc_mcollective/example1.yaml
   :language: yaml
   :linenos:


