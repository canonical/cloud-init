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

    User-data can be given by the user at instance launch time. See
    :ref:`user_data_formats` for acceptable user-data content.


This is done via the ``--user-data`` or ``--user-data-file`` argument to
ec2-run-instances for example.

* Check your local client's documentation for how to provide a `user-data`
  string or `user-data` file to cloud-init on instance creation.


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
                    {init,modules,single,query,dhclient-hook,features,analyze,devel,collect-logs,clean,status}
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
    {init,modules,single,query,dhclient-hook,features,analyze,devel,collect-logs,clean,status}
      init                initializes cloud-init and performs initial modules
      modules             activates modules using a given configuration key
      single              run a single module
      query               Query instance metadata from the command line
      dhclient-hook       run the dhclient hookto record network info
      features            list defined features
      analyze             Devel tool: Analyze cloud-init logs and data
      devel               Run development tools
      collect-logs        Collect and tar all cloud-init debug info
      clean               Remove logs and artifacts so cloud-init can re-run
      status              Report cloud-init status or wait on completion


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

.. _cli_query:

cloud-init query
------------------
Query standardized cloud instance metadata crawled by cloud-init and stored
in ``/run/cloud-init/instance-data.json``. This is a convenience command-line
interface to reference any cached configuration metadata that cloud-init
crawls when booting the instance. See :ref:`instance_metadata` for more info.

* **--all**: Dump all available instance data as json which can be queried.
* **--instance-data**: Optional path to a different instance-data.json file to
  source for queries.
* **--list-keys**: List available query keys from cached instance data.

.. code-block:: shell-session

  # List all top-level query keys available (includes standardized aliases)
  % cloud-init query --list-keys
  availability_zone
  base64_encoded_keys
  cloud_name
  ds
  instance_id
  local_hostname
  region
  v1

* **<varname>**: A dot-delimited variable path into the instance-data.json
   object.

.. code-block:: shell-session

  # Query cloud-init standardized metadata on any cloud
  % cloud-init query v1.cloud_name
  aws  # or openstack, azure, gce etc.

  # Any standardized instance-data under a <v#> key is aliased as a top-level
  # key for convenience.
  % cloud-init query cloud_name
  aws  # or openstack, azure, gce etc.

  # Query datasource-specific metadata on EC2
  % cloud-init query ds.meta_data.public_ipv4

* **--format** A string that will use jinja-template syntax to render a string
   replacing

.. code-block:: shell-session

  # Generate a custom hostname fqdn based on instance-id, cloud and region
  % cloud-init query --format 'custom-{{instance_id}}.{{region}}.{{v1.cloud_name}}.com'
  custom-i-0e91f69987f37ec74.us-east-2.aws.com


.. note::
  The standardized instance data keys under **v#** are guaranteed not to change
  behavior or format. If using top-level convenience aliases for any
  standardized instance data keys, the most value (highest **v#**) of that key
  name is what is reported as the top-level value. So these aliases act as a
  'latest'.


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

 * ``cloud-init devel render``: Use cloud-init's jinja template render to
   process  **#cloud-config** or **custom-scripts**, injecting any variables
   from ``/run/cloud-init/instance-data.json``. It accepts a user-data file
   containing  the jinja template header ``## template: jinja`` and renders
   that content with any instance-data.json variables present.


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
