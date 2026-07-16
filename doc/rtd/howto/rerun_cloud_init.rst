.. _rerun_cloud_init:

How to re-run ``cloud-init``
****************************

.. _fully_rerun_cloud_init:

How to fully re-run cloud-init
==============================

Most cloud-init configuration is only applied to the system once. This means
that simply rebooting the system will only re-run a subset of cloud-init.
Cloud-init provides two different options for re-running cloud-init for
debugging purposes.

.. warning::

    Making cloud-init run again may be destructive and must never be done on a
    production system. Artefacts such as ssh keys or passwords may be
    overwritten.

Remove the logs and cache, then reboot
--------------------------------------

This method will reboot the system as if cloud-init never ran. This
command does not remove all cloud-init artifacts from previous runs of
cloud-init, but it will clean enough artifacts to allow cloud-init to
think that it hasn't run yet. It will then re-run after a reboot.

.. code-block:: shell-session

   cloud-init clean --logs --reboot

Run a single cloud-init module
------------------------------

If you are using :ref:`user-data cloud-config<user_data_formats-cloud_config>`
format, you might wish to re-run just a single configuration module.
Cloud-init provides the ability to run a single module in isolation and
separately from boot. This command is:

.. code-block:: shell-session

   $ sudo cloud-init single --name cc_ssh --frequency always

Example output:

.. code-block::

   ...
   Generating public/private ed25519 key pair
   ...

This subcommand is not called by the init system. It can be called manually to
load the configured datasource and run a single cloud-config module once, using
the cached instance-data after the instance has booted.

.. note::

    Each cloud-config module has a module ``FREQUENCY`` configured: ``PER_INSTANCE``, ``PER_BOOT``, ``PER_ONCE`` or ``PER_ALWAYS``. When a module is run by cloud-init, it stores a semaphore file in :file:`/var/lib/cloud/instance/sem/config_<module_name>.<frequency>` which marks when the module last successfully ran. Presence of this semaphore file prevents a module from running again if it has already been run.

Inspect :file:`cloud-init.log` for output of what operations were performed as
a result.

.. _partially_rerun_cloud_init:

Manually run cloud-init stages
------------------------------

During normal boot of cloud-init, the init system runs the following command
command:

.. code-block:: shell-session

   cloud-init --all-stages

Keep in mind that running this manually may not behave the same as cloud-init
behaves when it is started by the init system. The first reason for this is
that cloud-init's stages are intended to run before and after specific events
in the boot order, so there are no guarantees that it will do the right thing
when running out of order. The second reason is that cloud-init will skip its
normal synchronization protocol when it detects that stdin is a tty for purpose
of debugging and development.

This command cannot be expected to be stable when executed outside of the init
system due to its ordering requirements.

Reboot the instance
-------------------

Rebooting the instance will re-run any parts of cloud-init that run per-boot.

.. code-block:: shell-session

    reboot -h now
