.. _cli:

CLI commands
************

For the latest list of subcommands and arguments use ``cloud-init``'s
``--help`` option. This can be used against ``cloud-init`` itself, or on any
of its subcommands.

.. code-block:: shell-session

   $ cloud-init --help

Example output:

.. code-block::

   usage: cloud-init [-h] [--version] [--debug] [--force]
                                                               {init,modules,single,query,features,analyze,devel,collect-logs,clean,status,schema} ...

    options:
      -h, --help            show this help message and exit
      --version, -v         Show program's version number and exit.
      --debug, -d           Show additional pre-action logging (default: False).
      --force               Force running even if no datasource is found (use at your own risk).

    Subcommands:
      {init,modules,single,query,features,analyze,devel,collect-logs,clean,status,schema}
        init                Initialize cloud-init and perform initial modules.
        modules             Activate modules using a given configuration key.
        single              Run a single module.
        query               Query standardized instance metadata from the command line.
        features            List defined features.
        analyze             Devel tool: Analyze cloud-init logs and data.
        devel               Run development tools.
        collect-logs        Collect and tar all cloud-init debug info.
        clean               Remove logs and artifacts so cloud-init can re-run.
        status              Report cloud-init status or wait on completion.
        schema              Validate cloud-config files using jsonschema.


The rest of this document will give an overview of each of the subcommands.

.. _cli_analyze:

:command:`analyze`
==================

Get detailed reports of where ``cloud-init`` spends its time during the boot
process. For more complete reference see :ref:`analyze`.

Possible subcommands include:

* :command:`blame`: report ordered by most costly operations.
* :command:`dump`: machine-readable JSON dump of all ``cloud-init`` tracked
  events.
* :command:`show`: show time-ordered report of the cost of operations during
  each boot stage.
* :command:`boot`: show timestamps from kernel initialisation, kernel finish
  initialisation, and ``cloud-init`` start.

.. _cli_clean:

:command:`clean`
================

Remove ``cloud-init`` artifacts from :file:`/var/lib/cloud` and config files
(best effort) to simulate a clean instance. On reboot, ``cloud-init`` will
re-run all stages as it did on first boot.

* :command:`--logs`: Optionally remove all ``cloud-init`` log files in
  :file:`/var/log/`.
* :command:`--reboot`: Reboot the system after removing artifacts.
* :command:`--machine-id`: Set :file:`/etc/machine-id` to ``uninitialized\n``
  on this image for systemd environments. On distributions without systemd,
  remove the file. Best practice when cloning a golden image, to ensure the
  next boot of that image auto-generates a unique machine ID.
  `More details on machine-id`_.
* :command:`--configs [all | ssh_config | network ]`: Optionally remove all
  ``cloud-init`` generated config files. Argument `ssh_config` cleans
  config files for ssh daemon. Argument `network` removes all generated
  config files for network. `all` removes config files of all types.

.. note::

   Cloud-init provides the directory :file:`/etc/cloud/clean.d/` for third party
   applications which need additional configuration artifact cleanup from
   the filesystem when the `clean` command is invoked.

   The :command:`clean` operation is typically performed by image creators
   when preparing a golden image for clone and redeployment. The clean command
   removes any cloud-init semaphores, allowing cloud-init to treat the next
   boot of this image as the "first boot". When the image is next booted
   cloud-init will performing all initial configuration based on any valid
   datasource meta-data and user-data.

   Any executable scripts in this subdirectory will be invoked in lexicographical
   order with run-parts when running the :command:`clean` command.

   Typical format of such scripts would be a ##-<some-app> like the following:
   :file:`/etc/cloud/clean.d/99-live-installer`

   An example of a script is:

   .. code-block:: bash

      sudo rm -rf /var/lib/installer_imgs/
      sudo rm -rf /var/log/installer/


.. _cli_collect_logs:

:command:`collect-logs`
=======================

Collect and tar ``cloud-init``-generated logs, data files, and system
information for triage. This subcommand is integrated with apport.

Logs collected include:

* :file:`/var/log/cloud-init.log`
* :file:`/var/log/cloud-init-output.log`
* :file:`/run/cloud-init`
* :file:`/var/lib/cloud/instance/user-data.txt`
* ``cloud-init`` package version
* ``dmesg`` output
* ``journalctl`` output

.. note::
   Ubuntu users can file bugs using :command:`ubuntu-bug cloud-init` to
   automatically attach these logs to a bug report.

.. _cli_devel:

:command:`devel`
================

Collection of development tools under active development. These tools will
likely be promoted to top-level subcommands when stable.

Do **NOT** rely on the output of these commands as they can and will change.

Current subcommands:

:command:`net-convert`
----------------------

