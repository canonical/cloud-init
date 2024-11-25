.. _cce-ntp:

Network Time Protocol (NTP)
***************************

The NTP module configures NTP services. If NTP is not installed on the system,
but NTP configuration is specified, NTP will be installed.

For a full list of keys, refer to the :ref:`NTP module <mod_cc_ntp>` schema.

Available keys:
===============

- ``servers``:
  List of NTP servers to sync with.
- ``pools``:
  List of NTP pool servers to sync with. Pools are typically DNS hostnames
  which resolve to different specific servers to load balance a set of
  services.

Each server in the list will be added in list-order in the format:

.. code-block:: yaml

   [pool|server] <server entry> iburst

If no servers or pools are defined but NTP is enabled, then cloud-init will
render the distro default list of pools:

.. code-block:: yaml

    pools = [
       '0.{distro}.pool.ntp.org',
       '1.{distro}.pool.ntp.org',
       '2.{distro}.pool.ntp.org',
       '3.{distro}.pool.ntp.org',
    ]

So putting these together, we can see a straightforward example:

.. code-block:: yaml

    #cloud-config
    ntp:
      pools: ['0.company.pool.ntp.org', '1.company.pool.ntp.org', 'ntp.myorg.org']
      servers: ['my.ntp.server.local', 'ntp.ubuntu.com', '192.168.23.2']

Override NTP with chrony
========================

Here we override NTP with chrony configuration on Ubuntu. The example uses
cloud-init's default chrony configuration.

.. literalinclude:: ../../../module-docs/cc_ntp/example1.yaml
   :language: yaml
   :linenos:

Custom NTP client config
========================

This example provides a custom NTP client configuration.

.. literalinclude:: ../../../module-docs/cc_ntp/example2.yaml
   :language: yaml
   :linenos:

