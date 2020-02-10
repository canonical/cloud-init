.. _reporting_bugs:

Reporting Bugs
**************

The following documents:

1) How to collect information for reporting bugs
2) How to file bugs to the upstream cloud-init project or for distro specific
   packages

Collect Logs
============

To aid in debugging, please collect the necessary logs. To do so, run the
`collect-logs` subcommand to produce a tarfile that you can easily upload:

.. code-block:: shell-session

  $ cloud-init collect-logs
  Wrote /home/ubuntu/cloud-init.tar.gz

If your version of cloud-init does not have the  `collect-logs` subcommand,
then please manually collect the base log files by doing the following:

.. code-block:: shell-session

  $ dmesg > dmesg.txt
  $ sudo journalctl -o short-precise > journal.txt
  $ sudo tar -cvf cloud-init.tar dmesg.txt journal.txt /run/cloud-init \
      /var/log/cloud-init.log /var/log/cloud-init-output.log

Report Upstream Bug
===================

Bugs for upstream cloud-init are tracked using Launchpad. To file a bug:

1. Collect the necessary debug logs as described above
2. `Create a Launchpad account`_ or login to your existing account
3. `Report an upstream cloud-init bug`_

If debug logs are not provided, you will be asked for them before any
further time is spent debugging. If you are unable to obtain the required
logs please explain why in the bug.

If your bug is for a specific distro using cloud-init, please first consider
reporting it with the upstream distro or confirm that it still occurs
with the latest upstream cloud-init code. See below for details on specific
distro reporting.

Distro Specific Issues
======================

For issues specific to your distro please use one of the following distro
specific reporting mechanisms:

Ubuntu
------

To report a bug on Ubuntu use the `ubuntu-bug` command on the affected
system to automatically collect the necessary logs and file a bug on
Launchpad:

.. code-block:: shell-session

  $ ubuntu-bug cloud-init

If that does not work or is not an option, please collect the logs using the
commands in the above Collect Logs section and then report the bug on the
`Ubuntu bug tracker`_. Make sure to attach your collected logs!

Debian
------

To file a bug against the Debian package fo cloud-init please use the
`Debian bug tracker`_ to file against 'Package: cloud-init'. See the
`Debian bug reporting wiki`_ wiki page for more details.

Red Hat, CentOS, & Fedora
-------------------------

To file a bug against the Red Hat or Fedora packages of cloud-init please use
the `Red Hat bugzilla`_.

SUSE & openSUSE
---------------

To file a bug against the SuSE packages of cloud-init please use the
`SUSE bugzilla`_.

Arch
----

To file a bug against the Arch package of cloud-init please use the
`Arch Linux Bugtracker`_. See the `Arch bug reporting wiki`_ for more
details.

.. _Create a Launchpad account: https://help.launchpad.net/YourAccount/NewAccount
.. _Report an upstream cloud-init bug: https://bugs.launchpad.net/cloud-init/+filebug
.. _Ubuntu bug tracker: https://bugs.launchpad.net/ubuntu/+source/cloud-init/+filebug
.. _Debian bug tracker: https://bugs.debian.org/cgi-bin/pkgreport.cgi?pkg=cloud-init;dist=unstable
.. _Debian bug reporting wiki: https://www.debian.org/Bugs/Reporting
.. _Red Hat bugzilla: https://bugzilla.redhat.com/
.. _SUSE bugzilla: https://bugzilla.suse.com/index.cgi
.. _Arch Linux Bugtracker: https://bugs.archlinux.org/
.. _Arch bug reporting wiki: https://wiki.archlinux.org/index.php/Bug_reporting_guidelines

.. vi: textwidth=79
