.. _capabilities:

************
Capabilities
************

- Setting a default locale
- Setting an instance hostname
- Generating instance SSH private keys
- Adding SSH keys to a user's ``.ssh/authorized_keys`` so they can log in
- Setting up ephemeral mount points
- Configuring network devices

User configurability
====================

`Cloud-init`_ 's behavior can be configured via user-data.

    User-data can be given by the user at instance launch time.

This is done via the ``--user-data`` or ``--user-data-file`` argument to
ec2-run-instances for example.

* Check your local clients documentation for how to provide a `user-data`
  string or `user-data` file for usage by cloud-init on instance creation.


Feature detection
=================

Newer versions of cloud-init may have a list of additional features that they
support. This allows other applications to detect what features the installed
cloud-init supports without having to parse its version number. If present,
this list of features will be located at ``cloudinit.version.FEATURES``.

Currently defined feature names include:

 - ``NETWORK_CONFIG_V1`` support for v1 networking configuration,
   see :ref:`network_config_v1` documentation for examples.
 - ``NETWORK_CONFIG_V2`` support for v2 networking configuration,
   see :ref:`network_config_v2` documentation for examples.


CLI Interface
=============

The command line documentation is accessible on any cloud-init installed
system:

.. code-block:: shell-session

  % cloud-init --help
  usage: cloud-init [-h] [--version] [--file FILES]

                    [--debug] [--force]
                    {init,modules,single,dhclient-hook,features,analyze,devel,collect-logs,clean,status}
                    ...

  optional arguments:
    -h, --help            show this help message and exit
    --version, -v         show program's version number and exit
    --file FILES, -f FILES
                          additional yaml configuration files to use
    --debug, -d           show additional pre-action logging (default: False)
    --force               force running even if no datasource is found (use at
                          your own risk)

  Subcommands:
    {init,modules,single,dhclient-hook,features,analyze,devel,collect-logs,clean,status}
      init                initializes cloud-init and performs initial modules
      modules             activates modules using a given configuration key
      single              run a single module
      dhclient-hook       run the dhclient hookto record network info
      features            list defined features
      analyze             Devel tool: Analyze cloud-init logs and data
      devel               Run development tools
      collect-logs        Collect and tar all cloud-init debug info
      clean               Remove logs and artifacts so cloud-init can re-run.
      status              Report cloud-init status or wait on completion.

CLI Subcommand details
======================

.. _cli_features:

cloud-init features
-------------------
Print out each feature supported.  If cloud-init does not have the
features subcommand, it also does not support any features described in
this document.

.. code-block:: shell-session

  % cloud-init features
  NETWORK_CONFIG_V1
  NETWORK_CONFIG_V2

.. _cli_status:

cloud-init status
-----------------
Report whether cloud-init is running, done, disabled or errored. Exits
non-zero if an error is detected in cloud-init.

 * **--long**: Detailed status information.
 * **--wait**: Block until cloud-init completes.

.. code-block:: shell-session

  % cloud-init status --long
  status: done
  time: Wed, 17 Jan 2018 20:41:59 +0000
  detail:
  DataSourceNoCloud [seed=/var/lib/cloud/seed/nocloud-net][dsmode=net]

  # Cloud-init running still short versus long options
  % cloud-init status
  status: running
  % cloud-init status --long
  status: running
  time: Fri, 26 Jan 2018 21:39:43 +0000
  detail:
  Running in stage: init-local

.. _cli_collect_logs:

cloud-init collect-logs
-----------------------
Collect and tar cloud-init generated logs, data files and system
information for triage. This subcommand is integrated with apport. 

**Note**: Ubuntu users can file bugs with `ubuntu-bug cloud-init` to
automaticaly attach these logs to a bug report.

Logs collected are:

 * /var/log/cloud-init*log
 * /run/cloud-init
 * cloud-init package version
 * dmesg output
 * journalctl output
 * /var/lib/cloud/instance/user-data.txt

.. _cli_analyze:

cloud-init analyze
------------------
Get detailed reports of where cloud-init spends most of its time. See
:ref:`boot_time_analysis` for more info.

 * **blame** Report ordered by most costly operations.
 * **dump** Machine-readable JSON dump of all cloud-init tracked events.
 * **show** show time-ordered report of the cost of operations during each
   boot stage.

.. _cli_devel:

cloud-init devel
----------------
Collection of development tools under active development. These tools will
likely be promoted to top-level subcommands when stable.

 * ``cloud-init devel schema``: A **#cloud-config** format and schema
   validator. It accepts a cloud-config yaml file and annotates potential
   schema errors locally without the need for deployment. Schema
   validation is work in progress and supports a subset of cloud-config
   modules.

.. _cli_clean:

cloud-init clean
----------------
Remove cloud-init artifacts from /var/lib/cloud and optionally reboot the
machine to so cloud-init re-runs all stages as it did on first boot.

 * **--logs**: Optionally remove /var/log/cloud-init*log files.
 * **--reboot**: Reboot the system after removing artifacts.

.. _cli_init:

cloud-init init
---------------
Generally run by OS init systems to execute cloud-init's stages
*init* and *init-local*. See :ref:`boot_stages` for more info.
Can be run on the commandline, but is generally gated to run only once
due to semaphores in **/var/lib/cloud/instance/sem/** and
**/var/lib/cloud/sem**.

 * **--local**: Run *init-local* stage instead of *init*.

.. _cli_modules:

cloud-init modules
------------------
Generally run by OS init systems to execute *modules:config* and
*modules:final* boot stages. This executes cloud config :ref:`modules`
configured to run in the init, config and final stages. The modules are
declared to run in various boot stages in the file
**/etc/cloud/cloud.cfg** under keys **cloud_init_modules**,
**cloud_init_modules** and **cloud_init_modules**. Can be run on the
commandline, but each module is gated to run only once due to semaphores
in ``/var/lib/cloud/``.

 * **--mode (init|config|final)**: Run *modules:init*, *modules:config* or
   *modules:final* cloud-init stages. See :ref:`boot_stages` for more info.

.. _cli_single:

cloud-init single
-----------------
Attempt to run a single named cloud config module.  The following example
re-runs the cc_set_hostname module ignoring the module default frequency
of once-per-instance:

 * **--name**: The cloud-config module name to run
 * **--frequency**: Optionally override the declared module frequency
   with one of (always|once-per-instance|once)

.. code-block:: shell-session

  % cloud-init single --name set_hostname --frequency always

**Note**: Mileage may vary trying to re-run each cloud-config module, as
some are not idempotent.

.. _Cloud-init: https://launchpad.net/cloud-init
.. vi: textwidth=78
