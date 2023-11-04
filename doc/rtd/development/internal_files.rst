.. _internal_files:

Internal Files: data
********************

Cloud-init uses the filesystem to store its own internal state. These files
are not intended for user consumption, but may prove helpful to debug
unexpected cloud-init failures.

.. _data_files:

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

The :file:`/var/lib/cloud/data` directory contains information related to the
previous boot:

* :file:`instance-id`:
  ID of the instance as discovered by ``cloud-init``. Changing this file has
  no effect.
* :file:`result.json`:
  JSON file showing both the datasource used to set up the instance, and
  whether any errors occurred.
* :file:`status.json`:
  JSON file showing the datasource used, a breakdown of all four stages,
  whether any errors occurred, and the start and stop times of the stages.
