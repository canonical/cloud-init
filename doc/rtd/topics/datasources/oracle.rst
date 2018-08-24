.. _datasource_oracle:

Oracle
======

This datasource reads metadata, vendor-data and user-data from
`Oracle Compute Infrastructure`_ (OCI).

Oracle Platform
---------------
OCI provides bare metal and virtual machines.  In both cases, 
the platform identifies itself via DMI data in the chassis asset tag
with the string 'OracleCloud.com'.

Oracle's platform provides a metadata service that mimics the 2013-10-17
version of OpenStack metadata service.  Initially support for Oracle
was done via the OpenStack datasource.

Cloud-init has a specific datasource for Oracle in order to:
 a. allow and support future growth of the OCI platform.
 b. address small differences between OpenStack and Oracle metadata
    implementation.


.. _Oracle Compute Infrastructure: https://cloud.oracle.com/
.. vi: textwidth=78
