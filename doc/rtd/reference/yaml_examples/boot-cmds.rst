.. _cce-boot-cmds:

Run commands during boot
************************

Both ``runcmd`` and ``bootcmd`` can be used to run commands during the boot
process.
``bootcmd`` runs on every boot, and is typically used to run commands very
early in the boot process (just after a boothook, and often before other
cloud-init modules have run).
``runcmd`` only runs on first boot, and **after** the instance has been started
and all other configuration has been applied.

Run commands only on first boot
===============================

- ``runcmd`` contains either a list of lists or a list of strings. Each item
  will be run in order, with output printed to the console.
- The list must be written in proper YAML -- be sure to quote any characters
  (such as ':') that would otherwise be "eaten".

For a full list of keys, refer to the `runcmd module`_ schema.

.. code-block:: yaml

    #cloud-config
    runcmd:
     - [ ls, -l, / ]
     - [ sh, -xc, "echo $(date) ': hello world!'" ]
     - [ sh, -c, echo "=========hello world=========" ]
     - ls -l /root
     - mkdir /run/mydir
     - [ wget, "http://slashdot.org", -O, /run/mydir/index.html ]

.. note::
   Don't write files to ``/tmp`` from cloud-init -- use ``/run/somedir``
   instead. Early boot environments can race ``systemd-tmpfiles-clean`` (LP:
   #1707222).

Run commands in early boot
==========================

- The ``INSTANCE_ID`` variable will be set to the current instance ID by
  default.
- The ``cloud-init-per`` command can be used to make ``bootcmd`` run exactly
  once.

For a full list of keys, refer to the `bootcmd module`_ schema.

.. code-block:: yaml

    #cloud-config
    bootcmd:
      - echo 192.168.1.130 us.archive.ubuntu.com >> /etc/hosts
      - [ cloud-init-per, once, mymkfs, mkfs, /dev/vdb ]

.. LINKS
.. _bootcmd module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#bootcmd
.. _runcmd module: https://cloudinit.readthedocs.io/en/latest/reference/modules.html#runcmd
