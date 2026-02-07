.. _configuration:

Configuration priority
**********************

Configuration settings are prioritized by their source. Settings from a higher
priority source override settings from lower priority sources.  In decreasing
priority:

1. Runtime configuration
2. Image configuration
3. Builtin defaults

.. _runtime_config:

Runtime configuration
---------------------

Runtime configuration is fetched from the datasource and is defined at instance
launch. Runtime settings use the :ref:`user-data format.<user_data_formats>`.

User-provided configurations override settings provided by the platform (called
:ref:`vendor-data<vendor-data>`).

Every platform supporting ``cloud-init`` should provide a method for supplying
user-data. See your cloud provider's documentation for details. The
:ref:`datasource page<datasources>` for your cloud might have clues for how to
define user-data.

Once an instance has been initialized, the user-data may not be edited.
It is sourced directly from the cloud, so even if you find a local file
that contains user-data, it will likely be overwritten in the next boot.


Image configuration
-------------------

Image configurations are built into an image before it boots. Image
configurations can define :ref:`user-data<user_data_formats>`
settings, as well as other :ref:`base configuration<base_config_reference>`
settings.

From highest priority to lowest, image configuration sources are:

- **Runtime config**: Machine-generated :file:`/run/cloud-init/cloud.cfg`. Do
  not write to this file.
- **Configuration directory**: Anything defined in :file:`/etc/cloud/cloud.cfg`
  and :file:`/etc/cloud/cloud.cfg.d/*.cfg`.
- **Hardcoded config** Config_ that lives within the source of ``cloud-init``
  and cannot be changed.

.. _upstream-config:

Builtin defaults
----------------

Some settings are part of the source code and may be overridden.

.. _network:

Network configuration
=====================

Cloud-init brings up the network without any configuration required. See
:ref:`network configuration documentation<network_config>` for more
information.

.. _Config: https://github.com/canonical/cloud-init/blob/b861ea8a5e1fd0eb33096f60f54eeff42d80d3bd/cloudinit/settings.py#L22
.. _cloud.cfg template: https://github.com/canonical/cloud-init/blob/main/config/cloud.cfg.tmpl
.. _YAML version 1.1: https://yaml.org/spec/1.1/current.html
