.. _configuration:

Configuration sources
*********************

Internally, ``cloud-init`` builds a single configuration that is then
referenced throughout the life of ``cloud-init``. The configuration is built
from multiple sources such that if a key is defined in multiple sources, the
higher priority source overwrites the lower priority source.

Base configuration
==================

From lowest priority to highest, configuration sources are:

- **Hardcoded config**: Config_ that lives within the source of ``cloud-init``
  and cannot be changed.
- **Configuration directory**: Anything defined in :file:`/etc/cloud/cloud.cfg`
  and :file:`/etc/cloud/cloud.cfg.d`.
- **Runtime config**: Anything defined in :file:`/run/cloud-init/cloud.cfg`.
- **Kernel command line**: On the kernel command line, anything found between
  ``cc:`` and ``end_cc`` will be interpreted as cloud-config user data.

These four sources make up the base configuration.

Vendor and user data
====================

Added to the base configuration are :ref:`vendor data<vendordata>` and
:ref:`user data<user_data_formats>` which are both provided by the datasource.

These get fetched from the datasource and are defined at instance launch.

.. note::
   While much of what is defined in the base configuration can be overridden by
   vendor data and user data, base configuration sources do not conform to
   :ref:`#cloud-config<user_data_formats>`.

Network configuration
=====================

Network configuration happens independently from other ``cloud-init``
configuration. See :ref:`network configuration documentation<network_config>`
for more information.

Specifying configuration
==========================

End users
---------

Pass :ref:`user data<user_data_formats>` to the cloud provider.
Every platform supporting ``cloud-init`` will provide a method of supplying
user data. If you're unsure how to do this, reference the documentation
provided by the cloud platform you're on. Additionally, there may be
related ``cloud-init`` documentation in the :ref:`datasource<datasources>`
section.

Once an instance has been initialised, the user data may not be edited.
It is sourced directly from the cloud, so even if you find a local file
that contains user data, it will likely be overwritten in the next boot.

Distro providers
----------------

Modify the base config. This often involves submitting a PR to modify
the base `cloud.cfg template`_, which is used to customise
:file:`/etc/cloud/cloud.cfg` per distro. Additionally, a file can be added to
:file:`/etc/cloud/cloud.cfg.d` to override a piece of the base configuration.

Cloud providers
---------------

Pass vendor data. This is the preferred method for clouds to provide
their own customisation. In some cases, it may make sense to modify the
base config in the same manner as distro providers on cloud-supported
images.


.. _Config: https://github.com/canonical/cloud-init/blob/b861ea8a5e1fd0eb33096f60f54eeff42d80d3bd/cloudinit/settings.py#L22
.. _cloud.cfg template: https://github.com/canonical/cloud-init/blob/main/config/cloud.cfg.tmpl
