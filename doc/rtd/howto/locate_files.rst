How to find files
*****************

Cloud-init log files
====================

``Cloud-init`` uses two files to log to:

- :file:`/var/log/cloud-init-output.log`:
  Captures the output from each stage of ``cloud-init`` when it runs.
- :file:`/var/log/cloud-init.log`:
  Very detailed log with debugging output, describing each action taken.
- :file:`/run/cloud-init`:
  Contains logs about how ``cloud-init`` enabled or disabled itself, as well as
  what platforms/datasources were detected. These logs are most useful when
  trying to determine what ``cloud-init`` did or did not run.

Be aware that each time a system boots, new logs are appended to the files in
:file:`/var/log`. Therefore, the files may contain information from more
than one boot.

When reviewing these logs, look for errors or Python tracebacks.

Configuration files
===================

``Cloud-init`` configuration files are provided in two places:

- :file:`/etc/cloud/cloud.cfg`
- :file:`/etc/cloud/cloud.cfg.d/*.cfg`

These files can define the modules that run during instance initialisation,
the datasources to evaluate on boot, as well as other settings.

See the :ref:`configuration sources explanation<configuration>` and
:ref:`configuration reference<base_config_reference>` pages for more details.

Data files
==========

Inside the :file:`/var/lib/cloud/` directory there are two important
subdirectories:

:file:`instance`
----------------

The :file:`/var/lib/cloud/instance` directory is a symbolic link that points
to the most recently used :file:`instance-id` directory. This folder contains
the information ``cloud-init`` received from datasources, including vendor and
user data. This can help to determine that the correct data was passed.

It also contains the :file:`datasource` file that contains the full information
about which datasource was identified and used to set up the system.

Finally, the :file:`boot-finished` file is the last thing that
``cloud-init`` creates.

:file:`data`
------------

The :file:`/var/lib/cloud/data` directory contain information related to the
previous boot:

* :file:`instance-id`:
  ID of the instance as discovered by ``cloud-init``. Changing this file has
  no effect.
* :file:`result.json`:
  JSON file showing both the datasource used to set up the instance, and
  whether any errors occurred.
* :file:`status.json`:
  JSON file showing the datasource used, a breakdown of all four modules,
  whether any errors occurred, and the start and stop times.
