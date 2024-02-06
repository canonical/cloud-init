.. _boot_stages:

Boot stages
***********

There are five stages to boot:

1. Detect
2. Local
3. Network
4. Config
5. Final

.. _boot-Detect:

Detect
======

A platform identification tool called ``ds-identify`` runs in the first stage.
This tool detects which platform the instance is running on. This tool is
integrated into the init system to disable cloud-init when no platform is
found, and enable cloud-init when a valid platform is detected. This stage
might not be present for every installation of cloud-init.

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

- **datasource**: Cloud-provided network configuration via metadata.
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
have already been applied. Otherwise, that could have negative effects such
as DHCP hooks or broadcast of an old hostname. It would also put the system
in an odd state to recover from, as it may then have to restart network
devices.

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
| systemd service  | ``cloud-init.service``                                   |
+---------+--------+----------------------------------------------------------+
| runs             | after local stage and configured networking is up        |
+---------+--------+----------------------------------------------------------+
| blocks           | as much of remaining boot as possible                    |
+---------+--------+----------------------------------------------------------+
| modules          | *cloud_init_modules* in ``/etc/cloud/cloud.cfg``         |
+---------+--------+----------------------------------------------------------+

This stage requires all configured networking to be online, as it will fully
process any user data that is found. Here, processing means it will:

- retrieve any ``#include`` or ``#include-once`` (recursively) including
  http,
- decompress any compressed content, and
- run any part-handler found.

This stage runs the ``disk_setup`` and ``mounts`` modules which may partition
and format disks and configure mount points (such as in :file:`/etc/fstab`).
Those modules cannot run earlier as they may receive configuration input
from sources only available via the network. For example, a user may have
provided user data in a network resource that describes how local mounts
should be done.

On some clouds, such as Azure, this stage will create filesystems to be
mounted, including ones that have stale (previous instance) references in
:file:`/etc/fstab`. As such, entries in :file:`/etc/fstab` other than those
necessary for cloud-init to run should not be done until after this stage.

A part-handler and :ref:`boothooks<explanation/format:\`\`cloud-boothook\`\`>`
will run at this stage.

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
- user-defined scripts (i.e., shell scripts passed as user data).

For scripts external to ``cloud-init`` looking to wait until ``cloud-init`` is
finished, the :command:`cloud-init status --wait` subcommand can help block
external scripts until ``cloud-init`` is done without having to write your own
``systemd`` units dependency chains. See :ref:`cli_status` for more info.

.. _boot-First_boot_determination:

First boot determination
========================

``Cloud-init`` has to determine whether or not the current boot is the first
boot of a new instance, so that it applies the appropriate configuration. On
an instance's first boot, it should run all "per-instance" configuration,
whereas on a subsequent boot it should run only "per-boot" configuration. This
section describes how ``cloud-init`` performs this determination, as well as
why it is necessary.

When it runs, ``cloud-init`` stores a cache of its internal state for use
across stages and boots.

If this cache is present, then ``cloud-init`` has run on this system
before [#not-present]_. There are two cases where this could occur. Most
commonly, the instance has been rebooted, and this is a second/subsequent
boot. Alternatively, the filesystem has been attached to a *new* instance,
and this is the instance's first boot. The most obvious case where this
happens is when an instance is launched from an image captured from a
launched instance.

By default, ``cloud-init`` attempts to determine which case it is running
in by checking the instance ID in the cache against the instance ID it
determines at runtime. If they do not match, then this is an instance's
first boot; otherwise, it's a subsequent boot. Internally, ``cloud-init``
refers to this behaviour as ``check``.

This behaviour is required for images captured from launched instances to
behave correctly, and so is the default that generic cloud images ship with.
However, there are cases where it can cause problems [#problems]_. For these
cases, ``cloud-init`` has support for modifying its behaviour to trust the
instance ID that is present in the system unconditionally. This means that
``cloud-init`` will never detect a new instance when the cache is present,
and it follows that the only way to cause ``cloud-init`` to detect a new
instance (and therefore its first boot) is to manually remove
``cloud-init``'s cache. Internally, this behaviour is referred to as
``trust``.

To configure which of these behaviours to use, ``cloud-init`` exposes the
``manual_cache_clean`` configuration option.  When ``false`` (the default),
``cloud-init`` will ``check`` and clean the cache if the instance IDs do
not match (this is the default, as discussed above). When ``true``,
``cloud-init`` will ``trust`` the existing cache (and therefore not clean it).

Manual cache cleaning
=====================

``Cloud-init`` ships a command for manually cleaning the cache:
:command:`cloud-init clean`. See :ref:`cli_clean`'s documentation for further
details.

Reverting ``manual_cache_clean`` setting
----------------------------------------

Currently there is no support for switching an instance that is launched with
``manual_cache_clean: true`` from ``trust`` behaviour to ``check`` behaviour,
other than manually cleaning the cache.

.. warning:: If you want to capture an instance that is currently in ``trust``
   mode as an image for launching other instances, you **must** manually clean
   the cache. If you do not do so, then instances launched from the captured
   image will all detect their first boot as a subsequent boot of the captured
   instance, and will not apply any per-instance configuration.

   This is a functional issue, but also a potential security one:
   ``cloud-init`` is responsible for rotating SSH host keys on first boot,
   and this will not happen on these instances.

.. [#not-present] It follows that if this cache is not present,
   ``cloud-init`` has not run on this system before, so this is
   unambiguously this instance's first boot.

.. [#problems] A couple of ways in which this strict reliance on the presence
   of a datasource has been observed to cause problems:

    - If a cloud's metadata service is flaky and ``cloud-init`` cannot
      obtain the instance ID locally on that platform, ``cloud-init``'s
      instance ID determination will sometimes fail to determine the current
      instance ID, which makes it impossible to determine if this is an
      instance's first or subsequent boot (`#1885527`_).
    - If ``cloud-init`` is used to provision a physical appliance or device
      and an attacker can present a datasource to the device with a different
      instance ID, then ``cloud-init``'s default behaviour will detect this as
      an instance's first boot and reset the device using the attacker's
      configuration (this has been observed with the
      :ref:`NoCloud datasource<datasource_nocloud>` in `#1879530`_).

.. _generator: https://www.freedesktop.org/software/systemd/man/systemd.generator.html
.. _#1885527: https://bugs.launchpad.net/ubuntu/+source/cloud-init/+bug/1885527
.. _#1879530: https://bugs.launchpad.net/ubuntu/+source/cloud-init/+bug/1879530
