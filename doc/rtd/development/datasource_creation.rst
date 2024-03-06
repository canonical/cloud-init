.. _datasource_creation:

Supporting your cloud or platform
*********************************

The upstream cloud-init project regularly accepts code contributions for new
platforms that wish to support cloud-init.

Ways to add platform support
============================

To add cloud-init support for a new platform, there are two possible
approaches:

1. Provide platform compatibility with one of the existing datasource
   definitions, such as `nocloud`_ via `DatasourceNoCloud.py`_. Several
   platforms, including `Libvirt`_ and `Proxmox`_ use this approach.
2. Add a new datasource definition to upstream cloud-init. This provides
   tighter integration, a better debugging experience, and more control
   and flexibility of cloud-init's interaction with the datasource. This
   option is more sensible for clouds that have a unique architecture.

Platform requirements
=====================

There are some technical and logistical prerequisites that must be met for
cloud-init support.

Technical requirements
----------------------

A cloud needs to be able to identify itself to cloud-init at runtime, and that
the cloud be able to provide configuration to the instance.

A mechanism for self-identification
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Each cloud platform must positively identify itself to the guest. This allows
the guest to make educated decisions based on the platform on which it is
running. On the x86 and arm64 architectures, many clouds identify themselves
through `DMI`_ data. For example, Oracle's public cloud provides the string
``'OracleCloud.com'`` in the DMI chassis-asset field.

``Cloud-init``-enabled images produce a log file with details about the
platform. Reading through this log in :file:`/run/cloud-init/ds-identify.log`
may provide the information needed to uniquely identify the platform.
If the log is not present, one can generate the log by running ``ds-identify``
manually.

The mechanism used to identify the platform will be required for
``ds-identify`` and the datasource module sections below.

A mechanism for cloud-init to retrieve configuration
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

There are different methods that cloud-init can use to retrieve
cloud-configuration for configuring the instance. The most common method is a
webserver providing configuration over a link-local network.

Logistical requirements
-----------------------

As with any open source project, multiple logistal requirements exist.

Testing access
^^^^^^^^^^^^^^

A platform that isn't available for testing cannot be independently validated.
You will need to provide some means for community members and upstream
developers to test and verify this platform. Code that cannot be used cannot be
supported.

Maintainer support
^^^^^^^^^^^^^^^^^^

A point of contact is required who can answer questions and occasionally
provide testing or maintenance support. Maintainership is relatively informal,
but there is an expectation that from time to time upstream may need to contact
a the maintainer with inquiries. Datasources that appear to be unmaintained
and/or unused may be considered for eventual removal.

Adding cloud-init support
=========================

There are multiple ways to provide `user data`, `metadata`, and
`vendor data`, and each cloud solution prefers its own way. A datasource
abstract base class defines a single interface to interact with the different
clouds. Each cloud implementation must inherit from this base class to use this
shared functionality and interface. See :file:`cloud-init/sources/__init__.py`
to see this class.

If you are interested in adding a new datasource for your cloud platform you
will need to do all of the following:

Add datasource module cloudinit/sources/DataSource<CloudPlatform>.py
--------------------------------------------------------------------

We suggest you start by copying one of the simpler datasources
such as ``DataSourceHetzner``.

Re-run datasource detection
^^^^^^^^^^^^^^^^^^^^^^^^^^^

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
:file:`config/cloud.cfg.tmpl`, which ultimately sets the default
``datasource_list`` that is installed by distros that use the upstream
packaging configuration.

Add documentation for your datasource
-------------------------------------

You should add a new file in
:file:`doc/rtd/reference/datasources/<cloudplatform>.rst`
and reference it in
:file:`doc/rtd/reference/datasources.rst`

Benefits of including your datasource in upstream cloud-init
============================================================

Datasources included in upstream cloud-init benefit from ongoing maintenance,
compatibility with the rest of the codebase, and security fixes by the upstream
development team.


.. _make-mime: https://cloudinit.readthedocs.io/en/latest/explanation/instancedata.html#storage-locations
.. _DMI: https://www.dmtf.org/sites/default/files/standards/documents/DSP0005.pdf
.. _Libvirt: https://github.com/virt-manager/virt-manager/blob/main/man/virt-install.rst#--cloud-init
.. _Proxmox: https://pve.proxmox.com/wiki/Cloud-Init_Support
.. _DatasourceNoCloud.py: https://github.com/canonical/cloud-init/blob/main/cloudinit/sources/DataSourceNoCloud.py
.. _nocloud: https://cloudinit.readthedocs.io/en/latest/reference/datasources/nocloud.html
