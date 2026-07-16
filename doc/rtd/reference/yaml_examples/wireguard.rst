.. _cce-wireguard:

Configure Wireguard tunnel
**************************

In this example, we show how to configure one (or more) Wireguard interfaces,
and also provide (optional) readiness probes.

Each interface you wish to create will be named after the ``name`` parameter,
and the config will be written to a file located under ``config_path``.

The ``content`` parameter should be set with a valid Wireguard configuration.

The readiness probes ensure Wireguard has connectivity before continuing the
cloud-init process. This could be useful if you need access to specific
services like an internal APT repository server (e.g., Landscape) to install or
update packages.

For a full list of keys, refer to the
:ref:`Wireguard module <mod_cc_wireguard>` schema.

.. literalinclude:: ../../../module-docs/cc_wireguard/example1.yaml
   :language: yaml
   :linenos:

