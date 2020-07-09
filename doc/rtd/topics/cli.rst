.. _cli:

CLI Interface
*************

For the latest list of subcommands and arguments use cloud-init's ``--help``
option. This can be used against cloud-init itself or any of its subcommands.

.. code-block:: shell-session

  $ cloud-init --help
    usage: /usr/bin/cloud-init [-h] [--version] [--file FILES] [--debug] [--force]
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
        query               Query standardized instance metadata from the command
                            line.
        dhclient-hook       Run the dhclient hook to record network info.
        features            list defined features
        analyze             Devel tool: Analyze cloud-init logs and data
        devel               Run development tools
        collect-logs        Collect and tar all cloud-init debug info
        clean               Remove logs and artifacts so cloud-init can re-run.
        status              Report cloud-init status or wait on completion.

The rest of this document will give an overview of each of the subcommands.


.. _cli_analyze:

analyze
=======

Get detailed reports of where cloud-init spends its time during the boot
process. For more complete reference see :ref:`analyze`.

Possible subcommands include:

* *blame*: report ordered by most costly operations
* *dump*: machine-readable JSON dump of all cloud-init tracked events
* *show*: show time-ordered report of the cost of operations during each
  boot stage
* *boot*: show timestamps from kernel initialization, kernel finish
  initialization, and cloud-init start


.. _cli_clean:

clean
=====

Remove cloud-init artifacts from ``/var/lib/cloud`` to simulate a clean
instance. On reboot, cloud-init will re-run all stages as it did on first boot.

* *\\-\\-logs*: optionally remove all cloud-init log files in ``/var/log/``
* *\\-\\-reboot*: reboot the system after removing artifacts


.. _cli_collect_logs:

collect-logs
============

Collect and tar cloud-init generated logs, data files, and system
information for triage. This subcommand is integrated with apport.

Logs collected include:

 * ``/var/log/cloud-init.log``
 * ``/var/log/cloud-init-output.log``
 * ``/run/cloud-init``
 * ``/var/lib/cloud/instance/user-data.txt``
 * cloud-init package version
 * ``dmesg`` output
 * journalctl output

.. note::

  Ubuntu users can file bugs with ``ubuntu-bug cloud-init`` to
  automatically attach these logs to a bug report


.. _cli_devel:

devel
=====

Collection of development tools under active development. These tools will
likely be promoted to top-level subcommands when stable.

Do **NOT** rely on the output of these commands as they can and will change.

Current subcommands:

 * ``net-convert``: manually use cloud-init's network format conversion, useful
   for testing configuration or testing changes to the network conversion logic
   itself.
 * ``render``: use cloud-init's jinja template render to
   process  **#cloud-config** or **custom-scripts**, injecting any variables
   from ``/run/cloud-init/instance-data.json``. It accepts a user-data file
   containing  the jinja template header ``## template: jinja`` and renders
   that content with any instance-data.json variables present.
 * ``schema``: a **#cloud-config** format and schema
   validator. It accepts a cloud-config yaml file and annotates potential
   schema errors locally without the need for deployment. Schema
   validation is work in progress and supports a subset of cloud-config
   modules.


.. _cli_features:

features
========

Print out each feature supported.  If cloud-init does not have the
features subcommand, it also does not support any features described in
this document.

.. code-block:: shell-session

  $ cloud-init features
  NETWORK_CONFIG_V1
  NETWORK_CONFIG_V2


.. _cli_init:

init
====

Generally run by OS init systems to execute cloud-init's stages
*init* and *init-local*. See :ref:`boot_stages` for more info.
Can be run on the commandline, but is generally gated to run only once
due to semaphores in ``/var/lib/cloud/instance/sem/`` and
``/var/lib/cloud/sem``.

* *\\-\\-local*: run *init-local* stage instead of *init*


.. _cli_modules:

modules
=======

Generally run by OS init systems to execute *modules:config* and
*modules:final* boot stages. This executes cloud config :ref:`modules`
configured to run in the init, config and final stages. The modules are
declared to run in various boot stages in the file
``/etc/cloud/cloud.cfg`` under keys:

