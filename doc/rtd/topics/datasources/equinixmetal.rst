.. _datasource_equinixmetal:

Equinix Metal (EquinixMetal)
======================
The ``EquinixMetal`` datasource reads data from Equinix Metal.
Support is present in cloud-init since 0.7.9.
.. TODO update the version

Metadata Service
----------------
The Equinix Metal metadata service is available at the well known url
``http://metadata.platformequinix.com/``. For more information see
Equinix Metal on `metadata
<https://metal.equinix.com/developers/docs/servers/metadata/`__.

Versions
^^^^^^^^
Like the EC2 metadata service, Equinix Metal's metadata service provides
versioned data under specific paths.  As of December 2020, partial support
for the ``2009-04-04`` version is provided in the root path.

Equinix Metal's own metadata format is available in the ``metadata`` root
path.

Cloud-init uses the EC2 compatible ``2009-04-04`` version.

Additional metadata service root paths include:
 * components - an inventory of hardware components and status
 * userdata - the userdata provided at device creation time. This value can be
   updated with the Equinix Metal API, and the latest value will be provided.

Metadata
^^^^^^^^
Instance metadata can be queried at
``http://metadata.platformequinix.com/2009-04-04/meta-data``

.. code-block:: shell-session

    $ curl http://metadata.platformequinix.com/2009-04-04/meta-data
    instance-id
    hostname
    iqn
    plan
    facility
    tags
    operating-system
    public-keys
    public-ipv4
    public-ipv6

Userdata
^^^^^^^^
If provided, user-data will appear at
``http://metadata.platformequinix.com/2009-04-04/user-data``.
If no user-data is provided, this will return an empty
``application/x-octetstream`` response.

.. code-block:: shell-session

    $ curl http://metadata.platformequinix.com/2009-04-04/user-data
    #!/bin/sh
    echo "Hello World."

.. vi: textwidth=78
