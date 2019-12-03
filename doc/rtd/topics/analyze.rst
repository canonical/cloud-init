.. _analyze:

Analyze
*******

The analyze subcommand was added to cloud-init in order to help analyze
cloud-init boot time performance. It is loosely based on systemd-analyze where
there are four subcommands:

- blame
- show
- dump
- boot

Usage
=====

The analyze command requires one of the four subcommands:

.. code-block:: shell-session

  $ cloud-init analyze blame
  $ cloud-init analyze show
  $ cloud-init analyze dump
  $ cloud-init analyze boot

Availability
============

The analyze subcommand is generally available across all distributions with the
exception of Gentoo and FreeBSD.

Subcommands
===========

Blame
-----

The ``blame`` action matches ``systemd-analyze blame`` where it prints, in
descending order, the units that took the longest to run.  This output is
highly useful for examining where cloud-init is spending its time during
execution.

.. code-block:: shell-session

  $ cloud-init analyze blame
  -- Boot Record 01 --
      00.80300s (init-network/config-growpart)
      00.64300s (init-network/config-resizefs)
      00.62100s (init-network/config-ssh)
      00.57300s (modules-config/config-grub-dpkg)
      00.40300s (init-local/search-NoCloud)
      00.38200s (init-network/config-users-groups)
      00.19800s (modules-config/config-apt-configure)
      00.03700s (modules-final/config-keys-to-console)
      00.02100s (init-network/config-update_etc_hosts)
      00.02100s (init-network/check-cache)
      00.00800s (modules-final/config-ssh-authkey-fingerprints)
      00.00800s (init-network/consume-vendor-data)
      00.00600s (modules-config/config-timezone)
      00.00500s (modules-final/config-final-message)
      00.00400s (init-network/consume-user-data)
      00.00400s (init-network/config-mounts)
      00.00400s (init-network/config-disk_setup)
      00.00400s (init-network/config-bootcmd)
      00.00400s (init-network/activate-datasource)
      00.00300s (init-network/config-update_hostname)
      00.00300s (init-network/config-set_hostname)
      00.00200s (modules-final/config-snappy)
      00.00200s (init-network/config-rsyslog)
      00.00200s (init-network/config-ca-certs)
      00.00200s (init-local/check-cache)
      00.00100s (modules-final/config-scripts-vendor)
      00.00100s (modules-final/config-scripts-per-once)
      00.00100s (modules-final/config-salt-minion)
      00.00100s (modules-final/config-rightscale_userdata)
      00.00100s (modules-final/config-phone-home)
      00.00100s (modules-final/config-package-update-upgrade-install)
      00.00100s (modules-final/config-fan)
      00.00100s (modules-config/config-ubuntu-advantage)
      00.00100s (modules-config/config-ssh-import-id)
      00.00100s (modules-config/config-snap)
      00.00100s (modules-config/config-set-passwords)
      00.00100s (modules-config/config-runcmd)
      00.00100s (modules-config/config-locale)
      00.00100s (modules-config/config-byobu)
      00.00100s (modules-config/config-apt-pipelining)
      00.00100s (init-network/config-write-files)
      00.00100s (init-network/config-seed_random)
      00.00100s (init-network/config-migrator)
      00.00000s (modules-final/config-ubuntu-drivers)
      00.00000s (modules-final/config-scripts-user)
      00.00000s (modules-final/config-scripts-per-instance)
      00.00000s (modules-final/config-scripts-per-boot)
      00.00000s (modules-final/config-puppet)
      00.00000s (modules-final/config-power-state-change)
      00.00000s (modules-final/config-mcollective)
      00.00000s (modules-final/config-lxd)
      00.00000s (modules-final/config-landscape)
      00.00000s (modules-final/config-chef)
      00.00000s (modules-config/config-snap_config)
      00.00000s (modules-config/config-ntp)
      00.00000s (modules-config/config-emit_upstart)
      00.00000s (modules-config/config-disable-ec2-metadata)
      00.00000s (init-network/setup-datasource)

  1 boot records analyzed

Show
----

The ``show`` action is similar to ``systemd-analyze critical-chain`` which
prints a list of units, the time they started and how long they took.
Cloud-init has four stages and within each stage a number of modules may run
depending on configuration. ``cloudinit-analyze show`` will, for each boot,
print this information and a summary total time, per boot.

The following is an abbreviated example of the show output:

.. code-block:: shell-session

  $ cloud-init analyze show
  -- Boot Record 01 --
  The total time elapsed since completing an event is printed after the "@" character.
  The time the event takes is printed after the "+" character.

  Starting stage: init-local
  |``->no cache found @00.01700s +00.00200s
  |`->found local data from DataSourceNoCloud @00.11000s +00.40300s
  Finished stage: (init-local) 00.94200 seconds

  Starting stage: init-network
  |`->restored from cache with run check: DataSourceNoCloud [seed=/dev/sr0][dsmode=net] @04.79500s +00.02100s
  |`->setting up datasource @04.88900s +00.00000s
  |`->reading and applying user-data @04.90100s +00.00400s
  |`->reading and applying vendor-data @04.90500s +00.00800s
  |`->activating datasource @04.95200s +00.00400s
  Finished stage: (init-network) 02.72100 seconds

  Starting stage: modules-config
  |`->config-emit_upstart ran successfully @15.43100s +00.00000s
  |`->config-snap ran successfully @15.43100s +00.00100s
  ...
  |`->config-runcmd ran successfully @16.22300s +00.00100s
  |`->config-byobu ran successfully @16.23400s +00.00100s
  Finished stage: (modules-config) 00.83500 seconds

  Starting stage: modules-final
  |`->config-snappy ran successfully @16.87400s +00.00200s
  |`->config-package-update-upgrade-install ran successfully @16.87600s +00.00100s
  ...
  |`->config-final-message ran successfully @16.93700s +00.00500s
  |`->config-power-state-change ran successfully @16.94300s +00.00000s
  Finished stage: (modules-final) 00.10300 seconds

  Total Time: 4.60100 seconds

  1 boot records analyzed

