.. _reporting_bugs:

Report bugs
***********

In this guide, you will learn how to:

1) Search for existing issues.
2) Collect logs required for the bug report.
3) File bugs with the upstream ``cloud-init`` project.
4) Report issues for distro-specific packages.

Search for existing issues
==========================

Before filing a bug against cloud-init, make sure to search the `open issues`_
for bugs with similar symptoms and log messages. If you are uncertain whether
an existing issue is identical, then mention the potentially related issue(s)
in the bug report.

Collect logs
============

To debug an issue, it is crucial to understand what happened both before and
during the error condition. It may be tempting to file a bug with just a
snippet or two of the logs, but this is not enough information to reliably
debug the issue. To do so, run the following command to produce a tarfile that
you can upload:

.. code-block:: shell-session

   $ sudo cloud-init collect-logs

Example output:

.. code-block::

   Wrote /home/ubuntu/cloud-init.tar.gz

If your version of ``cloud-init`` does not have the :command:`collect-logs`
subcommand, then please manually collect the base log files by running the
following:

.. code-block:: shell-session

   $ sudo dmesg > dmesg.txt
   $ sudo journalctl -o short-precise > journal.txt
   $ sudo tar -cvf cloud-init.tar dmesg.txt journal.txt /run/cloud-init \
      /var/log/cloud-init.log /var/log/cloud-init-output.log

Report upstream bugs
====================

Bugs for upstream ``cloud-init`` are tracked using GitHub Issues. To file a
bug:

1. Collect the necessary debug logs as described above.
2. `Report an upstream cloud-init bug`_ on GitHub.

Bug reports that lack complete logs may be labeled ``incomplete`` until
sufficient information is provided. To aid in debugging, please include the
necessary logs in the bug report.

If your bug is for a specific distro using ``cloud-init``, please first
consider reporting it with the downstream distro or confirm that it still
occurs with the latest upstream ``cloud-init`` code. See the following section
for details on specific distro reporting.

Report documentation bugs
=========================

For documentation issues, you can submit an issue in GitHub using the
"Give feedback" button at the top of each documentation page. Make sure to
include a detailed description of the issue that you are seeing. Please
include screenshots if that helps to explain the problem.

Report distro-specific issues
=============================

For issues specific to your distro please use one of the following
distro-specific reporting mechanisms:

Ubuntu
------

To report a bug on Ubuntu use the :command:`ubuntu-bug` command on the affected
system to automatically collect the necessary logs and file a bug on
Launchpad:

.. code-block:: shell-session

   $ ubuntu-bug cloud-init

If that does not work or is not an option, please collect the logs using the
commands in the above Collect Logs section and then report the bug on the
`Ubuntu bug tracker`_. Make sure to attach your collected logs!

Debian
------

To file a bug against the Debian package of ``cloud-init`` please use the
`Debian bug tracker`_ to file against 'Package: cloud-init'. See the
`Debian bug reporting wiki`_ page for more details.

Red Hat, CentOS and Fedora
--------------------------

To file a bug against the Red Hat or Fedora packages of ``cloud-init`` please
use the `Red Hat jira`_.

SUSE and openSUSE
-----------------

To file a bug against the SUSE packages of ``cloud-init`` please use the
`SUSE bugzilla`_.

Arch Linux
----------

To file a bug against the Arch package of ``cloud-init`` please use the
`Arch Linux Bugtracker`_. See the `Arch Linux bug reporting wiki`_ for more
details.

.. LINKS:
.. _open issues: https://github.com/canonical/cloud-init/issues
.. _Report an upstream cloud-init bug: https://github.com/canonical/cloud-init/issues
.. _Ubuntu bug tracker: https://bugs.launchpad.net/ubuntu/+source/cloud-init/+filebug
.. _Debian bug tracker: https://bugs.debian.org/cgi-bin/pkgreport.cgi?pkg=cloud-init;dist=unstable
.. _Debian bug reporting wiki: https://www.debian.org/Bugs/Reporting
.. _Red Hat jira: https://issues.redhat.com/
.. _SUSE bugzilla: https://bugzilla.suse.com/index.cgi
.. _Arch Linux Bugtracker: https://bugs.archlinux.org/
.. _Arch Linux bug reporting wiki: https://wiki.archlinux.org/index.php/Bug_reporting_guidelines