* *cloud_init_modules*
* *cloud_config_modules*
* *cloud_final_modules*

Can be run on the command line, but each module is gated to run only once due
to semaphores in ``/var/lib/cloud/``.

* *\\-\\-mode [init|config|final]*: run *modules:init*, *modules:config* or
  *modules:final* cloud-init stages. See :ref:`boot_stages` for more info.


.. _cli_query:

query
=====

Query standardized cloud instance metadata crawled by cloud-init and stored
in ``/run/cloud-init/instance-data.json``. This is a convenience command-line
interface to reference any cached configuration metadata that cloud-init
crawls when booting the instance. See :ref:`instance_metadata` for more info.

* *\\-\\-all*: dump all available instance data as json which can be queried
* *\\-\\-instance-data*: optional path to a different instance-data.json file
  to source for queries
* *\\-\\-list-keys*: list available query keys from cached instance data
* *\\-\\-format*: a string that will use jinja-template syntax to render a
  string replacing
* *<varname>*: a dot-delimited variable path into the instance-data.json
  object

Below demonstrates how to list all top-level query keys that are standardized
aliases:

.. code-block:: shell-session

    $ cloud-init query --list-keys
    _beta_keys
    availability_zone
    base64_encoded_keys
    cloud_name
    ds
    instance_id
    local_hostname
    platform
    public_ssh_keys
    region
    sensitive_keys
    subplatform
    userdata
    v1
    vendordata

Below demonstrates how to query standardized metadata from clouds:

.. code-block:: shell-session

  % cloud-init query v1.cloud_name
  aws  # or openstack, azure, gce etc.

  # Any standardized instance-data under a <v#> key is aliased as a top-level key for convenience.
  % cloud-init query cloud_name
  aws  # or openstack, azure, gce etc.

  # Query datasource-specific metadata on EC2
  % cloud-init query ds.meta_data.public_ipv4

.. note::

  The standardized instance data keys under **v#** are guaranteed not to change
  behavior or format. If using top-level convenience aliases for any
  standardized instance data keys, the most value (highest **v#**) of that key
  name is what is reported as the top-level value. So these aliases act as a
  'latest'.

This data can then be formatted to generate custom strings or data:

.. code-block:: shell-session

  # Generate a custom hostname fqdn based on instance-id, cloud and region
  % cloud-init query --format 'custom-{{instance_id}}.{{region}}.{{v1.cloud_name}}.com'
  custom-i-0e91f69987f37ec74.us-east-2.aws.com


.. _cli_single:

single
======

Attempt to run a single named cloud config module.

* *\\-\\-name*: the cloud-config module name to run
* *\\-\\-frequency*: optionally override the declared module frequency
  with one of (always|once-per-instance|once)

The following example re-runs the cc_set_hostname module ignoring the module
default frequency of once-per-instance:

.. code-block:: shell-session

  $ cloud-init single --name set_hostname --frequency always

.. note::

  Mileage may vary trying to re-run each cloud-config module, as
  some are not idempotent.


.. _cli_status:

status
======

Report whether cloud-init is running, done, disabled or errored. Exits
non-zero if an error is detected in cloud-init.

* *\\-\\-long*: detailed status information
* *\\-\\-wait*: block until cloud-init completes

Below are examples of output when cloud-init is running, showing status and
the currently running modules, as well as when it is done.

.. code-block:: shell-session

  $ cloud-init status
  status: running

  $ cloud-init status --long
  status: running
  time: Fri, 26 Jan 2018 21:39:43 +0000
  detail:
  Running in stage: init-local

  $ cloud-init status
  status: done

  $ cloud-init status --long
  status: done
  time: Wed, 17 Jan 2018 20:41:59 +0000
  detail:
  DataSourceNoCloud [seed=/var/lib/cloud/seed/nocloud-net][dsmode=net]

.. vi: textwidth=79
