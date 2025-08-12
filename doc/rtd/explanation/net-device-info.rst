.. _net-device-info:

Net Device Info
===============

During boot, cloud-init prints a table to the serial console that summarizes
the information about detected network devices and their state at that
moment in time. A sample table appears as follows:

.. spelling:word-list::
   :ignore-words:
        Hw
        fe

.. csv-table::
   :align: center
   :header-rows: 1

    Device, Up, Address, Mask, Scope, Hw-Address
    eth0, True, 10.70.162.47, 255.255.255.0, global, 00:16:3e:1d:76:9b
    eth0, True, fe80::216:3eff:fe1d:769b/64, ., link, 00:16:3e:1d:76:9b
    lo, True, 127.0.0.1, 255.0.0.0, host, .
    lo, True, ::1/128, ., host, .

This table may be useful to analyze scenarios where an instance fails
to boot. The table is not printed in the final stage and it does not
necessarily represent the network’s final state.

Why does the table show interfaces as down?
----------------------------------------------

If the table shows interfaces as down, it means that they were not
activated by the system before the table was printed. There are a few
potential reasons this can occur. Some explanations include: the order
in which the distro starts system services results in network devices
being brought up after the table is printed, the supplied network
configuration either implicitly or explicitly does not bring up the
interfaces

The recommended troubleshooting advice is to inspect the network from
the shell and confirm whether or not it matches your expected setup
and follow the :ref:`debugging instructions<how_to_debug>`.