Manually use ``cloud-init``'s network format conversion. Useful for testing
configuration or testing changes to the network conversion logic itself.

:command:`render`
-----------------

Use ``cloud-init``'s jinja template render to process **#cloud-config** or
**custom-scripts**, injecting any variables from
:file:`/run/cloud-init/instance-data.json`. It accepts a user data file
containing the jinja template header ``## template: jinja`` and renders that
content with any :file:`instance-data.json` variables present.

:command:`hotplug-hook`
-----------------------

Hotplug related subcommands. This command is intended to be
called via a ``systemd`` service and is not considered user-accessible except
for debugging purposes.


:command:`query`
^^^^^^^^^^^^^^^^

Query if hotplug is enabled for a given subsystem.

:command:`handle`
^^^^^^^^^^^^^^^^^

Respond to newly added system devices by retrieving updated system metadata
and bringing up/down the corresponding device.

:command:`enable`
^^^^^^^^^^^^^^^^^

Enable hotplug for a given subsystem. This is a last resort command for
administrators to enable hotplug in running instances. The recommended
method is configuring :ref:`events`, if not enabled by default in the active
datasource.

.. _cli_features:

:command:`features`
===================

Print out each feature supported. If ``cloud-init`` does not have the
:command:`features` subcommand, it also does not support any features
described in this document.

.. code-block:: shell-session

   $ cloud-init features

Example output:

.. code-block::

   NETWORK_CONFIG_V1
   NETWORK_CONFIG_V2


.. _cli_init:

:command:`init`
===============

Generally run by OS init systems to execute ``cloud-init``'s stages:
*init* and *init-local*. See :ref:`boot_stages` for more info.
Can be run on the command line, but is generally gated to run only once
due to semaphores in :file:`/var/lib/cloud/instance/sem/` and
:file:`/var/lib/cloud/sem`.

* :command:`--local`: Run *init-local* stage instead of *init*.
* :command:`--file` : Use additional yaml configuration files.

.. _cli_modules:

:command:`modules`
==================

Generally run by OS init systems to execute ``modules:config`` and
``modules:final`` boot stages. This executes cloud config :ref:`modules`
configured to run in the Init, Config and Final stages. The modules are
declared to run in various boot stages in the file
:file:`/etc/cloud/cloud.cfg` under keys:

* ``cloud_init_modules``
* ``cloud_config_modules``
* ``cloud_final_modules``

Can be run on the command line, but each module is gated to run only once due
to semaphores in :file:`/var/lib/cloud/`.

* :command:`--mode [init|config|final]`: Run ``modules:init``,
  ``modules:config`` or ``modules:final`` ``cloud-init`` stages.
  See :ref:`boot_stages` for more info.
* :command:`--file` : Use additional yaml configuration files.

.. warning::
   `--mode init` is deprecated in 24.1 and scheduled to be removed in 29.1.
   Use :command:`cloud-init init` instead.

.. _cli_query:

:command:`query`
================

Query standardised cloud instance metadata crawled by ``cloud-init`` and stored
in :file:`/run/cloud-init/instance-data.json`. This is a convenience
command-line interface to reference any cached configuration metadata that
``cloud-init`` crawls when booting the instance. See :ref:`instance_metadata`
for more info.

* :command:`--all`: Dump all available instance data as JSON which can be
  queried.
* :command:`--instance-data`: Optional path to a different
  :file:`instance-data.json` file to source for queries.
* :command:`--list-keys`: List available query keys from cached instance data.
* :command:`--format`: A string that will use jinja-template syntax to render a
  string replacing.
* :command:`<varname>`: A dot-delimited variable path into the
  :file:`instance-data.json` object.

Below demonstrates how to list all top-level query keys that are standardised
aliases:

.. code-block:: shell-session

    $ cloud-init query --list-keys

Example output:

.. code-block::

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

Here are a few examples of how to query standardised metadata from clouds:

.. code-block:: shell-session

   $ cloud-init query v1.cloud_name

Example output:

.. code-block::

   aws  # or openstack, azure, gce etc.

Any standardised ``instance-data`` under a <v#> key is aliased as a top-level
key for convenience:

.. code-block:: shell-session

   $ cloud-init query cloud_name

Example output:

.. code-block::

   aws  # or openstack, azure, gce etc.

One can also query datasource-specific metadata on EC2, e.g.:

.. code-block:: shell-session

   $ cloud-init query ds.meta_data.public_ipv4


