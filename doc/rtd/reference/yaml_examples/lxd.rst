.. _cce-lxd:

LXD
***

LXD can be configured using ``lxd init`` (and optionally, ``lxd bridge``. If
LXD configuration is provided, it will be installed on the system if it is not
already present.

For a full list of keys, refer to the `LXD module`_ schema.

Minimal configuration
=====================

The simplest working configuration of LXD, with a directory backend, is as
follows:

.. code-block:: yaml

    #cloud-config
    lxd:
      init:
        storage_backend: dir

Config options showcase
=======================

This example shows a fuller configuration example, showcasing many of the LXD
options. For a more complete list of the config options available, refer to the
`LXD module`_ docs. If an option is not specified, it will default to "none".

.. code-block:: yaml

    #cloud-config
    lxd:
      init:
        network_address: 0.0.0.0
        network_port: 8443
        storage_backend: zfs
        storage_pool: datapool
        storage_create_loop: 10
      bridge:
        mode: new
        mtu: 1500
        name: lxdbr0
        ipv4_address: 10.0.8.1
        ipv4_netmask: 24
        ipv4_dhcp_first: 10.0.8.2
        ipv4_dhcp_last: 10.0.8.3
        ipv4_dhcp_leases: 250
        ipv4_nat: true
        ipv6_address: fd98:9e0:3744::1
        ipv6_netmask: 64
        ipv6_nat: true
        domain: lxd

Advanced configuration
======================

For more complex, non-iteractive LXD configuration of networks, storage pools,
profiles, projects, clusters and core config, ``lxd:preseed`` config will be
passed as stdin to the command:

.. code-block:: bash

    lxd init --preseed

See the `non-interactive LXD configuration`_ documentation, or run
``lxd init --dump`` to see the viable preseed YAML allowed.

Preseed settings configure the LXD daemon to listen for HTTPS connections on
``192.168.1.1`` port 9999, a nested profile which allows for LXD nesting on
containers, and a limited project allowing for RBAC approach when defining
behavior for sub projects.

.. code-block:: yaml

    #cloud-config
    lxd:
      preseed: |
        config:
          core.https_address: 192.168.1.1:9999
        networks:
          - config:
              ipv4.address: 10.42.42.1/24
              ipv4.nat: true
              ipv6.address: fd42:4242:4242:4242::1/64
              ipv6.nat: true
            description: ""
            name: lxdbr0
            type: bridge
            project: default
        storage_pools:
          - config:
              size: 5GiB
              source: /var/snap/lxd/common/lxd/disks/default.img
            description: ""
            name: default
            driver: zfs
        profiles:
          - config: {}
            description: Default LXD profile
            devices:
              eth0:
                name: eth0
                network: lxdbr0
                type: nic
              root:
                path: /
                pool: default
                type: disk
            name: default
          - config: {}
            security.nesting: true
            devices:
              eth0:
                name: eth0
                network: lxdbr0
                type: nic
              root:
                path: /
                pool: default
                type: disk
            name: nested
        projects:
          - config:
              features.images: true
              features.networks: true
              features.profiles: true
              features.storage.volumes: true
            description: Default LXD project
            name: default
          - config:
              features.images: false
              features.networks: true
              features.profiles: false
              features.storage.volumes: false
            description: Limited Access LXD project
            name: limited

.. _LXD module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#lxd
.. _non-interactive LXD configuration: https://documentation.ubuntu.com/lxd/en/latest/howto/initialize/#non-interactive-configuration
