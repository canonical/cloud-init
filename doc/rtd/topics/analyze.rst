*************************
Cloud-init Analyze Module
*************************

Overview
========
The analyze module was added to cloud-init in order to help analyze cloud-init boot time 
performance. It is loosely based on systemd-analyze where there are 4 main actions: 
show, blame, dump, and boot.

The 'show' action is similar to 'systemd-analyze critical-chain' which prints a list of units, the 
time they started and how long they took. For cloud-init, we have four stages, and within each stage
a number of modules may run depending on configuration.  ‘cloudinit-analyze show’ will, for each 
boot, print this information and a summary total time, per boot.

The 'blame' action matches 'systemd-analyze blame' where it prints, in descending order, 
the units that took the longest to run.  This output is highly useful for examining where cloud-init 
is spending its time during execution.

The 'dump' action simply dumps the cloud-init logs that the analyze module is performing
the analysis on and returns a list of dictionaries that can be consumed for other reporting needs.

The 'boot' action prints out kernel related timestamps that are not included in any of the
cloud-init logs. There are three different timestamps that are presented to the user: 
kernel start, kernel finish boot, and cloud-init start. This was added for additional
clarity into the boot process that cloud-init does not have control over, to aid in debugging of 
performance issues related to cloudinit startup or tracking regression.

Usage
=====
Using each of the printing formats is as easy as running one of the following bash commands:

.. code-block:: shell-session

  cloud-init analyze show
  cloud-init analyze blame
  cloud-init analyze dump
  cloud-init analyze boot

Cloud-init analyze boot Timestamp Gathering
===========================================
The following boot related timestamps are gathered on demand when cloud-init analyze boot runs:
- Kernel Startup, which is inferred from system uptime
- Kernel Finishes Initialization, which is inferred from systemd UserSpaceMonotonicTimestamp property
- Cloud-init activation, which is inferred from the property InactiveExitTimestamp of the cloud-init
local systemd unit.

In order to gather the necessary timestamps using systemd, running the commands

.. code-block:: shell-session

	systemctl show -p UserspaceTimestampMonotonic  
	systemctl show cloud-init-local -p InactiveExitTimestampMonotonic

will gather the UserspaceTimestamp and InactiveExitTimestamp. 
The UserspaceTimestamp tracks when the init system starts, which is used as an indicator of kernel
finishing initialization. The InactiveExitTimestamp tracks when a particular systemd unit transitions
from the Inactive to Active state, which can be used to mark the beginning of systemd's activation
of cloud-init.

Currently this only works for distros that use systemd as the init process. We will be expanding
support for other distros in the future and this document will be updated accordingly.

If systemd is not present on the system, dmesg is used to attempt to find an event that logs the
beginning of the init system. However, with this method only the first two timestamps are able to be found;
dmesg does not monitor userspace processes, so no cloud-init start timestamps are emitted like when
using systemd.

List of Cloud-init analyze boot supported distros
=================================================
- Arch
- CentOS
- Debian
- Fedora
- OpenSuSE
- Red Hat Enterprise Linux
- Ubuntu
- SUSE Linux Enterprise Server
- CoreOS

List of Cloud-init analyze boot unsupported distros
===================================================
- FreeBSD
- Gentoo