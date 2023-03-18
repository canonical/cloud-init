.. _datasources:

Datasources
***********

# todo fix links
Datasources are sources of configuration data for ``cloud-init``. This data
comes in the form of `user data`, `meta data`, and `vendor data`, which are
combined together into a single configuration.

To view this data, run ``sudo cloud-init query -a`` or check one of the files
that at instancedata-Using_

TODO: the following belongs in dev docs

Since there are multiple ways to provide this data (each cloud solution seems
to prefer its own way), a datasource abstract class was internally created to
allow for a single way to access the different cloud systems methods, providing
this data through the typical usage of subclasses.

Source
======

The following is a list of documents for each supported datasource:

.. toctree::
   :titlesonly:

   datasources/aliyun.rst
   datasources/altcloud.rst
   datasources/ec2.rst
   datasources/azure.rst
   datasources/cloudsigma.rst
   datasources/cloudstack.rst
   datasources/configdrive.rst
   datasources/digitalocean.rst
   datasources/e24cloud.rst
   datasources/exoscale.rst
   datasources/fallback.rst
   datasources/gce.rst
   datasources/lxd.rst
   datasources/maas.rst
   datasources/nocloud.rst
   datasources/nwcs.rst
   datasources/opennebula.rst
   datasources/openstack.rst
   datasources/oracle.rst
   datasources/ovf.rst
   datasources/rbxcloud.rst
   datasources/smartos.rst
   datasources/upcloud.rst
   datasources/vmware.rst
   datasources/vultr.rst
   datasources/zstack.rst

How to configure datasource
===========================
- mention that by default cloud-init should automatically determine which datasource it is running on
- however, in some cases, the datasource does not identify itself to cloud-init
- mention datasource_list in /etc/cloud/cloud.cfg.d/
- mention kernel commandline (include a map of datasource <-> dsname)


# TODO: everything below this line belongs in a dev doc

Datasource creation
===================

The datasource objects have a few touch points with ``cloud-init``. If you
are interested in adding a new datasource for your cloud platform you will
need to take care of the following items:

Identify a mechanism for positive identification of the platform
----------------------------------------------------------------

It is good practice for a cloud platform to positively identify itself to
the guest. This allows the guest to make educated decisions based on the
platform on which it is running. On the x86 and arm64 architectures, many
clouds identify themselves through DMI data. For example, Oracle's public
cloud provides the string ``'OracleCloud.com'`` in the DMI chassis-asset
field.

``Cloud-init``-enabled images produce a log file with details about the
platform. Reading through this log in :file:`/run/cloud-init/ds-identify.log`
may provide the information needed to uniquely identify the platform.
If the log is not present, you can generate it by running from source
:file:`./tools/ds-identify` or the installed location
:file:`/usr/lib/cloud-init/ds-identify`.

The mechanism used to identify the platform will be required for the
``ds-identify`` and datasource module sections below.

# Todo: the following line is broken in upstream docs, lets fix it now
Add datasource module :file:`cloudinit/sources/DataSource<CloudPlatform>.py`
----------------------------------------------------------------------------

It is suggested that you start by copying one of the simpler datasources
such as ``DataSourceHetzner``.

Add tests for datasource module
-------------------------------

Add a new file with some tests for the module to
:file:`cloudinit/sources/test_<yourplatform>.py`. For example, see
:file:`cloudinit/sources/tests/test_oracle.py`

Update ``ds-identify``
----------------------

In ``systemd`` systems, ``ds-identify`` is used to detect which datasource
should be enabled, or if ``cloud-init`` should run at all. You'll need to
make changes to :file:`tools/ds-identify`.

Add tests for ``ds-identify``
-----------------------------

Add relevant tests in a new class to
:file:`tests/unittests/test_ds_identify.py`. You can use ``TestOracle`` as
an example.

Add your datasource name to the built-in list of datasources
------------------------------------------------------------

Add your datasource module name to the end of the ``datasource_list``
entry in :file:`cloudinit/settings.py`.

Add your cloud platform to apport collection prompts
----------------------------------------------------

Update the list of cloud platforms in :file:`cloudinit/apport.py`. This list
will be provided to the user who invokes :command:`ubuntu-bug cloud-init`.

Enable datasource by default in Ubuntu packaging branches
---------------------------------------------------------

Ubuntu packaging branches contain a template file,
:file:`debian/cloud-init.templates`, which ultimately sets the default
``datasource_list`` when installed via package. This file needs updating when
the commit gets into a package.

Add documentation for your datasource
-------------------------------------

You should add a new file in :file:`doc/datasources/<cloudplatform>.rst`.

.. _make-mime: https://cloudinit.readthedocs.io/en/latest/explanation/instancedata.html#storage-locations
