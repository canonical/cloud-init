****************
Directory layout
****************

Cloudinits's directory structure is somewhat different from a regular application::

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

  The main directory containing the cloud-init specific subdirectories.
  It is typically located at ``/var/lib`` but there are certain configuration
  scenarios where this can be altered. 

  TBD, describe this overriding more.

``data/``

  Contains information related to instance ids, datasources and hostnames of the previous
  and current instance if they are different. These can be examined as needed to
  determine any information related to a previous boot (if applicable).

``handlers/``

  Custom ``part-handlers`` code is written out here. Files that end up here are written
  out with in the scheme of ``part-handler-XYZ`` where ``XYZ`` is the handler number (the
  first handler found starts at 0).


``instance``

  A symlink to the current ``instances/`` subdirectory that points to the currently
  active instance (which is active is dependent on the datasource loaded).

``instances/``

  All instances that were created using this image end up with instance identifier
  subdirectories (and corresponding data for each instance). The currently active
  instance will be symlinked the ``instance`` symlink file defined previously.

``scripts/``

  Scripts that are downloaded/created by the corresponding ``part-handler`` will end up
  in one of these subdirectories.

``seed/``

  TBD

``sem/``

  Cloud-init has a concept of a module semaphore, which basically consists
  of the module name and its frequency. These files are used to ensure a module
  is only ran `per-once`, `per-instance`, `per-always`. This folder contains
  semaphore `files` which are only supposed to run `per-once` (not tied to the instance id).

.. vi: textwidth=78
