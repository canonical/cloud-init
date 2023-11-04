.. _datasource_creation:

Datasource creation
*******************

There are multiple ways to provide `user data`, `metadata`, and
`vendor data`, and each cloud solution prefers its own way. A datasource
abstract base class defines a single interface to interact with the different
clouds. Each cloud implementation must inherit from this base class to use this
shared functionality and interface. See :file:`cloud-init/sources/__init__.py`
to see this class.

If you are interested in adding a new datasource for your cloud platform you
will need to do all of the following:

Identify a mechanism for positive identification of the platform
================================================================

It is good practice for a cloud platform to positively identify itself to
the guest. This allows the guest to make educated decisions based on the
platform on which it is running. On the x86 and arm64 architectures, many
clouds identify themselves through `DMI`_ data. For example, Oracle's public
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

Add datasource module cloudinit/sources/DataSource<CloudPlatform>.py
====================================================================

We suggest you start by copying one of the simpler datasources
such as ``DataSourceHetzner``.

Re-run datasource detection
---------------------------

While developing a new datasource it may be helpful to manually run datasource
detection without rebooting the system.

To re-run datasource detection, you must first force :file:`ds-identify` to
re-run, then clean up any logs, and finally, re-run ``cloud-init``:

.. code-block:: bash

   sudo DI_LOG=stderr /usr/lib/cloud-init/ds-identify --force
   sudo cloud-init clean --logs
   sudo cloud-init init --local
   sudo cloud-init init

Add tests for datasource module
===============================

Add a new file with some tests for the module to
:file:`cloudinit/sources/test_<yourplatform>.py`. For example, see
:file:`cloudinit/sources/tests/test_oracle.py`

Update ``ds-identify``
======================

In ``systemd`` systems, ``ds-identify`` is used to detect which datasource
should be enabled, or if ``cloud-init`` should run at all. You'll need to
make changes to :file:`tools/ds-identify`.

Add tests for ``ds-identify``
=============================

Add relevant tests in a new class to
:file:`tests/unittests/test_ds_identify.py`. You can use ``TestOracle`` as
an example.

Add your datasource name to the built-in list of datasources
============================================================

Add your datasource module name to the end of the ``datasource_list``
entry in :file:`cloudinit/settings.py`.

Add your cloud platform to apport collection prompts
====================================================

Update the list of cloud platforms in :file:`cloudinit/apport.py`. This list
will be provided to the user who invokes :command:`ubuntu-bug cloud-init`.

Enable datasource by default in Ubuntu packaging branches
=========================================================

Ubuntu packaging branches contain a template file,
:file:`debian/cloud-init.templates`, which ultimately sets the default
``datasource_list`` when installed via package. This file needs updating when
the commit gets into a package.

Add documentation for your datasource
=====================================

You should add a new file in
:file:`doc/rtd/reference/datasources/<cloudplatform>.rst`
and reference it in
:file:`doc/rtd/reference/datasources.rst`

.. _make-mime: https://cloudinit.readthedocs.io/en/latest/explanation/instancedata.html#storage-locations
.. _DMI: https://www.dmtf.org/sites/default/files/standards/documents/DSP0005.pdf
