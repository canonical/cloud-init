.. _configuration:

Configuration
*************

Internally, cloud-init builds a single configuration that is then referenced
throughout the life of cloud-init. The configuration is built from multiple
sources such that if a key is defined in multiple sources, the higher priority
source overwrites the lower priority source.

From lowest priority to highest, configuration sources are:

* **Hardcoded config**: Config_ that lives within the source of cloud-init
  and cannot be changed.
* **Configuration directory**: Anything defined in ``/etc/cloud/cloud.cfg`` and
  ``/etc/cloud/cloud.cfg.d``
* **Runtime config**: Anything defined in ``/run/cloud-init/cloud.cfg``
* **Kernel command line**: On the kernel command line, anything found between
  ``cc:`` and ``end_cc`` will be interpreted as cloud-config user data.

These four sources make up the **base configuration**. Added to these
to provide the full configuration are:

* **Vendor data**: :ref:`Data<vendordata>` provided by the datasource
* **User data**: :ref:`Data<user_data_formats>` also provided by
  the datasource

.. note::
  Even though baseconfiguration is found in ``/etc/cloud/cloud.cfg``, it is
  distinct from :ref:`#cloud-config<topics/format:Cloud Config Data>`, which
  is a specific user data format.

Network Configuration
=====================
Network configuration happens independently from other cloud-init
configuration. It is sourced from the cloud provided metadata servce and is
not user editable. If you need to change your network configuration,
your options are:

* Use the cloud-provided tools to update your network topology in the cloud.
* :ref:`Disable cloud-init network configuration entirely
  <topics/network-config:Disabling Network Configuration>`.
  This leaves network configuration entirely up to you.

Specifying Configuration
==========================

End users
---------
Pass :ref:`user data<user_data_formats>` to the cloud provider.
Every platform supporting cloud-init will provide a method of supplying
user data. If you're unsure how to do this, reference the documentation
provided by the cloud platform you're on. Additionally, there may be
related cloud-init documentation in the :ref:`datasource<datasources>`
section.

Once an instance has been initialized, the user data may not be edited.
It is sourced directly from the cloud, so even if you find a local file
that contains user data, it will likely be overwritten next boot.

To modify the run frequency of a particular cloud-init module,
:ref:`cloud-init single<cli_single>` may be used. This can be used to
disable a module you no longer with to run.

Distro Providers
----------------
Modify the base config. This often involves submitting a PR to modify
the base `cloud.cfg template`_, which is used to customize
`/etc/cloud/cloud.cfg` per distro. Additionally, a file can be added to
``/etc/cloud/cloud.cfg.d`` to override a piece of the base configuration.

Cloud Providers
---------------
Pass vendor data. This is the preferred method for clouds to provide
their own customization. In some cases, it may make sense to modify the
base config in the same manner as distro providers on cloud-supported
images.


.. _Config: https://github.com/canonical/cloud-init/blob/b861ea8a5e1fd0eb33096f60f54eeff42d80d3bd/cloudinit/settings.py#L22
.. _cloud.cfg template: https://github.com/canonical/cloud-init/blob/main/config/cloud.cfg.tmpl
