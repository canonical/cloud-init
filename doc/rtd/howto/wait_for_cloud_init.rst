.. _wait_for_cloud_init:

How to wait for cloud-init
**************************

It is useful to be able to wait until cloud-init has completed running prior
to doing some other task.

CLI
===

Cloud-init's command ``cloud-init status --wait`` will exit once cloud-init has
completed.

SystemD
=======

Systems using systemd may be configured to start a service after cloud-init
completes. This may be accomplished by including
``After=cloud-final.service multi-user.target`` in the unit file. For example:

.. code-block::

    [Unit]
    Description=Example service
    After=cloud-final.service multi-user.target

    [Service]
    Type=oneshot
    ExecStart=sh -c 'echo "Howdy partner 🤠"'

    [Install]
    WantedBy=multi-user.target
