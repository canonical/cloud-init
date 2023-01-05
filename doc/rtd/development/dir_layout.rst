.. _dir_layout:

Directory layout
****************

``Cloud-init``'s directory structure is somewhat different from a regular
application: ::

  /var/lib/cloud/
      - data/
         - instance-id
         - previous-instance-id
         - datasource
         - previous-datasource
         - previous-hostname
      - handlers/
      - instance
      - instances/
          i-00000XYZ/
            - boot-finished
            - cloud-config.txt
            - datasource
            - handlers/
            - obj.pkl
            - scripts/
            - sem/
            - user-data.txt
            - user-data.txt.i
      - scripts/
         - per-boot/
         - per-instance/
         - per-once/
      - seed/
      - sem/

``/var/lib/cloud``

  The main directory containing the ``cloud-init``-specific subdirectories.
  It is typically located at :file:`/var/lib` but there are certain
  configuration scenarios where this can be altered.

.. TODO: expand this section

``data/``

  Contains information related to instance IDs, datasources and hostnames of
  the previous and current instance if they are different. These can be
  examined as needed to determine any information related to a previous boot
  (if applicable).

``handlers/``

  Custom ``part-handlers`` code is written out here. Files that end up here are
  written out within the scheme of ``part-handler-XYZ`` where ``XYZ`` is the
  handler number (the first handler found starts at ``0``).


``instance``

  A symlink to the current ``instances/`` subdirectory that points to the
  currently active instance (the active instance is dependent on the datasource
  loaded).

``instances/``

  All instances that were created using this image end up with instance
  identifier subdirectories (and corresponding data for each instance). The
  currently active instance will be symlinked to the ``instance`` symlink file
  defined previously.

``scripts/``

  Scripts that are downloaded/created by the corresponding ``part-handler``
  will end up in one of these subdirectories.

``seed/``

  Contains seeded data files: :file:`meta-data`, :file:`network-config`,
  :file:`user-data`, :file:`vendor-data`.

``sem/``

  ``Cloud-init`` has a concept of a module semaphore, which basically consists
  of the module name and its frequency. These files are used to ensure a module
  is only run "per-once", "per-instance", or "per-always". This folder contains
  semaphore :file:`files` which are only supposed to run "per-once" (not tied
  to the instance ID).
