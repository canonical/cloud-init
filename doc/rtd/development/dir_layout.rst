.. _dir_layout:

Directory layout
****************

``/var/lib/cloud``
==================

The main directory containing the cloud-init-specific subdirectories. It is
typically located at :file:`/var/lib` but there are certain configuration
scenarios where this can be changed.

.. TODO: expand this section

``.../data/``
-------------

This directory contains information about instance IDs, datasources and
hostnames of the previous and current instance if they are different. These can
be examined as needed to determine any information related to a previous boot
(if applicable).

``.../handlers/``
-----------------

Custom ``part-handlers`` code is written out here. Files that end up here are
written out within the scheme of ``part-handler-XYZ`` where ``XYZ`` is the
handler number (the first handler found starts at ``0``).

``.../instance``
----------------

A symlink to the current ``instances/`` subdirectory, which points to the
currently active instance. Note that the active instance depends on the loaded
datasource.

``.../instances/``
------------------

All instances that were created using this image end up with instance
identifier subdirectories (with corresponding data for each instance). The
currently active instance will be symlinked to the ``instance`` symlink file
defined previously.

``.../scripts/``
----------------

Scripts in one of these subdirectories are downloaded/created by the
corresponding ``part-handler``.

``.../seed/``
-------------

Contains seeded data files: :file:`meta-data`, :file:`network-config`,
:file:`user-data`, :file:`vendor-data`.

``.../sem/``
------------

Cloud-init has a concept of a module semaphore, which consists of the module
name and its frequency. These files are used to ensure a module is only run
"per-once", "per-instance", or "per-always". This folder contains
semaphore :file:`files` which are only supposed to run "per-once" (not tied
to the instance ID).
