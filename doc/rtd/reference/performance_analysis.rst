.. _performance:

Performance analysis
********************

Occasionally, instances don't perform as well as expected, and so we provide
a simple tool to inspect which operations took the longest during boot and
setup.

.. _boot_time_analysis:

:command:`cloud-init analyze`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The `cloud-init` command has an analysis sub-command, :command:`analyze`, which
parses any :file:`cloud-init.log` file into formatted and sorted events. This
analysis reveals the most costly cloud-init operations and which configuration
options are responsible. These subcommands default to reading
:file:`/var/log/cloud-init.log`.

:command:`analyze show`
^^^^^^^^^^^^^^^^^^^^^^^

Parse and organise :file:`cloud-init.log` events by stage and include each
sub-stage granularity with time delta reports.

.. code-block:: shell-session

    $ cloud-init analyze show -i my-cloud-init.log

Example output:

.. code-block:: shell-session

    -- Boot Record 01 --
    The total time elapsed since completing an event is printed after the "@"
    character.
    The time the event takes is printed after the "+" character.

    Starting stage: modules-config
    |`->config-snap_config ran successfully @05.47700s +00.00100s
    |`->config-ssh-import-id ran successfully @05.47800s +00.00200s
    |`->config-locale ran successfully @05.48000s +00.00100s
    ...


:command:`analyze dump`
^^^^^^^^^^^^^^^^^^^^^^^

Parse :file:`cloud-init.log` into event records and return a list of
dictionaries that can be consumed for other reporting needs.

.. code-block:: shell-session

    $ cloud-init analyze dump -i my-cloud-init.log

Example output:

.. code-block::

    [
     {
      "description": "running config modules",
      "event_type": "start",
      "name": "modules-config",
      "origin": "cloudinit",
      "timestamp": 1510807493.0
     },...

:command:`analyze blame`
^^^^^^^^^^^^^^^^^^^^^^^^

Parse :file:`cloud-init.log` into event records and sort them based on the
highest time cost for a quick assessment of areas of cloud-init that may
need improvement.

.. code-block:: shell-session

    $ cloud-init analyze blame -i my-cloud-init.log

Example output:

.. code-block::

    -- Boot Record 11 --
         00.01300s (modules-final/config-scripts-per-boot)
         00.00400s (modules-final/config-final-message)
         00.00100s (modules-final/config-rightscale_userdata)
         ...

:command:`analyze boot`
^^^^^^^^^^^^^^^^^^^^^^^

Make subprocess calls to the kernel in order to get relevant pre-cloud-init
timestamps, such as the kernel start, kernel finish boot, and cloud-init
start.

.. code-block:: shell-session

    $ cloud-init analyze boot

Example output:

.. code-block::

    -- Most Recent Boot Record --
        Kernel Started at: 2019-06-13 15:59:55.809385
        Kernel ended boot at: 2019-06-13 16:00:00.944740
        Kernel time to boot (seconds): 5.135355
        Cloud-init start: 2019-06-13 16:00:05.738396
        Time between Kernel boot and Cloud-init start (seconds): 4.793656