If additional boot records are detected then they are printed out from oldest
to newest.

Dump
----

The ``dump`` action simply dumps the cloud-init logs that the analyze module
is performing the analysis on and returns a list of dictionaries that can be
consumed for other reporting needs. Each element in the list is a boot entry.

.. code-block:: shell-session

  $ cloud-init analyze dump
  [
  {
    "description": "starting search for local datasources",
    "event_type": "start",
    "name": "init-local",
    "origin": "cloudinit",
    "timestamp": 1567057578.037
  },
  {
    "description": "attempting to read from cache [check]",
    "event_type": "start",
    "name": "init-local/check-cache",
    "origin": "cloudinit",
    "timestamp": 1567057578.054
  },
  {
    "description": "no cache found",
    "event_type": "finish",
    "name": "init-local/check-cache",
    "origin": "cloudinit",
    "result": "SUCCESS",
    "timestamp": 1567057578.056
  },
  {
    "description": "searching for local data from DataSourceNoCloud",
    "event_type": "start",
    "name": "init-local/search-NoCloud",
    "origin": "cloudinit",
    "timestamp": 1567057578.147
  },
  {
    "description": "found local data from DataSourceNoCloud",
    "event_type": "finish",
    "name": "init-local/search-NoCloud",
    "origin": "cloudinit",
    "result": "SUCCESS",
    "timestamp": 1567057578.55
  },
  {
    "description": "searching for local datasources",
    "event_type": "finish",
    "name": "init-local",
    "origin": "cloudinit",
    "result": "SUCCESS",
    "timestamp": 1567057578.979
  },
  {
    "description": "searching for network datasources",
    "event_type": "start",
    "name": "init-network",
    "origin": "cloudinit",
    "timestamp": 1567057582.814
  },
  {
    "description": "attempting to read from cache [trust]",
    "event_type": "start",
    "name": "init-network/check-cache",
    "origin": "cloudinit",
    "timestamp": 1567057582.832
  },
  ...
  {
    "description": "config-power-state-change ran successfully",
    "event_type": "finish",
    "name": "modules-final/config-power-state-change",
    "origin": "cloudinit",
    "result": "SUCCESS",
    "timestamp": 1567057594.98
  },
  {
    "description": "running modules for final",
    "event_type": "finish",
    "name": "modules-final",
    "origin": "cloudinit",
    "result": "SUCCESS",
    "timestamp": 1567057594.982
  }
  ]


Boot
----

The ``boot`` action prints out kernel related timestamps that are not included
in any of the cloud-init logs. There are three different timestamps that are
presented to the user:

- kernel start
- kernel finish boot
- cloud-init start

This was added for additional clarity into the boot process that cloud-init
does not have control over, to aid in debugging of performance issues related
to cloud-init startup, and tracking regression.

.. code-block:: shell-session

  $ cloud-init analyze boot
  -- Most Recent Boot Record --
      Kernel Started at: 2019-08-29 01:35:37.753790
      Kernel ended boot at: 2019-08-29 01:35:38.807407
      Kernel time to boot (seconds): 1.053617000579834
      Cloud-init activated by systemd at: 2019-08-29 01:35:43.992460
      Time between Kernel end boot and Cloud-init activation (seconds): 5.185053110122681
      Cloud-init start: 2019-08-29 08:35:45.867000
  successful

Timestamp Gathering
^^^^^^^^^^^^^^^^^^^

The following boot related timestamps are gathered on demand when cloud-init
analyze boot runs:

- Kernel startup gathered from system uptime
- Kernel finishes initialization from systemd
  UserSpaceMonotonicTimestamp property
- Cloud-init activation from the property InactiveExitTimestamp of the
  cloud-init local systemd unit

In order to gather the necessary timestamps using systemd, running the
commands below will gather the UserspaceTimestamp and InactiveExitTimestamp:

.. code-block:: shell-session

  $ systemctl show -p UserspaceTimestampMonotonic
  UserspaceTimestampMonotonic=989279
  $ systemctl show cloud-init-local -p InactiveExitTimestampMonotonic
  InactiveExitTimestampMonotonic=4493126

The UserspaceTimestamp tracks when the init system starts, which is used as
an indicator of kernel finishing initialization. The InactiveExitTimestamp
tracks when a particular systemd unit transitions from the Inactive to Active
state, which can be used to mark the beginning of systemd's activation of
cloud-init.

Currently this only works for distros that use systemd as the init process.
We will be expanding support for other distros in the future and this document
will be updated accordingly.

If systemd is not present on the system, dmesg is used to attempt to find an
event that logs the beginning of the init system. However, with this method
only the first two timestamps are able to be found; dmesg does not monitor
userspace processes, so no cloud-init start timestamps are emitted like when
using systemd.

.. vi: textwidth=79