.. note::

   The standardised instance data keys under **v#** are guaranteed not to
   change behaviour or format. If using top-level convenience aliases for any
   standardised instance data keys, the most value (highest **v#**) of that key
   name is what is reported as the top-level value. So these aliases act as a
   'latest'.

This data can then be formatted to generate custom strings or data. For
example, we can generate a custom hostname FQDN based on ``instance-id``, cloud
and region:

.. code-block:: shell-session

   $ cloud-init query --format 'custom-{{instance_id}}.{{region}}.{{v1.cloud_name}}.com'

.. code-block::

   custom-i-0e91f69987f37ec74.us-east-2.aws.com


.. _cli_schema:

:command:`schema`
=================

Validate cloud-config files using jsonschema.

* :command:`-h, --help`: Show this help message and exit.
* :command:`-c CONFIG_FILE, --config-file CONFIG_FILE`: Path of the
  cloud-config YAML file to validate.
* :command:`-t SCHEMA_TYPE, --schema-type SCHEMA_TYPE`: The schema type to
  validate --config-file against. One of: cloud-config, network-config.
  Default: cloud-config.
* :command:`--system`: Validate the system cloud-config user data.
* :command:`-d DOCS [cc_module ...], --docs DOCS [cc_module ...]`:
  Print schema module
  docs. Choices are: "all" or "space-delimited" ``cc_names``.
* :command:`--annotate`: Annotate existing cloud-config file with errors.

The following example checks a config file and annotates the config file with
errors on :file:`stdout`.

.. code-block:: shell-session

   $ cloud-init schema -c ./config.yml --annotate


.. _cli_single:

:command:`single`
=================

Attempt to run a single, named, cloud config module.

* :command:`--name`: The cloud-config module name to run.
* :command:`--frequency`: Module frequency for this run.
  One of (``always``|``instance``|``once``).
* :command:`--report`: Enable reporting.
* :command:`--file` : Use additional yaml configuration files.

The following example re-runs the ``cc_set_hostname`` module ignoring the
module default frequency of ``instance``:

.. code-block:: shell-session

   $ cloud-init single --name set_hostname --frequency always

.. note::

   Mileage may vary trying to re-run each ``cloud-config`` module, as
   some are not idempotent.

.. _cli_status:

:command:`status`
=================

Report cloud-init's current status.

Exits 1 if ``cloud-init`` crashes, 2 if ``cloud-init`` finishes but experienced
recoverable errors, and 0 if ``cloud-init`` ran without error.

* :command:`--long`: Detailed status information.
* :command:`--wait`: Block until ``cloud-init`` completes.
* :command:`--format [yaml|json]`: Machine-readable JSON or YAML
  detailed output.

The :command:`status` command can be used simply as follows:

.. code-block:: shell-session

   $ cloud-init status

Which shows whether ``cloud-init`` is currently running, done, disabled, or in
error. Note that the ``extended_status`` key in ``--long`` or ``--format json``
contains more accurate and complete status information. Example output:

.. code-block::

   status: running

The :command:`--long` option, shown below, provides a more verbose output.

.. code-block:: shell-session

   $ cloud-init status --long

Example output when ``cloud-init`` is running:

.. code-block::

   status: running
   extended_status: running
   boot_status_code: enabled-by-generator
   last_update: Wed, 13 Mar 2024 18:46:26 +0000
   detail: DataSourceLXD
   errors: []
   recoverable_errors: {}

Example output when ``cloud-init`` is done:

.. code-block::

   status: done
   extended_status: done
   boot_status_code: enabled-by-generator
   last_update: Wed, 13 Mar 2024 18:46:26 +0000
   detail: DataSourceLXD
   errors: []
   recoverable_errors: {}

The detailed output can be shown in machine-readable JSON or YAML with the
:command:`format` option, for example:

.. code-block:: shell-session

   $ cloud-init status --format=json

Which would produce the following example output:

.. code-block::

    {
      "boot_status_code": "enabled-by-generator",
      "datasource": "lxd",
      "detail": "DataSourceLXD",
      "errors": [],
      "extended_status": "done",
      "init": {
        "errors": [],
        "finished": 1710355584.3603137,
        "recoverable_errors": {},
        "start": 1710355584.2216876
      },
      "init-local": {
        "errors": [],
        "finished": 1710355582.279756,
        "recoverable_errors": {},
        "start": 1710355582.2255273
      },
      "last_update": "Wed, 13 Mar 2024 18:46:26 +0000",
      "modules-config": {
        "errors": [],
        "finished": 1710355585.5042186,
        "recoverable_errors": {},
        "start": 1710355585.334438
      },
      "modules-final": {
        "errors": [],
        "finished": 1710355586.9038777,
        "recoverable_errors": {},
        "start": 1710355586.8076844
      },
      "recoverable_errors": {},
      "stage": null,
      "status": "done"
    }

.. _More details on machine-id: https://www.freedesktop.org/software/systemd/man/machine-id.html
