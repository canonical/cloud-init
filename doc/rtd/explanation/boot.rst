.. _boot_stages:

Boot stages
***********

There are five stages to boot which are run seqentially: ``Detect``, ``Local``,
``Network``, ``Config`` and ``Final``

Visual representation of cloud-init boot stages with respect to network config
and system accessibility:

.. raw:: html

  <div class="mermaid">
  graph TB

    D["<a href='#detect'>Detect</a>"] ---> L

    L --> NU([Network up])
    L & NU --> N
    subgraph L["<a href='#local'>Local</a>"]
        FI[Fetch IMDS]
    end

    N --> NO([Network online])
    N & NO --> C
    N --> S([SSH])
    N --> Login([Login])

    subgraph N["<a href='#network'>Network</a>"]
        cloud_init_modules
    end
    %% cloud_config_modules

    subgraph C["<a href='#config'>Config</a>"]
        cloud_config_modules
    end

    C --> F
    subgraph F["<a href='#final'>Final</a>"]
        cloud_final_modules
    end
  </div>

.. _boot-Detect:

Detect
======

A platform identification tool called ``ds-identify`` runs in the first stage.
This tool detects which platform the instance is running on. This tool is
integrated into the init system to disable cloud-init when no platform is
found, and enable cloud-init when a valid platform is detected.

.. _boot-Local:

Local
=====

+------------------+----------------------------------------------------------+
| systemd service  | ``cloud-init-local.service``                             |
+---------+--------+----------------------------------------------------------+
| runs             | as soon as possible with ``/`` mounted read-write        |
+---------+--------+----------------------------------------------------------+
| blocks           | as much of boot as possible, *must* block network        |
+---------+--------+----------------------------------------------------------+
| modules          | none                                                     |
+---------+--------+----------------------------------------------------------+

The purpose of the local stage is to:

 - Locate "local" data sources, and
 - Apply networking configuration to the system (including "fallback").

In most cases, this stage does not do much more than that. It finds the
datasource and determines the network configuration to be used. That
network configuration can come from:

- **datasource**: Cloud-provided network configuration via meta-data.
- **fallback**: ``Cloud-init``'s fallback networking consists of rendering
  the equivalent to ``dhcp on eth0``, which was historically the most popular
  mechanism for network configuration of a guest.
- **none**: Network configuration can be disabled by writing the file
  :file:`/etc/cloud/cloud.cfg` with the content:
  ``network: {config: disabled}``.

If this is an instance's first boot, then the selected network configuration
is rendered. This includes clearing of all previous (stale) configuration
including persistent device naming with old MAC addresses.

This stage must block network bring-up or any stale configuration that might
have already been applied. Otherwise, that could have negative effects such as
broadcast of an old hostname. It would also put the system in an odd state to
recover from, as it may then have to restart network devices.

``Cloud-init`` then exits and expects for the continued boot of the operating
system to bring network configuration up as configured.

.. note::
   In the past, local datasources have been only those that were available
   without network (such as 'ConfigDrive'). However, as seen in the recent
   additions to the :ref:`DigitalOcean datasource<datasource_digital_ocean>`,
   even data sources that require a network can operate at this stage.

.. _boot-Network:

Network
=======

+------------------+----------------------------------------------------------+
| systemd service  | ``cloud-init-network.service``                           |
+---------+--------+----------------------------------------------------------+
| runs             | after local stage and configured networking is up        |
+---------+--------+----------------------------------------------------------+
| blocks           | majority of remaining boot (e.g. SSH and console login)  |
+---------+--------+----------------------------------------------------------+
| modules          | *cloud_init_modules* in ``/etc/cloud/cloud.cfg``         |
+---------+--------+----------------------------------------------------------+

This stage requires all configured networking to be online, as it will fully
process any user-data that is found. Here, processing means it will:

- retrieve any ``#include`` or ``#include-once`` (recursively) including
  http,
- decompress any compressed content, and
- run any part-handler found.

This stage runs the ``disk_setup`` and ``mounts`` modules which may partition
and format disks and configure mount points (such as in :file:`/etc/fstab`).
Those modules cannot run earlier as they may receive configuration input
from sources only available via the network. For example, a user may have
provided user-data in a network resource that describes how local mounts
should be done.

On some clouds, such as Azure, this stage will create filesystems to be
mounted, including ones that have stale (previous instance) references in
:file:`/etc/fstab`. As such, entries in :file:`/etc/fstab` other than those
necessary for cloud-init to run should not be done until after this stage.

A part-handler and :ref:`boothooks<user_data_formats-cloud_boothook>`
will run at this stage.

After this stage completes, expect to be able to access the system via serial
console login or SSH.

.. _boot-Config:

Config
======

+------------------+----------------------------------------------------------+
| systemd service  | ``cloud-config.service``                                 |
+---------+--------+----------------------------------------------------------+
| runs             | after network                                            |
+---------+--------+----------------------------------------------------------+
| blocks           | nothing                                                  |
+---------+--------+----------------------------------------------------------+
| modules          | *cloud_config_modules* in ``/etc/cloud/cloud.cfg``       |
+---------+--------+----------------------------------------------------------+

This stage runs config modules only. Modules that do not really have an
effect on other stages of boot are run here, including ``runcmd``.

.. _boot-Final:

Final
=====

+------------------+----------------------------------------------------------+
| systemd service  | ``cloud-final.service``                                  |
+---------+--------+----------------------------------------------------------+
| runs             | as final part of boot (traditional "rc.local")           |
+---------+--------+----------------------------------------------------------+
| blocks           | nothing                                                  |
+---------+--------+----------------------------------------------------------+
| modules          | *cloud_final_modules* in ``/etc/cloud/cloud.cfg``        |
+---------+--------+----------------------------------------------------------+

This stage runs as late in boot as possible. Any scripts that a user is
accustomed to running after logging into a system should run correctly here.
Things that run here include:

- package installations,
- configuration management plugins (Ansible, Puppet, Chef, salt-minion), and
- user-defined scripts (i.e., shell scripts passed as user-data).

For scripts external to ``cloud-init`` looking to wait until ``cloud-init`` is
finished, the :command:`cloud-init status --wait` subcommand can help block
external scripts until ``cloud-init`` is done without having to write your own
``systemd`` units dependency chains. See :ref:`cli_status` for more info.

See the :ref:`first boot documentation <First_boot_determination>` to learn how
cloud-init decides that a boot is the "first boot".

.. _generator: https://www.freedesktop.org/software/systemd/man/systemd.generator.html
