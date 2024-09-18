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

A cloud needs to be able to identify itself to cloud-init at runtime and
provide unique configuration to the instance.

A mechanism for identification
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Each cloud platform must positively identify itself to the guest. This allows
the guest to make educated decisions based on the platform on which it is
running. On the x86 and arm64 architectures, many clouds identify themselves
through `DMI`_ data. For example, Oracle's public cloud provides the string
``'OracleCloud.com'`` in the DMI chassis-asset field. Some platforms present
attached devices with well known filesystem label, kernel command line flags or
virtualization types which uniquely identify a particular cloud platform.

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
shared functionality and interface. See `cloudinit/sources/__init__.py`_
to see this class.

If you are interested in adding a new datasource for your cloud platform you
will need to do all of the following:

Update ``ds-identify``
----------------------

In ``systemd``, Alpine and BSD environments, ``ds-identify`` runs in early boot
to detect which datasource should be enabled, or if ``cloud-init`` should run
at all. You'll need to add early identification support for the platform via a
``dscheck_<CloudPlatform>`` function in `tools/ds-identify`_.
For example, see `NWCS support`_

Add tests for ``ds-identify``
-----------------------------

Add relevant tests in a new class to
`tests/unittests/test_ds_identify.py`_. Use ``TestOracle`` as an example.

Add datasource module cloudinit/sources/DataSource<CloudPlatform>.py
--------------------------------------------------------------------

Use one of the simpler datasources such as ``DataSourceHetzner`` as a guiding
template for style and expectations. The DataSource module should implement a
``ds_detect`` method validates the same identification conditions defined
in ds-identify and returns ``True`` when met. This allows cloud-init to support
environments without ds-identify run as part of the init system.

Re-run datasource detection
^^^^^^^^^^^^^^^^^^^^^^^^^^^

While developing a new datasource it may be helpful to manually run datasource
detection without rebooting the system.

To re-run datasource detection, first force :file:`ds-identify` to
re-run, then clean up any logs, and finally, re-run ``cloud-init``:

.. code-block:: bash

   sudo DI_LOG=stderr /usr/lib/cloud-init/ds-identify --force
   sudo cloud-init clean --logs
   sudo cloud-init init --local
   sudo cloud-init init

Add tests for datasource module
-------------------------------

Add a new file with some tests for the module to
:file:`tests/unittests/sources/test_<cloudplatform>.py`. For example, see
`tests/unittests/sources/test_oracle.py`_

Add your datasource name to the built-in list of datasources
------------------------------------------------------------

Add the new datasource module name to the end of the ``datasource_list``
entry in `cloudinit/settings.py`_.

Add your cloud platform to apport collection prompts
----------------------------------------------------

Update the list of cloud platforms in `cloudinit/apport.py`_. This list
will be provided to the user who invokes :command:`ubuntu-bug cloud-init`.

Enable datasource by default in Ubuntu packaging branches
---------------------------------------------------------

Ubuntu packaging branches contain a template file,
:file:`config/cloud.cfg.tmpl`, which ultimately sets the default
``datasource_list`` that is installed by distros that use the upstream
packaging configuration.

Add documentation for your datasource
-------------------------------------

Update the following docs:
1. Add a new file in :file:`doc/rtd/reference/datasources/<cloudplatform>.rst`
2. Reference `<cloudplatform>.rst` in `doc/rtd/reference/datasources.rst`_
3. Add an alphabetized dsname entry in representing the datasource
`doc/rtd/reference/datasource_dsname_map.rst`_

Benefits of including a datasource in upstream cloud-init
=========================================================

Datasources included in upstream cloud-init benefit from ongoing maintenance,
compatibility with the rest of the codebase, and security fixes by the upstream
development team.

If this is not possible, one can add
:ref:`custom out-of-tree datasources<custom_datasource>` to cloud-init.

.. _make-mime: https://cloudinit.readthedocs.io/en/latest/explanation/instancedata.html#storage-locations
.. _DMI: https://www.dmtf.org/sites/default/files/standards/documents/DSP0005.pdf
.. _Libvirt: https://github.com/virt-manager/virt-manager/blob/main/man/virt-install.rst#--cloud-init
.. _Proxmox: https://pve.proxmox.com/wiki/Cloud-Init_Support
.. _DatasourceNoCloud.py: https://github.com/canonical/cloud-init/blob/main/cloudinit/sources/DataSourceNoCloud.py
.. _nocloud: https://cloudinit.readthedocs.io/en/latest/reference/datasources/nocloud.html
.. _NWCS support: https://github.com/canonical/cloud-init/commit/d0cae67b
.. _doc/rtd/reference/datasources.rst: https://github.com/canonical/cloud-init/tree/main/doc/reference/datasources.rst
.. _doc/rtd/reference/datasource_dsname_map.rst: https://github.com/canonical/cloud-init/tree/main/doc/reference/datasource_dsname_map.rst
.. _cloudinit/apport.py: https://github.com/canonical/cloud-init/tree/main/cloudinit/apport.py
.. _cloudinit/settings.py: https://github.com/canonical/cloud-init/tree/main/cloudinit/settings.py
.. _cloudinit/sources/__init__.py: https://github.com/canonical/cloud-init/tree/main/cloudinit/sources/__init__.py
.. _tests/unittests/test_ds_identify.py: https://github.com/canonical/cloud-init/tree/main/tests/unittests/test_ds_identify.py
.. _tests/unittests/sources/test_oracle.py:  https://github.com/canonical/cloud-init/tree/main/tests/unittests/sources/test_oracle.py
.. _tools/ds-identify:  https://github.com/canonical/cloud-init/tree/main/tools/ds-identify
