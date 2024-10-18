.. _cce-lxd:

LXD
***

LXD can be configured using ``lxd init`` (and optionally, ``lxd bridge``. If
LXD configuration is provided, it will be installed on the system if it is not
already present.

For a full list of keys, refer to the :ref:`LXD module <mod_cc_lxd>` schema.

Minimal configuration
=====================

The simplest working configuration of LXD, with a directory backend, is as
follows:

.. literalinclude:: ../../../module-docs/cc_lxd/example1.yaml
   :language: yaml
   :linenos:

Config options showcase
=======================

This example shows a fuller configuration example, showcasing many of the LXD
options. For a more complete list of the config options available, refer to the
:ref:`LXD module <mod_cc_lxd>` docs. If an option is not specified, it will
default to "none".

.. literalinclude:: ../../../module-docs/cc_lxd/example2.yaml
   :language: yaml
   :linenos:

Advanced configuration
======================

For more complex, non-interactive LXD configuration of networks, storage pools,
profiles, projects, clusters and core config, ``lxd:preseed`` config will be
passed as stdin to the command:

.. code-block:: bash

    lxd init --preseed

See the `non-interactive LXD configuration`_ documentation, or run
``lxd init --dump`` to see the viable preseed YAML allowed.

Preseed settings configure the LXD daemon to listen for HTTPS connections on
``192.168.1.1`` port 9999, a nested profile which allows for LXD nesting on
containers, and a limited project allowing for RBAC approach when defining
behavior for sub-projects.

.. literalinclude:: ../../../module-docs/cc_lxd/example3.yaml
   :language: yaml
   :linenos:

.. LINKS
.. _non-interactive LXD configuration: https://documentation.ubuntu.com/lxd/en/latest/howto/initialize/#non-interactive-configuration
