***********
Boot Stages
***********
In order to be able to provide the functionality that it does, cloud-init
must be integrated into the boot in fairly controlled way.

There are 5 stages.

1. **Generator**
2. **Local**
3. **Network**
4. **Config**
5. **Final**

Generator
=========
When booting under systemd, a
`generator <https://www.freedesktop.org/software/systemd/man/systemd.generator.html>`_
will run that determines if cloud-init.target should be included in the
boot goals.  By default, this generator will enable cloud-init.  It will
not enable cloud-init if either:

 * A file exists: ``/etc/cloud/cloud-init.disabled``
 * The kernel command line as found in /proc/cmdline contains ``cloud-init=disabled``.
   When running in a container, the kernel command line is not honored, but
   cloud-init will read an environment variable named ``KERNEL_CMDLINE`` in
   its place.

This mechanism for disabling at runtime currently only exists in systemd.

Local
=====
 * **systemd service**: ``cloud-init-local.service``
 * **runs**: As soon as possible with / mounted read-write.
 * **blocks**: as much of boot as possible, *must* block network bringup.
 * **modules**: none

The purpose of the local stage is:
 * locate "local" data sources.
 * apply networking configuration to the system (including "Fallback")

In most cases, this stage does not do much more than that.  It finds the
datasource and determines the network configuration to be used.  That
network configuration can come from:

 * the datasource
 * fallback: Cloud-init's fallback networking consists of rendering the
   equivalent to "dhcp on eth0", which was historically the most popular
   mechanism for network configuration of a guest.
 * none.  network configuration can be disabled entirely with 
   config like the following in /etc/cloud/cloud.cfg: 
   '``network: {config: disabled}``'.

If this is an instance's first boot, then the selected network configuration
is rendered.  This includes clearing of all previous (stale) configuration
including persistent device naming with old mac addresses.

This stage must block network bring-up or any stale configuration might
already have been applied.  That could have negative effects such as DHCP
hooks or broadcast of an old hostname.  It would also put the system in
an odd state to recover from as it may then have to restart network
devices.

Cloud-init then exits and expects for the continued boot of the operating
system to bring network configuration up as configured.

**Note**: In the past, local data sources have been only those that were
available without network (such as 'ConfigDrive').  However, as seen in
the recent additions to the DigitalOcean datasource, even data sources
that require a network can operate at this stage.

Network
=======
 * **systemd service**: ``cloud-init.service``
 * **runs**: After local stage and configured networking is up.
 * **blocks**: As much of remaining boot as possible.
 * **modules**: ``init_modules``

This stage requires all configured networking to be online, as it will fully
process any user-data that is found.  Here, processing means:

 * retrive any ``#include`` or ``#include-once`` (recursively) including http
 * uncompress any compressed content
 * run any part-handler found.

This stage runs the ``disk_setup`` and ``mounts`` modules which may partition
and format disks and configure mount points (such as in /etc/fstab).
Those modules cannot run earlier as they may receive configuration input
from sources only available via network.  For example, a user may have
provided user-data in a network resource that describes how local mounts
should be done.

On some clouds such as Azure, this stage will create filesystems to be
mounted, including ones that have stale (previous instance) references in
/etc/fstab. As such, entries /etc/fstab other than those necessary for
cloud-init to run should not be done until after this stage.

A part-handler will run at this stage, as will boothooks including
cloud-config ``bootcmd``.  The user of this functionality has to be aware
that the system is in the process of booting when their code runs.

Config
======
 * **systemd service**: ``cloud-config.service``
 * **runs**: After network stage.
 * **blocks**: None.
 * **modules**: ``config_modules``

This stage runs config modules only.  Modules that do not really have an
effect on other stages of boot are run here.


Final
=====
 * **systemd service**: ``cloud-final.service``
 * **runs**: As final part of boot (traditional "rc.local")
 * **blocks**: None.
 * **modules**: ``final_modules``

This stage runs as late in boot as possible.  Any scripts that a user is
accustomed to running after logging into a system should run correctly here.
Things that run here include

 * package installations
 * configuration management plugins (puppet, chef, salt-minion)
 * user-scripts (including ``runcmd``).

.. vi: textwidth=78
