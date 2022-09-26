.. _configuration:

Configuration Sources
*********************

Internally, cloud-init builds a single configuration that is then referenced
throughout the life of cloud-init. The configuration is built from multiple
sources such that if a key is defined in multiple sources, the higher priority
source overwrites the lower priority source.

Base Configuration
==================

From lowest priority to highest, configuration sources are:

* **Hardcoded config**: Config_ that lives within the source of cloud-init
  and cannot be changed.
* **Configuration directory**: Anything defined in ``/etc/cloud/cloud.cfg`` and
  ``/etc/cloud/cloud.cfg.d``.
* **Runtime config**: Anything defined in ``/run/cloud-init/cloud.cfg``.
* **Kernel command line**: On the kernel command line, anything found between
  ``cc:`` and ``end_cc`` will be interpreted as cloud-config user data.

These four sources make up the base configuration.

Vendor and User Data
====================
Added to the base configuration are:

* **Vendor data**: :ref:`Data<vendordata>` provided by the datasource
* **User data**: :ref:`Data<user_data_formats>` also provided by
  the datasource

These get fetched from the datasource and are defined at instance launch.

.. note::
  While much of what is defined in the base configuration can be overridden by
  vendor data and user data, base configuration sources do not conform to
  :ref:`#cloud-config<topics/format:Cloud Config Data>`

Network Configuration
=====================
Network configuration happens independently from other cloud-init
configuration. See :ref:`network configuration documentation<default_behavior>`
for more information.

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
