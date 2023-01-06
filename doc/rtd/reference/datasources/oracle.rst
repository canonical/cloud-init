.. _datasource_oracle:

Oracle
******

This datasource reads metadata, vendor data and user data from
`Oracle Compute Infrastructure`_ (OCI).

Oracle platform
===============

OCI provides bare metal and virtual machines. In both cases, the platform
identifies itself via DMI data in the chassis asset tag with the string
``'OracleCloud.com'``.

Oracle's platform provides a metadata service that mimics the ``2013-10-17``
version of OpenStack metadata service. Initially, support for Oracle was done
via the OpenStack datasource.

``Cloud-init`` has a specific datasource for Oracle in order to:

a. Allow and support the future growth of the OCI platform.
b. Address small differences between OpenStack and Oracle metadata
    implementation.

Configuration
=============

The following configuration can be set for the datasource in system
configuration (in :file:`/etc/cloud/cloud.cfg` or
:file:`/etc/cloud/cloud.cfg.d/`).

``configure_secondary_nics``
----------------------------

A boolean, defaulting to False. If set to True on an OCI Virtual Machine,
``cloud-init`` will fetch networking metadata from Oracle's IMDS and use it
to configure the non-primary network interface controllers in the system. If
set to True on an OCI Bare Metal Machine, it will have no effect (though this
may change in the future).

Example configuration
---------------------

An example configuration with the default values is provided below:

.. code-block:: yaml

   datasource:
    Oracle:
     configure_secondary_nics: false

.. _Oracle Compute Infrastructure: https://cloud.oracle.com/
