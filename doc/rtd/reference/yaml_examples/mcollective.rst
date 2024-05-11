.. _cce-mcollective:

Install and configure Mcollective
*********************************

This example shows how Mcollective can be installed, configured and started.

It provides server private and public keys, and provides the following
config settings in ``/etc/mcollective/server.cfg``:

For a full list of keys, refer to the `Mcollective module`_ schema.

.. code-block:: yaml

    #cloud-config
    mcollective:
      conf:
        loglevel: debug
        plugin.stomp.host: dbhost
        public-cert: |
            -------BEGIN CERTIFICATE--------
            <cert data>
            -------END CERTIFICATE--------
        private-cert: |
            -------BEGIN CERTIFICATE--------
            <cert data>
            -------END CERTIFICATE--------

.. warning::
   The EC2 metadata service is a network service, and thus is readable by
   non-root users on the system (i.e. ``ec2metadata --user-data``).

   If you want security against this, use ``include-once`` + SSL URLs.

.. LINKS
.. _Mcollective module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#mcollective
