.. _user_files:

Log and configuration files
*********************************

Cloud-init uses the filesystem to read inputs and write outputs. These files
are configuration and log files, respectively. If other methods of
:ref:`debugging cloud-init<how_to_debug>` fail, then digging into log files is
your next step in debugging.

.. _log_files:

Cloud-init log files
====================

Cloud-init's early boot logic runs before system loggers are available
or filesystems are mounted. Runtime logs and early boot logs have different
locations.

Runtime logs
------------

While booting, ``cloud-init`` logs to two different files:


- :file:`/var/log/cloud-init-output.log`:
  Captures the output from each stage of ``cloud-init`` when it runs.
- :file:`/var/log/cloud-init.log`:
  Very detailed log with debugging output, describing each action taken.

Be aware that each time a system boots, new logs are appended to the files in
:file:`/var/log`. Therefore, the files may contain information from more
than one boot.

When reviewing these logs, look for errors or Python tracebacks.

Early boot logs
---------------

Prior to initialization, ``cloud-init`` runs early detection and
enablement / disablement logic.

- :file:`/run/cloud-init/cloud-init-generator.log`:
  On systemd systems, this log file describes early boot enablement of
  cloud-init via the systemd generator. These logs are most useful if trying
  to figure out why cloud-init did not run.
- :file:`/run/cloud-init/ds-identify.log`:
  Contains logs about platform / datasource detection. These logs are most
  useful if cloud-init did not identify the correct datasource (cloud) to run
  on.



.. _configuration_files:

Configuration files
===================

``Cloud-init`` configuration files are provided in two places:

- :file:`/etc/cloud/cloud.cfg`
- :file:`/etc/cloud/cloud.cfg.d/*.cfg`

These files can define the modules that run during instance initialisation,
the datasources to evaluate on boot, as well as other settings.

See the :ref:`configuration sources explanation<configuration>` and
:ref:`configuration reference<base_config_reference>` pages for more details.
